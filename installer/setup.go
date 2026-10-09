package main

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/CharlesMod/wasp/catalog"
	"github.com/CharlesMod/wasp/engine"
	"github.com/CharlesMod/wasp/fetch"
	"github.com/CharlesMod/wasp/fit"
	"github.com/CharlesMod/wasp/profile"
	"github.com/CharlesMod/wasp/service"
	"github.com/CharlesMod/wasp/wizard"
)

//go:embed catalog.json
var catalogJSON []byte

//go:embed banner-dark.png
var bannerPNG []byte

// Mind kinds an answer can name.
const (
	KindLocal  = "local"
	KindURL    = "url"
	KindClaude = "claude"
	KindHive   = "hive"
)

const (
	ClaudeModel   = "claude-sonnet-5-5"
	HiveModelName = "gemma-4-26b-a4b-iq3s" // the Hive's name for it, when its court cannot say what it serves
	maxServeCtx   = 32768                  // tokens per slot DBee asks the server for, at most
)

// thinking models get a per-phase effort in dbee.toml.
var thinking = map[string]bool{"swift-qwen3.8-27b-iq3xs": true}

// Setup is DBee Setup as a wizard.Product. Every outside thing it touches is
// a field, so tests give fakes and a real run gets the defaults from newSetup.
type Setup struct {
	Purge   bool // uninstall removes the cases too
	Root    string
	Home    string
	Profile profile.Profile
	Catalog catalog.Catalog
	Version string
	Env     func(string) string
	Hive    Hive

	Svc    *service.Manager
	Lister UnitLister
	HTTP   *http.Client
	// Exec runs a command with extra environment (the mind probe).
	Exec func(ctx context.Context, env []string, name string, args ...string) ([]byte, error)
	// Python puts a private interpreter under root and returns its path.
	Python       func(ctx context.Context, root string, prog fetch.Progress) (string, error)
	EngineSource engine.Source
	// ProbeEngine starts the engine once to prove it runs here (engine.Probe
	// when the engine is built for the running system).
	ProbeEngine func(ctx context.Context, server string) error
	ModelURL    func(catalog.Entry) string
	EngineRoots []string
	ModelRoots  []string
	Payload     fs.FS
	PickPort    func() (int, error)
	// HealthWait bounds the wait on a server still loading its model.
	HealthWait time.Duration

	mu        sync.Mutex
	claudeKey string
	rec       *fit.Recommendation
	already   map[string]string
}

func (s *Setup) goos() string {
	if s.Profile.OS != "" {
		return s.Profile.OS
	}
	return runtime.GOOS
}

func (s *Setup) client() *http.Client {
	if s.HTTP != nil {
		return s.HTTP
	}
	return &http.Client{Timeout: 30 * time.Second}
}

// Info implements wizard.Product: the Hive palette's medic blue.
func (s *Setup) Info() wizard.Info {
	return wizard.Info{Name: "DBee", Version: s.Version, Accent: "#38a8ff", AccentBG: "#0b2236", OnAccent: "#0a0a0a"}
}

func (s *Setup) recommendation() fit.Recommendation {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.rec == nil {
		r := fit.Recommend(s.Profile, s.Catalog)
		s.rec = &r
	}
	return *s.rec
}

func (s *Setup) verdict(name string) (fit.Verdict, bool) {
	for _, v := range s.recommendation().Verdicts {
		if v.Entry.Name == name {
			return v, true
		}
	}
	return fit.Verdict{}, false
}

func (s *Setup) modelRoots() []string {
	return append([]string{filepath.Join(s.Root, "models")}, s.ModelRoots...)
}

// alreadyHere is the path of a model file this machine holds, by sha256.
func (s *Setup) alreadyHere(e catalog.Entry) string {
	s.mu.Lock()
	if p, ok := s.already[e.Name]; ok {
		s.mu.Unlock()
		return p
	}
	s.mu.Unlock()
	p, _ := fetch.Find(e.SHA256, e.Bytes, s.modelRoots()...)
	s.mu.Lock()
	if s.already == nil {
		s.already = map[string]string{}
	}
	s.already[e.Name] = p
	s.mu.Unlock()
	return p
}

// shapeWords says a shape in plain words.
func shapeWords(k string) string {
	switch k {
	case fit.GPU:
		return "all on the graphics card: fast"
	case fit.MoEOffload:
		return "experts in system RAM: good"
	case fit.Partial:
		return "some layers on the graphics card, the rest in RAM: slow"
	case fit.Unified:
		return "in this Mac's shared memory: fast"
	}
	return "on the processor: slow"
}

// serveShape is the shape and context per slot DBee asks llama-server for.
func (s *Setup) serveShape(v fit.Verdict) (fit.Shape, int) {
	ctx := v.Ctx
	if ctx > maxServeCtx {
		ctx = maxServeCtx
	}
	if ctx < v.Entry.MinContext() {
		ctx = v.Entry.MinContext()
	}
	f := *v.Entry.Facts
	if f.TotalBytes == 0 {
		f.TotalBytes = v.Entry.Bytes
	}
	for _, sh := range fit.Plan(s.Profile, f, fit.Want{Ctx: ctx, Slots: 1}) {
		if sh.Kind == v.Best.Kind && sh.Fits {
			return sh, ctx
		}
	}
	return v.Best, v.Best.Ctx
}

// choice is what the person picked, resolved.
type choice struct {
	Kind    string
	Entry   catalog.Entry
	Verdict fit.Verdict
	URL     string // KindURL: base URL; KindHive: the court
	Model   string
	Whole   bool
	Watches []string
	Health  string
}

// ErrNoMind is the page's word when nothing was chosen.
var ErrNoMind = errors.New("Choose a mind to continue.")

func (s *Setup) choose(a wizard.Answers) (choice, error) {
	c := choice{Kind: a.String("mind_kind"), Health: strings.TrimSpace(a.String("health"))}
	switch c.Kind {
	case KindLocal:
		v, ok := s.verdict(a.String("model"))
		if !ok {
			return c, errors.New("Choose one of the models listed.")
		}
		if v.Locked || v.Unknown {
			return c, fmt.Errorf("%s cannot run here: %s.", v.Entry.Label, v.Why)
		}
		c.Entry, c.Verdict, c.Model = v.Entry, v, v.Entry.Name
	case KindURL:
		c.URL = strings.TrimRight(strings.TrimSpace(a.String("mind_url")), "/")
		c.Model = strings.TrimSpace(a.String("mind_model"))
		if i := strings.Index(c.URL, "#"); i >= 0 {
			c.URL, c.Model = c.URL[:i], c.URL[i+1:]
		}
		if !strings.HasPrefix(c.URL, "http://") && !strings.HasPrefix(c.URL, "https://") {
			return c, errors.New("Give the address of the server, like http://127.0.0.1:8080/v1.")
		}
	case KindClaude:
		c.Model = ClaudeModel
	case KindHive:
		if !s.Hive.Here && s.Hive.Court == "" {
			return c, errors.New("No Hive was found on this machine.")
		}
		c.URL = strings.TrimRight(strings.TrimSpace(a.String("hive_court")), "/")
		if c.URL == "" {
			c.URL = s.Hive.Court
		}
		if c.URL == "" {
			return c, errors.New("Give the Hive's court address.")
		}
		c.Model = strings.TrimSpace(a.String("hive_model"))
		if c.Model == "" {
			c.Model = s.hiveModel(c.URL)
		}
	case "":
		return c, ErrNoMind
	default:
		return c, fmt.Errorf("Unknown kind of mind %q.", c.Kind)
	}
	c.Whole = a.Bool("whole_machine")
	for _, w := range a.Strings("watch") {
		if w = strings.TrimSpace(w); w != "" {
			c.Watches = append(c.Watches, w)
		}
	}
	if c.Whole {
		c.Health = "" // dbee.toml cannot say "the whole machine and a URL"
	}
	return c, nil
}

// Spec is the mind spec for dbee.toml; port is the ride-along server's.
func (c choice) Spec(port int) string {
	switch c.Kind {
	case KindLocal:
		return fmt.Sprintf("openai:http://127.0.0.1:%d/v1#%s", port, c.Entry.Name)
	case KindURL:
		if c.Model == "" {
			return "openai:" + c.URL
		}
		return "openai:" + c.URL + "#" + c.Model
	case KindClaude:
		return "claude:" + ClaudeModel
	}
	return c.Model
}

func (c choice) MindName() string {
	switch c.Kind {
	case KindLocal:
		return c.Entry.Label
	case KindClaude:
		return "Claude (" + ClaudeModel + ")"
	case KindHive:
		return c.Model + " through the Hive"
	}
	if c.Model != "" {
		return c.Model + " at " + c.URL
	}
	return c.URL
}

// probeMind makes one chat call to a server the person already runs.
func (s *Setup) probeMind(ctx context.Context, base, model string) error {
	body, _ := json.Marshal(map[string]any{"model": orDefault(model, "local"), "max_tokens": 1,
		"messages": []map[string]string{{"role": "user", "content": "ping"}}})
	u := strings.TrimRight(base, "/")
	if !strings.HasSuffix(u, "/v1") {
		u += "/v1"
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "POST", u+"/chat/completions", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.client().Do(req)
	if err != nil {
		return fmt.Errorf("Nothing answered at %s (%v).", base, err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
	if resp.StatusCode != 200 {
		return fmt.Errorf("%s answered %d: %s", base, resp.StatusCode, strings.TrimSpace(string(b)))
	}
	return nil
}

func orDefault(s, d string) string {
	if s == "" {
		return d
	}
	return s
}

func gbText(n int64) string { return fmt.Sprintf("%.1f GB", float64(n)/1e9) }

// need is a rough size, in bytes, of what the install will add to the disk.
func (s *Setup) need(c choice) (int64, []string) {
	const mb = 1 << 20
	var items []string
	total := int64(120 * mb)
	items = append(items, "Python 3.12, private to DBee (about 120 MB)")
	items = append(items, "DBee, the doctor bee (a few MB)")
	if c.Kind == KindLocal {
		eng := int64(200 * mb)
		if s.goos() == "windows" && engine.DetectFlavor(s.Profile) == engine.CUDA {
			eng = 700 * mb
		}
		total += eng
		items = append(items, "the engine, llama.cpp "+engine.LlamaTag+" (reused if one is here)")
		if p := s.alreadyHere(c.Entry); p != "" {
			items = append(items, c.Entry.Label+": already on this machine, not downloaded")
		} else {
			total += c.Entry.Bytes
			items = append(items, c.Entry.Label+" ("+gbText(c.Entry.Bytes)+" download)")
		}
	}
	return total, items
}

func (s *Setup) plural(n int, one, many string) string {
	if n == 1 {
		return one
	}
	return many
}

func exists(p string) bool { _, err := os.Stat(p); return err == nil }

// hiveModel is the mind DBee asks a Hive's router for: of the models the court
// says it has seats for (GET /v1/route/demand), the best ranked in DBee's
// catalog, else the one with the most seats; HiveModelName when the court
// cannot say. A name the router does not serve would wait for a seat forever.
func (s *Setup) hiveModel(court string) string {
	cl := http.Client{Timeout: 5 * time.Second}
	if s.HTTP != nil {
		cl.Transport = s.HTTP.Transport
	}
	resp, err := cl.Get(strings.TrimRight(court, "/") + "/v1/route/demand")
	if err != nil {
		return HiveModelName
	}
	defer resp.Body.Close()
	var d struct {
		Seats map[string]int `json:"seats"`
	}
	if resp.StatusCode != http.StatusOK || json.NewDecoder(resp.Body).Decode(&d) != nil {
		return HiveModelName
	}
	best, rank, seats := "", -1, -1
	for _, e := range s.Catalog.Models {
		if d.Seats[e.Name] > 0 && e.Rank > rank {
			best, rank = e.Name, e.Rank
		}
	}
	if best != "" {
		return best
	}
	for name, n := range d.Seats {
		if n > seats || n == seats && name < best {
			best, seats = name, n
		}
	}
	if best == "" || seats <= 0 {
		return HiveModelName
	}
	return best
}
