package main

import (
	"context"
	"embed"
	"encoding/base64"
	"errors"
	"fmt"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"github.com/CharlesMod/wasp/wizard"
)

//go:embed pages
var pageFiles embed.FS

func pageFile(name string) string {
	b, _ := pageFiles.ReadFile("pages/" + name)
	return string(b)
}

// Pages implements wizard.Product.
func (s *Setup) Pages() []wizard.Page {
	banner := "data:image/png;base64," + base64.StdEncoding.EncodeToString(bannerPNG)
	return []wizard.Page{
		{ID: "welcome", Title: "Welcome to DBee", Lede: "An on-call engineer for your machines.",
			HTML: strings.ReplaceAll(pageFile("welcome.html"), "{{BANNER}}", banner)},
		{ID: "machine", Title: "This machine", Lede: "What DBee found here, in plain words.",
			HTML: pageFile("machine.html"), Script: pageFile("machine.js"), Data: s.machineData},
		{ID: "mind", Title: "Choose a mind", Lede: "DBee thinks with a language model. These are the ones that fit this machine.",
			HTML: pageFile("mind.html"), Script: pageFile("mind.js"), Data: s.mindData, Check: s.mindCheck},
		{ID: "watch", Title: "What to watch", Lede: "DBee wakes when one of these fails.",
			HTML: pageFile("watch.html"), Script: pageFile("watch.js"), Data: s.watchData, Check: s.watchCheck},
		{ID: "ready", Title: "Ready to install", Lede: "Here is what will be put on this machine.",
			HTML: pageFile("ready.html"), Script: pageFile("ready.js"), Data: s.readyData, Check: s.readyCheck},
		{ID: "done", Title: "DBee is watching", Lede: "",
			HTML: pageFile("done.html"), Script: pageFile("done.js"), Data: s.doneData},
	}
}

func fmtGB(n uint64) string { return fmt.Sprintf("%.1f GB", float64(n)/(1<<30)) }

func (s *Setup) machineData(c wizard.Context) (any, error) {
	p := s.Profile
	osName := map[string]string{"linux": "Linux", "darwin": "macOS", "windows": "Windows"}[p.OS]
	if osName == "" {
		osName = p.OS
	}
	sys := osName + " (" + p.Arch + ")"
	if p.WSL {
		sys += ", under WSL"
	}
	rows := [][2]string{
		{"System", sys},
		{"Processor", fmt.Sprintf("%d %s", p.CPUs, s.plural(p.CPUs, "core", "cores"))},
		{"Memory", fmt.Sprintf("%s in all, %s free", fmtGB(p.RAM), fmtGB(p.RAMAvail))},
	}
	switch {
	case p.Unified:
		rows = append(rows, [2]string{"Graphics", "Apple silicon: shares the memory above"})
	case len(p.GPUs) == 0:
		rows = append(rows, [2]string{"Graphics", "none found: models run on the processor"})
	default:
		for _, g := range p.GPUs {
			v := g.Name
			if g.VRAM > 0 {
				v += ", " + fmtGB(g.VRAM)
			}
			rows = append(rows, [2]string{"Graphics", v})
		}
	}
	free := "not measured"
	if p.DiskFree > 0 {
		free = fmtGB(p.DiskFree) + " free"
	}
	rows = append(rows, [2]string{"Disk at " + s.Root, free})
	hive := "No Hive found. DBee does not need one."
	if s.Hive.Here {
		hive = "A Hive is here. DBee will reuse its engine and models, and can use its minds."
	}
	return map[string]any{"rows": rows, "hive": hive}, nil
}

type card struct {
	Name        string `json:"name"`
	Label       string `json:"label"`
	Why         string `json:"why"`
	Size        string `json:"size"`
	Shape       string `json:"shape"`
	Ctx         int    `json:"ctx"`
	Recommended bool   `json:"recommended"`
	Locked      bool   `json:"locked"`
	Reason      string `json:"reason"`
	Already     bool   `json:"already"`
}

func (s *Setup) mindData(c wizard.Context) (any, error) {
	r := s.recommendation()
	var cards []card
	// the recommended first, then the others that fit, then the locked
	order := []int{}
	if r.Pick >= 0 {
		order = append(order, r.Pick)
	}
	for i, v := range r.Verdicts {
		if i != r.Pick && !v.Locked && !v.Unknown {
			order = append(order, i)
		}
	}
	for i, v := range r.Verdicts {
		if v.Locked || v.Unknown {
			order = append(order, i)
		}
	}
	for _, i := range order {
		v := r.Verdicts[i]
		cd := card{Name: v.Entry.Name, Label: orDefault(v.Entry.Label, v.Entry.Name), Why: v.Entry.Why,
			Size: gbText(v.Entry.Bytes), Recommended: i == r.Pick, Locked: v.Locked || v.Unknown, Reason: v.Why}
		if !cd.Locked {
			sh, ctx := s.serveShape(v)
			cd.Shape, cd.Ctx = shapeWords(sh.Kind), ctx
			cd.Already = s.alreadyHere(v.Entry) != ""
		}
		cards = append(cards, cd)
	}
	return map[string]any{
		"cards":  cards,
		"hive":   map[string]any{"available": s.Hive.Court != "", "court": s.Hive.Court, "model": HiveModelName},
		"claude": map[string]any{"saved": HasSecret(s.Home, "ANTHROPIC_API_KEY") || s.hasKey()},
	}, nil
}

func (s *Setup) hasKey() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.claudeKey != ""
}

func (s *Setup) mindCheck(c wizard.Context, a wizard.Answers) error {
	ch, err := s.choose(a)
	if err != nil {
		return err
	}
	switch ch.Kind {
	case KindURL:
		if err := s.probeMind(context.Background(), ch.URL, ch.Model); err != nil {
			return err
		}
	case KindClaude:
		// the key moves out of the answers (which the page can read back)
		// into memory until the config stage writes it
		if k := strings.TrimSpace(a.String("claude_key")); k != "" {
			s.mu.Lock()
			s.claudeKey = k
			s.mu.Unlock()
		} else if !s.hasKey() && !HasSecret(s.Home, "ANTHROPIC_API_KEY") {
			return errors.New("Paste your Anthropic API key.")
		}
		delete(a, "claude_key")
	}
	return nil
}

func (s *Setup) watchData(c wizard.Context) (any, error) {
	lister := s.Lister
	if lister == nil {
		return map[string]any{"units": []Unit{}, "error": "Services cannot be listed here; choose the whole machine."}, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	us, err := lister.List(ctx)
	if err != nil {
		return map[string]any{"units": []Unit{}, "error": "Could not list the services (" + err.Error() + "). You can still watch the whole machine."}, nil
	}
	if us == nil {
		us = []Unit{}
	}
	return map[string]any{"units": us}, nil
}

func (s *Setup) watchCheck(c wizard.Context, a wizard.Answers) error {
	ch, err := s.choose(a)
	if err != nil {
		return err
	}
	if !ch.Whole && len(ch.Watches) == 0 {
		return errors.New("Pick at least one service, or choose the whole machine.")
	}
	if h := strings.TrimSpace(a.String("health")); h != "" {
		u, err := url.Parse(h)
		if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
			return errors.New("The health URL should look like http://127.0.0.1:8080/.")
		}
	}
	return nil
}

func (s *Setup) readyData(c wizard.Context) (any, error) {
	ch, err := s.choose(c.Answers)
	if err != nil {
		return map[string]any{"error": err.Error()}, nil
	}
	n, items := s.need(ch)
	items = append(items, "the configuration, dbee.toml")
	items = append(items, s.servicesLine(ch))
	rows := [][2]string{
		{"Install folder", s.Root},
		{"Mind", ch.MindName()},
		{"Takes about", gbText(n) + " of disk"},
	}
	out := map[string]any{"items": items, "rows": rows}
	if s.Profile.DiskFree > 0 && uint64(n) > s.Profile.DiskFree {
		out["error"] = fmt.Sprintf("This needs about %s and the disk has %s free.", gbText(n), fmtGB(s.Profile.DiskFree))
	}
	return out, nil
}

func (s *Setup) servicesLine(ch choice) string {
	if ch.Kind == KindLocal {
		return "two background services: dbee-mind (the model server, on 127.0.0.1 only) and dbee (the doctor)"
	}
	return "one background service: dbee (the doctor)"
}

func (s *Setup) readyCheck(c wizard.Context, a wizard.Answers) error {
	ch, err := s.choose(a)
	if err != nil {
		return err
	}
	n, _ := s.need(ch)
	if s.Profile.DiskFree > 0 && uint64(n) > s.Profile.DiskFree {
		return fmt.Errorf("This needs about %s and the disk has %s free.", gbText(n), fmtGB(s.Profile.DiskFree))
	}
	return nil
}

func (s *Setup) doneData(c wizard.Context) (any, error) {
	ch, err := s.choose(c.Answers)
	if err != nil {
		return nil, err
	}
	watching := "the whole machine"
	if !ch.Whole {
		watching = fmt.Sprintf("%d %s", len(ch.Watches), s.plural(len(ch.Watches), "service", "services"))
	}
	bin := filepath.Join(s.Root, "bin", "dbee")
	return map[string]any{
		"head": "DBee is watching " + watching + " with " + ch.MindName() + ".",
		"rows": [][2]string{
			{"Its cases", filepath.Join(s.Root, "home") + " (one folder per case)"},
			{"Its log", filepath.Join(s.Root, "logs", "dbee.log")},
			{"Run it by hand", bin + " --help"},
			{"Stop it", "stop the dbee service; the folder and services stay until you uninstall"},
			{"Uninstall", "run dbee-setup --uninstall"},
		},
	}, nil
}
