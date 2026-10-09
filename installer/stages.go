package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/CharlesMod/wasp/engine"
	"github.com/CharlesMod/wasp/fetch"
	"github.com/CharlesMod/wasp/runtime"
	"github.com/CharlesMod/wasp/service"
	"github.com/CharlesMod/wasp/wizard"
)

// state is what the stages leave for the ones after them, in <root>/state.json,
// so a Retry from a later stage and a second run find it.
type state struct {
	Python    string `json:"python,omitempty"`
	Engine    string `json:"engine,omitempty"`
	Model     string `json:"model,omitempty"`
	ModelSize int64  `json:"model_size,omitempty"`
	Port      int    `json:"port,omitempty"`
}

func (s *Setup) statePath() string { return filepath.Join(s.Root, "state.json") }

func (s *Setup) readState() state {
	var st state
	if b, err := os.ReadFile(s.statePath()); err == nil {
		_ = json.Unmarshal(b, &st)
	}
	return st
}

func (s *Setup) saveState(st state) error {
	if err := os.MkdirAll(s.Root, 0o755); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(st, "", " ")
	tmp := s.statePath() + ".tmp"
	if err := os.WriteFile(tmp, b, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.statePath())
}

func (s *Setup) update(f func(*state)) error {
	st := s.readState()
	f(&st)
	return s.saveState(st)
}

// Plan implements wizard.Product: the stages for what was chosen.
func (s *Setup) Plan(a wizard.Answers) ([]wizard.Stage, error) {
	ch, err := s.choose(a)
	if err != nil {
		return nil, err
	}
	if !ch.Whole && len(ch.Watches) == 0 {
		return nil, errors.New("nothing was chosen to watch")
	}
	stages := []wizard.Stage{
		{Name: "Python", Run: s.stagePython},
		{Name: "DBee", Run: s.stageDBee(ch)},
	}
	if ch.Kind == KindLocal {
		stages = append(stages,
			wizard.Stage{Name: "The engine", Run: s.stageEngine},
			wizard.Stage{Name: "The model", Run: s.stageModel(ch)})
	}
	stages = append(stages,
		wizard.Stage{Name: "Configuration", Run: s.stageConfig(ch)},
		wizard.Stage{Name: "Services", Run: s.stageServices(ch)},
		wizard.Stage{Name: "Check", Run: s.stageCheck(ch)})
	return stages, nil
}

func (s *Setup) stagePython(ctx context.Context, step *wizard.Step) error {
	prog := fetch.Progress(step.Progress)
	var exe string
	var err error
	if s.Python != nil {
		exe, err = s.Python(ctx, s.Root, prog)
	} else {
		if p := runtime.Interpreter(runtime.Dir(s.Root, runtime.DefaultVersion, runtime.Tag), s.goos()); exists(p) {
			step.Say("a private Python is already here; reusing it")
		} else {
			step.Say("fetching Python " + runtime.DefaultVersion + " (python-build-standalone)")
		}
		exe, err = runtime.Python(ctx, s.Root, "", runtime.Options{Client: s.HTTP, Progress: prog, GOOS: s.goos()})
	}
	if err != nil {
		return err
	}
	step.Say("Python at " + exe)
	return s.update(func(st *state) { st.Python = exe })
}

func (s *Setup) stageDBee(ch choice) func(context.Context, *wizard.Step) error {
	return func(ctx context.Context, step *wizard.Step) error {
		st := s.readState()
		if st.Python == "" {
			return errors.New("no Python recorded: run the Python stage first")
		}
		app := filepath.Join(s.Root, "app")
		n, err := copyPayload(s.payload(), app)
		if err != nil {
			return err
		}
		step.Sayf("DBee laid in %s (%d files)", app, n)
		name, body := Launcher(s.goos(), app, st.Python, s.courtFor(ch))
		bin := filepath.Join(s.Root, "bin")
		if err := os.MkdirAll(bin, 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(bin, name), []byte(body), 0o755); err != nil {
			return err
		}
		step.Say("launcher " + filepath.Join(bin, name))
		return nil
	}
}

func (s *Setup) payload() fs.FS {
	if s.Payload != nil {
		return s.Payload
	}
	return embeddedPayload()
}

func (s *Setup) courtFor(ch choice) string {
	if ch.Kind == KindHive {
		return ch.URL
	}
	return ""
}

func (s *Setup) engineRoots() []string {
	return append([]string{filepath.Join(s.Root, "engine")}, s.EngineRoots...)
}

func (s *Setup) stageEngine(ctx context.Context, step *wizard.Step) error {
	flavor := engine.DetectFlavor(s.Profile)
	if rec, ok := engine.Find(engine.LlamaTag, flavor, s.engineRoots()...); ok {
		step.Sayf("an engine is already here (llama.cpp %s, %s); reusing it", rec.Tag, rec.Flavor)
		return s.update(func(st *state) { st.Engine = rec.Server })
	}
	src := s.EngineSource
	if src == nil {
		src = engine.GitHub{Client: s.HTTP, Progress: fetch.Progress(step.Progress)}
	}
	step.Sayf("installing llama.cpp %s (%s)", engine.LlamaTag, flavor)
	rec, err := engine.Install(ctx, s.Root, src, engine.InstallOptions{Flavor: flavor,
		GOOS: s.goos(), GOARCH: s.Profile.Arch, Progress: fetch.Progress(step.Progress)})
	if err != nil {
		return err
	}
	step.Say("engine at " + rec.Server)
	return s.update(func(st *state) { st.Engine = rec.Server })
}

func (s *Setup) stageModel(ch choice) func(context.Context, *wizard.Step) error {
	return func(ctx context.Context, step *wizard.Step) error {
		e := ch.Entry
		if st := s.readState(); st.Model != "" && st.ModelSize == e.Bytes && filepath.Base(st.Model) == e.HFFile {
			if fi, err := os.Stat(st.Model); err == nil && fi.Size() == e.Bytes {
				step.Say("the model is already in place: " + st.Model)
				return nil
			}
		}
		if p, ok := fetch.Find(e.SHA256, e.Bytes, s.modelRoots()...); ok {
			step.Say("found " + e.Label + " already on this machine; using it where it is")
			return s.update(func(st *state) { st.Model, st.ModelSize = p, e.Bytes })
		}
		url := e.URL()
		if s.ModelURL != nil {
			url = s.ModelURL(e)
		}
		dest := filepath.Join(s.Root, "models", e.HFFile)
		step.Sayf("downloading %s (%s)", e.Label, gbText(e.Bytes))
		_, err := fetch.Download(ctx, url, dest, fetch.Options{SHA256: e.SHA256, Client: s.downloadClient(),
			Progress: fetch.Progress(step.Progress)})
		if err != nil {
			return err
		}
		step.Say("verified " + e.HFFile)
		return s.update(func(st *state) { st.Model, st.ModelSize = dest, e.Bytes })
	}
}

// downloadClient has no overall timeout: a model is gigabytes.
func (s *Setup) downloadClient() *http.Client {
	if s.HTTP != nil {
		return s.HTTP
	}
	return &http.Client{}
}

func (s *Setup) port() (int, error) {
	if st := s.readState(); st.Port > 0 {
		return st.Port, nil
	}
	if s.PickPort != nil {
		return s.PickPort()
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func (s *Setup) config(ch choice, port int) Config {
	cfg := Config{Spec: ch.Spec(port), Home: filepath.Join(s.Root, "home")}
	if ch.Kind == KindHive {
		cfg.Court = ch.URL
	}
	if ch.Kind == KindLocal && (thinking[ch.Entry.Name] || ch.Entry.Reasoning == "effort") {
		cfg.Effort = map[string]string{"triage": "low", "diagnose": "medium", "treat": "medium"}
	}
	if !ch.Whole {
		for _, w := range ch.Watches {
			cfg.Watches = append(cfg.Watches, Watch{Service: w})
		}
		if ch.Health != "" {
			cfg.Watches = append(cfg.Watches, Watch{Health: ch.Health})
		}
	}
	return cfg
}

func (s *Setup) stageConfig(ch choice) func(context.Context, *wizard.Step) error {
	return func(ctx context.Context, step *wizard.Step) error {
		port := 0
		if ch.Kind == KindLocal {
			p, err := s.port()
			if err != nil {
				return err
			}
			port = p
			if err := s.update(func(st *state) { st.Port = p }); err != nil {
				return err
			}
		}
		if ch.Kind == KindClaude {
			s.mu.Lock()
			key := s.claudeKey
			s.mu.Unlock()
			if key != "" {
				if err := WriteSecret(s.Home, "ANTHROPIC_API_KEY", key); err != nil {
					return fmt.Errorf("saving the key: %w", err)
				}
				step.Say("the key is kept in " + SecretsPath(s.Home) + " (owner only)")
			} else if !HasSecret(s.Home, "ANTHROPIC_API_KEY") {
				return errors.New("no Anthropic key to save")
			}
		}
		cfg := s.config(ch, port)
		if err := os.MkdirAll(cfg.Home, 0o755); err != nil {
			return err
		}
		p := filepath.Join(s.Root, "dbee.toml")
		if err := os.WriteFile(p, []byte(cfg.TOML()), 0o644); err != nil {
			return err
		}
		step.Say("wrote " + p)
		return nil
	}
}

func (s *Setup) manager() *service.Manager {
	if s.Svc != nil {
		return s.Svc
	}
	return service.Default()
}

func (s *Setup) specs(ch choice) ([]service.Spec, error) {
	st := s.readState()
	logs := filepath.Join(s.Root, "logs")
	var out []service.Spec
	if ch.Kind == KindLocal {
		if st.Engine == "" || st.Model == "" || st.Port == 0 {
			return nil, errors.New("the engine, model or port is not recorded: run the earlier stages")
		}
		shape, ctx := s.serveShape(ch.Verdict)
		args := engine.ServeArgs(st.Model, shape, ctx, shape.Slots, ch.Entry.Samplers,
			engine.ServeOptions{Host: engine.LoopbackHost, Port: st.Port})
		env := map[string]string{}
		switch s.goos() {
		case "linux":
			env["LD_LIBRARY_PATH"] = filepath.Dir(st.Engine)
		case "darwin":
			env["DYLD_LIBRARY_PATH"] = filepath.Dir(st.Engine)
		}
		out = append(out, service.Spec{Name: MindService, Description: "DBee's model server (" + ch.Entry.Label + ")",
			Exec: append([]string{st.Engine}, args...), Env: env, WorkDir: s.Root, RestartOnFailure: true,
			LogFile: filepath.Join(logs, "mind.log")})
	}
	bin := "dbee"
	if s.goos() == "windows" {
		bin = "dbee.cmd"
	}
	env := map[string]string{}
	if c := s.courtFor(ch); c != "" {
		env["DBEE_COURT"] = c
	}
	out = append(out, service.Spec{Name: DBeeService, Description: "DBee, the doctor bee",
		Exec: []string{filepath.Join(s.Root, "bin", bin), "watch", "--config", filepath.Join(s.Root, "dbee.toml")},
		Env:  env, WorkDir: s.Root, RestartOnFailure: true, LogFile: filepath.Join(logs, "dbee.log")})
	return out, nil
}

func (s *Setup) stageServices(ch choice) func(context.Context, *wizard.Step) error {
	return func(ctx context.Context, step *wizard.Step) error {
		specs, err := s.specs(ch)
		if err != nil {
			return err
		}
		m := s.manager()
		for _, sp := range specs {
			_ = m.Stop(ctx, sp.Name) // a running older copy picks up the new definition
			res, err := m.Install(ctx, sp)
			if err != nil {
				return fmt.Errorf("installing %s: %w", sp.Name, err)
			}
			for _, n := range res.Notes {
				step.Say("note: " + n)
			}
			if err := m.Start(ctx, sp.Name); err != nil {
				step.Say("note: could not start " + sp.Name + " now: " + err.Error())
			}
			step.Say("service " + sp.Name + " installed")
		}
		return nil
	}
}

// stageCheck waits for the mind, makes one call through DBee's own mind code,
// and reads both services' status. A failure leaves everything in place.
func (s *Setup) stageCheck(ch choice) func(context.Context, *wizard.Step) error {
	return func(ctx context.Context, step *wizard.Step) error {
		st := s.readState()
		m := s.manager()
		if ch.Kind == KindLocal {
			step.Say("waiting for the model to load")
			if err := s.waitHealth(ctx, step, st.Port); err != nil {
				return err
			}
			step.Say("the model server answers")
		}
		env := []string{"PYTHONPATH=" + filepath.Join(s.Root, "app")}
		if c := s.courtFor(ch); c != "" {
			env = append(env, "DBEE_COURT="+c)
		}
		run := s.Exec
		if run == nil {
			run = execEnv
		}
		cctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
		defer cancel()
		if out, err := run(cctx, env, st.Python, "-c", pyProbe, filepath.Join(s.Root, "dbee.toml")); err != nil {
			return fmt.Errorf("DBee could not reach its mind: %s", lastLines(string(out), err))
		}
		step.Say("DBee spoke to its mind")
		names := []string{DBeeService}
		if ch.Kind == KindLocal {
			names = []string{MindService, DBeeService}
		}
		for _, n := range names {
			if err := s.waitRunning(ctx, m, n); err != nil {
				return err
			}
			step.Say("service " + n + " is running")
		}
		return nil
	}
}

const pyProbe = `import sys
from dbee import config, minds
c = config.load(sys.argv[1]); config.apply_env(c)
r = minds.mind(c.mind, wait_s=30).chat([{"role": "user", "content": "Reply with the word ready."}], max_tokens=64)
print("ok", (r.text or "")[:40])`

func lastLines(out string, err error) string {
	lines := strings.Split(strings.TrimSpace(out), "\n")
	if len(lines) > 6 {
		lines = lines[len(lines)-6:]
	}
	t := strings.TrimSpace(strings.Join(lines, "\n"))
	if t == "" {
		return err.Error()
	}
	return t
}

// waitHealth waits for llama-server's /health, which answers 503 while the
// model loads. The wait is bounded (a watchdog on a server that never comes
// up) and ends at once when the service is seen to have failed.
func (s *Setup) waitHealth(ctx context.Context, step *wizard.Step, port int) error {
	limit := s.HealthWait
	if limit <= 0 {
		limit = 15 * time.Minute
	}
	ctx, cancel := context.WithTimeout(ctx, limit)
	defer cancel()
	url := fmt.Sprintf("http://127.0.0.1:%d/health", port)
	m := s.manager()
	delay := 250 * time.Millisecond
	for {
		req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
		if resp, err := s.client().Do(req); err == nil {
			_, _ = io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if resp.StatusCode == 200 {
				return nil
			}
		}
		if st, err := m.Status(ctx, MindService); err == nil && st.Failed {
			return fmt.Errorf("the model server stopped (%s); its log is %s", orDefault(st.Detail, "failed"), filepath.Join(s.Root, "logs", "mind.log"))
		}
		select {
		case <-ctx.Done():
			if errors.Is(ctx.Err(), context.DeadlineExceeded) {
				return fmt.Errorf("the model server did not become ready within %s; its log is %s", limit, filepath.Join(s.Root, "logs", "mind.log"))
			}
			return ctx.Err()
		case <-time.After(delay):
		}
		if delay < 2*time.Second {
			delay *= 2
		}
	}
}

// waitRunning reads a service's status until it runs; a service that has
// failed ends the wait. The bound is a watchdog on a start that never lands.
func (s *Setup) waitRunning(ctx context.Context, m *service.Manager, name string) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	var last service.State
	for {
		st, err := m.Status(ctx, name)
		if err == nil {
			last = st
			if st.Running {
				return nil
			}
			if st.Failed {
				return fmt.Errorf("service %s failed (%s); its log is in %s", name, orDefault(st.Detail, "failed"), filepath.Join(s.Root, "logs"))
			}
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("service %s is not running (%s)", name, orDefault(last.Detail, "no status"))
		case <-time.After(500 * time.Millisecond):
		}
	}
}
