package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"testing/fstest"

	"github.com/CharlesMod/wasp/catalog"
	"github.com/CharlesMod/wasp/fetch"
	"github.com/CharlesMod/wasp/gguf"
	"github.com/CharlesMod/wasp/profile"
	"github.com/CharlesMod/wasp/service"
	"github.com/CharlesMod/wasp/wizard"
)

const gib = 1 << 30

var (
	laptop4GB = profile.Profile{OS: "linux", Arch: "amd64", CPUs: 8, RAM: 16 * gib, RAMAvail: 11*gib + gib/2, DiskFree: 400 * gib,
		GPUs: []profile.GPU{{Vendor: "nvidia", Name: "Test GTX 1650 Ti", VRAM: 4 * gib}}}
	cpuOnly8GB = profile.Profile{OS: "linux", Arch: "amd64", CPUs: 4, RAM: 8 * gib, RAMAvail: 6 * gib, DiskFree: 400 * gib}
)

// fakeBox is everything outside the process, faked: services, downloads,
// the engine archive, Python, and the mind's health.
type fakeBox struct {
	t        *testing.T
	home     string
	root     string
	model    []byte
	modelSHA string

	mu          sync.Mutex
	runs        []string // service commands
	execs       [][]string
	modelHits   atomic.Int32
	engineHits  atomic.Int32
	pythonCalls atomic.Int32
	healthy     atomic.Bool
	srv         *httptest.Server
	units       []Unit
}

func newBox(t *testing.T) *fakeBox {
	t.Helper()
	t.Setenv("WASP_ENGINE_FLAVOR", "cpu")
	b := &fakeBox{t: t, home: t.TempDir(), model: bytes.Repeat([]byte("gguf"), 2048)}
	b.root = filepath.Join(b.home, "dbee-root")
	sum := sha256.Sum256(b.model)
	b.modelSHA = hex.EncodeToString(sum[:])
	b.healthy.Store(true)
	b.srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/tiny.gguf":
			b.modelHits.Add(1)
			http.ServeContent(w, r, "tiny.gguf", testTime, bytes.NewReader(b.model))
		case r.URL.Path == "/health":
			if b.healthy.Load() {
				io.WriteString(w, `{"status":"ok"}`)
			} else {
				http.Error(w, "loading", 503)
			}
		case strings.HasSuffix(r.URL.Path, "/chat/completions"):
			io.WriteString(w, `{"choices":[{"message":{"content":"pong"}}]}`)
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(b.srv.Close)
	return b
}

func (b *fakeBox) port() int {
	_, p, _ := net.SplitHostPort(strings.TrimPrefix(b.srv.URL, "http://"))
	n := 0
	for _, c := range p {
		n = n*10 + int(c-'0')
	}
	return n
}

func (b *fakeBox) entry() catalog.Entry {
	return catalog.Entry{Name: "tiny", Label: "Tiny test model", HFRepo: "x/y", HFFile: "tiny.gguf", SHA256: b.modelSHA,
		Bytes: int64(len(b.model)), Kind: catalog.Dense, Rank: 1, MinCtx: 4096, Why: "A model for tests.",
		Facts: &gguf.Facts{Arch: "qwen35", Layers: 4, KVLayers: 4, KVHeads: 2, KeyLen: 64, ValLen: 64,
			CtxTrain: 16384, TotalBytes: int64(len(b.model))}}
}

func (b *fakeBox) svcRun(ctx context.Context, name string, args ...string) ([]byte, error) {
	b.mu.Lock()
	b.runs = append(b.runs, name+" "+strings.Join(args, " "))
	b.mu.Unlock()
	if len(args) > 0 && strings.Contains(strings.Join(args, " "), " show ") || contains(args, "show") {
		for _, a := range args {
			if strings.HasSuffix(a, ".service") && !exists(filepath.Join(b.home, ".config", "systemd", "user", a)) {
				return []byte("LoadState=not-found\nActiveState=inactive\nSubState=dead\n"), nil // as systemd says of a unit it has no file for
			}
		}
		return []byte("LoadState=loaded\nActiveState=active\nSubState=running\nExecMainStatus=0\nResult=success\n"), nil
	}
	return nil, nil
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}

func (b *fakeBox) ran(sub string) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	for _, r := range b.runs {
		if strings.Contains(r, sub) {
			return true
		}
	}
	return false
}

// setup is a Setup whose every outside door is the box.
func (b *fakeBox) setup(p profile.Profile, tweak func(*Setup)) *Setup {
	t := b.t
	e := b.entry()
	s := &Setup{
		Root: b.root, Home: b.home, Profile: p, Catalog: catalog.Catalog{Models: []catalog.Entry{e}}, Version: "test",
		Env:    func(k string) string { return "" },
		Svc:    &service.Manager{GOOS: "linux", Home: b.home, StateDir: filepath.Join(b.home, "svc"), UID: 1000, Run: b.svcRun},
		Lister: fakeLister{b},
		HTTP:   b.srv.Client(),
		Exec: func(ctx context.Context, env []string, name string, args ...string) ([]byte, error) {
			b.mu.Lock()
			b.execs = append(b.execs, append([]string{name}, env...))
			b.mu.Unlock()
			return []byte("ok pong"), nil
		},
		Python: func(ctx context.Context, root string, prog fetch.Progress) (string, error) {
			b.pythonCalls.Add(1)
			exe := filepath.Join(root, "python", "bin", "python3")
			if err := os.MkdirAll(filepath.Dir(exe), 0o755); err != nil {
				return "", err
			}
			return exe, os.WriteFile(exe, []byte("#!/bin/sh\n"), 0o755)
		},
		EngineSource: fakeEngine{b},
		ModelURL:     func(catalog.Entry) string { return b.srv.URL + "/tiny.gguf" },
		EngineRoots:  []string{filepath.Join(b.home, "no-engines")},
		ModelRoots:   []string{filepath.Join(b.home, "no-models")},
		Payload: fstest.MapFS{
			"dbee/__init__.py":       {Data: []byte("# fake dbee\n")},
			"dbee/__pycache__/x.pyc": {Data: []byte("junk")},
			"assets/runbook.jsonl":   {Data: []byte("{}\n")},
			"assets/fixes/a.sh":      {Data: []byte("#!/bin/sh\n")},
		},
		PickPort:   func() (int, error) { return b.port(), nil },
		HealthWait: 0,
	}
	if tweak != nil {
		tweak(s)
	}
	_ = t
	return s
}

type fakeLister struct{ b *fakeBox }

func (f fakeLister) List(context.Context) ([]Unit, error) { return f.b.units, nil }

type fakeEngine struct{ b *fakeBox }

func (fakeEngine) Name() string { return "fake" }
func (f fakeEngine) Fetch(ctx context.Context, tag, asset, dest string) (string, error) {
	f.b.engineHits.Add(1)
	var raw bytes.Buffer
	gz := gzip.NewWriter(&raw)
	tw := tar.NewWriter(gz)
	body := []byte("#!/bin/sh\n")
	tw.WriteHeader(&tar.Header{Name: "llama-" + tag + "/llama-server", Mode: 0o755, Size: int64(len(body)), Typeflag: tar.TypeReg})
	tw.Write(body)
	tw.Close()
	gz.Close()
	if err := os.WriteFile(dest, raw.Bytes(), 0o644); err != nil {
		return "", err
	}
	sum := sha256.Sum256(raw.Bytes())
	return hex.EncodeToString(sum[:]), nil
}

// drive runs the wizard over HTTP, like the window does.
type driver struct {
	t     *testing.T
	srv   *wizard.Server
	stop  func()
	token string
}

func serve(t *testing.T, s *Setup) *driver {
	t.Helper()
	p := s.Profile
	srv, err := wizard.New(s, wizard.Options{Root: s.Root, Profile: &p})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- srv.Serve(ctx) }()
	return &driver{t: t, srv: srv, token: srv.Token(), stop: func() { cancel(); <-done }}
}

func (d *driver) call(method, path string, body any) (int, []byte) {
	d.t.Helper()
	var rd io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		rd = bytes.NewReader(b)
	}
	req, _ := http.NewRequest(method, "http://"+d.srv.Addr()+path, rd)
	req.Header.Set(wizard.TokenHeader, d.token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		d.t.Fatal(err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, b
}

// page is a page's data and the answers kept so far.
func (d *driver) page(id string) map[string]any {
	d.t.Helper()
	code, b := d.call("GET", "/api/page/"+id, nil)
	if code != 200 {
		d.t.Fatalf("page %s: %d %s", id, code, b)
	}
	var out struct {
		Data    map[string]any `json:"data"`
		Answers map[string]any `json:"answers"`
	}
	if err := json.Unmarshal(b, &out); err != nil {
		d.t.Fatal(err)
	}
	if out.Data == nil {
		out.Data = map[string]any{}
	}
	out.Data["__answers"] = out.Answers
	return out.Data
}

// check posts a page's answers and returns the page's complaint, or "".
func (d *driver) check(id string, ans map[string]any) string {
	d.t.Helper()
	code, b := d.call("POST", "/api/check", map[string]any{"page": id, "answers": ans})
	if code != 200 {
		d.t.Fatalf("check %s: %d %s", id, code, b)
	}
	var out struct {
		OK    bool   `json:"ok"`
		Error string `json:"error"`
	}
	json.Unmarshal(b, &out)
	if out.OK {
		return ""
	}
	return out.Error
}

func readFile(t *testing.T, p string) string {
	t.Helper()
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func httpGet(url string) (string, error) {
	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return string(b), nil
}
