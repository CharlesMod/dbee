package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/CharlesMod/wasp/catalog"
	"github.com/CharlesMod/wasp/wizard"
)

func install(t *testing.T, s *Setup, a wizard.Answers) (string, error) {
	t.Helper()
	p := s.Profile
	var out bytes.Buffer
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	err := wizard.Run(ctx, s, wizard.Options{Root: s.Root, Profile: &p, Answers: a, Stdout: &out})
	return out.String(), err
}

func localAnswers() wizard.Answers {
	return wizard.Answers{"mind_kind": "local", "model": "tiny", "watch": []string{"nginx", "postgresql"}, "health": "http://127.0.0.1:8080/"}
}

func TestAFullInstallWritesTheConfigTheLauncherAndBothServices(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, nil)
	out, err := install(t, s, localAnswers())
	if err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	toml := readFile(t, filepath.Join(b.root, "dbee.toml"))
	for _, want := range []string{
		`spec = "openai:http://127.0.0.1:` + itoa(b.port()) + `/v1#tiny"`,
		"[[watch]]\nservice = \"nginx\"", "service = \"postgresql\"", `health = "http://127.0.0.1:8080/"`,
		`home = "` + filepath.Join(b.root, "home") + `"`,
	} {
		if !strings.Contains(toml, want) {
			t.Fatalf("dbee.toml lacks %q:\n%s", want, toml)
		}
	}
	launcher := readFile(t, filepath.Join(b.root, "bin", "dbee"))
	if !strings.Contains(launcher, "PYTHONPATH='"+filepath.Join(b.root, "app")+"'") || !strings.Contains(launcher, "-m dbee") ||
		!strings.Contains(launcher, "export PYTHONUNBUFFERED") {
		t.Fatalf("launcher:\n%s", launcher)
	}
	if fi, _ := os.Stat(filepath.Join(b.root, "bin", "dbee")); runtime.GOOS != "windows" && fi.Mode()&0o100 == 0 {
		t.Fatal("launcher is not executable")
	}
	if !exists(filepath.Join(b.root, "app", "dbee", "__init__.py")) || !exists(filepath.Join(b.root, "app", "assets", "runbook.jsonl")) {
		t.Fatal("the package and its assets are laid under app/")
	}
	if exists(filepath.Join(b.root, "app", "dbee", "__pycache__")) {
		t.Fatal("bytecode caches are left out")
	}
	if got := readFile(t, filepath.Join(b.root, "models", "tiny.gguf")); got != string(b.model) {
		t.Fatal("the model landed verified")
	}
	mind := readFile(t, filepath.Join(b.home, ".config", "systemd", "user", "dbee-mind.service"))
	for _, want := range []string{"llama-server", `"--host" "127.0.0.1"`, `"--port" "` + itoa(b.port()) + `"`, `"-ngl" "0"`, "tiny.gguf", "Restart=on-failure"} {
		if !strings.Contains(mind, want) {
			t.Fatalf("dbee-mind unit lacks %q:\n%s", want, mind)
		}
	}
	doc := readFile(t, filepath.Join(b.home, ".config", "systemd", "user", "dbee.service"))
	if !strings.Contains(doc, `"`+filepath.Join(b.root, "bin", "dbee")+`" "watch" "--config" "`+filepath.Join(b.root, "dbee.toml")+`"`) {
		t.Fatalf("dbee unit:\n%s", doc)
	}
	if !strings.Contains(doc, filepath.Join(b.root, "logs", "dbee.log")) {
		t.Fatalf("dbee logs to the logs folder:\n%s", doc)
	}
	if !b.ran("enable --now dbee-mind.service") || !b.ran("enable --now dbee.service") {
		t.Fatalf("both services enabled: %v", b.runs)
	}
	if len(b.execs) != 1 || !strings.Contains(strings.Join(b.execs[0], " "), "PYTHONPATH="+filepath.Join(b.root, "app")) {
		t.Fatalf("one tiny call through DBee's own mind code: %v", b.execs)
	}
}

func TestASecondRunReusesEverything(t *testing.T) {
	b := newBox(t)
	if out, err := install(t, b.setup(cpuOnly8GB, nil), localAnswers()); err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	m, e := b.modelHits.Load(), b.engineHits.Load()
	if m != 1 || e != 1 {
		t.Fatalf("first run downloads once: model %d engine %d", m, e)
	}
	out, err := install(t, b.setup(cpuOnly8GB, nil), localAnswers())
	if err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	if b.modelHits.Load() != m || b.engineHits.Load() != e {
		t.Fatalf("second run downloaded again: model %d engine %d", b.modelHits.Load(), b.engineHits.Load())
	}
	if !strings.Contains(out, "already here") && !strings.Contains(out, "already in place") {
		t.Fatalf("the second run should say it reused things:\n%s", out)
	}
}

func TestAnInstalledEngineAndModelFoundElsewhereAreUsedWhereTheyAre(t *testing.T) {
	b := newBox(t)
	outside := filepath.Join(b.home, "hive-models")
	os.MkdirAll(outside, 0o755)
	os.WriteFile(filepath.Join(outside, "theirs.gguf"), b.model, 0o644)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.ModelRoots = []string{outside} })
	if out, err := install(t, s, localAnswers()); err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	if b.modelHits.Load() != 0 {
		t.Fatal("a model found by sha256 is not downloaded")
	}
	if exists(filepath.Join(b.root, "models", "tiny.gguf")) {
		t.Fatal("and not copied")
	}
	if unit := readFile(t, filepath.Join(b.home, ".config", "systemd", "user", "dbee-mind.service")); !strings.Contains(unit, filepath.Join(outside, "theirs.gguf")) {
		t.Fatalf("the server points at the model where it is:\n%s", unit)
	}
}

func TestUninstallRemovesTheRootAndKeepsAModelOutsideIt(t *testing.T) {
	b := newBox(t)
	outside := filepath.Join(b.home, "hive-models")
	os.MkdirAll(outside, 0o755)
	theirs := filepath.Join(outside, "theirs.gguf")
	os.WriteFile(theirs, b.model, 0o644)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.ModelRoots = []string{outside} })
	if out, err := install(t, s, localAnswers()); err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	var out bytes.Buffer
	if err := s.Uninstall(context.Background(), &out); err != nil {
		t.Fatalf("%v\n%s", err, out.String())
	}
	if exists(b.root) {
		t.Fatal("the root is gone")
	}
	if !exists(theirs) {
		t.Fatal("a model outside the root is never removed")
	}
	for _, n := range []string{"dbee", "dbee-mind"} {
		if exists(filepath.Join(b.home, ".config", "systemd", "user", n+".service")) || !b.ran("disable --now "+n+".service") {
			t.Fatalf("service %s should be removed", n)
		}
	}
}

func TestUninstallLeavesAFolderThatIsNotDBees(t *testing.T) {
	b := newBox(t)
	os.MkdirAll(b.root, 0o755)
	os.WriteFile(filepath.Join(b.root, "photos.jpg"), []byte("x"), 0o644)
	s := b.setup(cpuOnly8GB, nil)
	if err := s.Uninstall(context.Background(), &bytes.Buffer{}); err == nil || !exists(filepath.Join(b.root, "photos.jpg")) {
		t.Fatalf("a foreign folder must be left alone: %v", err)
	}
	s.Root = b.home
	if err := s.Uninstall(context.Background(), &bytes.Buffer{}); err == nil {
		t.Fatal("the home folder must be refused")
	}
}

func TestClaudeIsInstalledWithItsKeyInAnOwnerOnlyFile(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, nil)
	out, err := install(t, s, wizard.Answers{"mind_kind": "claude", "claude_key": "sk-ant-secret-xyz", "whole_machine": true})
	if err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	secrets := filepath.Join(b.home, ".config", "dbee", "secrets.env")
	if got := readFile(t, secrets); got != "ANTHROPIC_API_KEY=sk-ant-secret-xyz\n" {
		t.Fatalf("secrets.env: %q", got)
	}
	if runtime.GOOS != "windows" {
		if fi, _ := os.Stat(secrets); fi.Mode().Perm() != 0o600 {
			t.Fatalf("mode %v", fi.Mode())
		}
	}
	toml := readFile(t, filepath.Join(b.root, "dbee.toml"))
	if !strings.Contains(toml, `spec = "claude:claude-sonnet-5-5"`) || strings.Contains(toml, "[[watch]]") {
		t.Fatalf("toml:\n%s", toml)
	}
	var all strings.Builder
	filepath.Walk(b.root, func(p string, fi os.FileInfo, err error) error {
		if err == nil && fi.Mode().IsRegular() && !strings.HasSuffix(p, "python3") {
			bb, _ := os.ReadFile(p)
			all.Write(bb)
		}
		return nil
	})
	all.WriteString(out)
	all.WriteString(strings.Join(b.runs, "\n"))
	if strings.Contains(all.String(), "sk-ant-secret-xyz") {
		t.Fatal("the key leaked into the install folder, the output or a command")
	}
	if b.modelHits.Load() != 0 || b.engineHits.Load() != 0 || b.ran("dbee-mind") {
		t.Fatal("a hosted mind needs no model, engine or model server")
	}
}

func TestTheHivesMindNeedsOnlyTheCourtInTheEnvironment(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.Hive = Hive{Here: true, Court: "http://court.invalid:4410"} })
	out, err := install(t, s, wizard.Answers{"mind_kind": "hive", "whole_machine": true})
	if err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	toml := readFile(t, filepath.Join(b.root, "dbee.toml"))
	if !strings.Contains(toml, `spec = "`+HiveModelName+`"`) || !strings.Contains(toml, `court = "http://court.invalid:4410"`) {
		t.Fatalf("toml:\n%s", toml)
	}
	if !strings.Contains(readFile(t, filepath.Join(b.root, "bin", "dbee")), "DBEE_COURT='http://court.invalid:4410'") {
		t.Fatal("the launcher exports the court")
	}
	if !strings.Contains(readFile(t, filepath.Join(b.home, ".config", "systemd", "user", "dbee.service")), "DBEE_COURT=http://court.invalid:4410") {
		t.Fatal("the service environment holds the court")
	}
}

func TestACheckThatFailsLeavesEverythingInstalledAndSaysWhat(t *testing.T) {
	b := newBox(t)
	b.healthy.Store(false)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.HealthWait = 300 * time.Millisecond })
	out, err := install(t, s, localAnswers())
	if err == nil || !strings.Contains(err.Error(), "did not become ready") {
		t.Fatalf("want a health timeout, got %v", err)
	}
	for _, p := range []string{"dbee.toml", "bin/dbee", "models/tiny.gguf", "state.json"} {
		if !exists(filepath.Join(b.root, p)) {
			t.Fatalf("%s should be left in place\n%s", p, out)
		}
	}
	b.healthy.Store(true)
	if _, err := install(t, b.setup(cpuOnly8GB, nil), localAnswers()); err != nil {
		t.Fatalf("a retry resumes: %v", err)
	}
}

func TestAMissingPayloadIsSaidPlainly(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.Payload = emptyFS{} })
	_, err := install(t, s, localAnswers())
	if err == nil || !strings.Contains(err.Error(), "stage.sh") {
		t.Fatalf("got %v", err)
	}
}

func TestTheWholeWizardRunsOverHTTPAndTheResultIsDone(t *testing.T) {
	b := newBox(t)
	d := serve(t, b.setup(cpuOnly8GB, nil))
	defer d.stop()
	for _, st := range []struct {
		id  string
		ans map[string]any
	}{{"mind", map[string]any{"mind_kind": "local", "model": "tiny"}}, {"watch", map[string]any{"whole_machine": true}}, {"ready", map[string]any{}}} {
		if msg := d.check(st.id, st.ans); msg != "" {
			t.Fatalf("%s: %s", st.id, msg)
		}
	}
	if code, body := d.call("POST", "/api/start", map[string]any{}); code != 202 {
		t.Fatalf("%d %s", code, body)
	}
	var snap wizard.Snapshot
	for seen := 0; snap.State == "" || snap.State == wizard.StateRunning; {
		_, body := d.call("GET", "/api/run?seen="+itoa(seen), nil)
		if err := json.Unmarshal(body, &snap); err != nil {
			t.Fatal(err)
		}
		seen = snap.Seq
	}
	if snap.State != wizard.StateDone {
		t.Fatalf("state %s: %s (%s)", snap.State, snap.Error, snap.Failed)
	}
	done := d.page("done")
	if !strings.Contains(done["head"].(string), "the whole machine") || !strings.Contains(done["head"].(string), "Tiny test model") {
		t.Fatalf("done page: %v", done["head"])
	}
	want := []string{"Python", "DBee", "The engine", "The model", "Configuration", "Services", "Check"}
	if strings.Join(snap.Stages, ",") != strings.Join(want, ",") {
		t.Fatalf("stages %v", snap.Stages)
	}
}

func TestMainRunsNonInteractivelyAndUninstalls(t *testing.T) {
	b := newBox(t)
	var out, errw bytes.Buffer
	tweak := func(s *Setup) {
		*s = *b.setup(cpuOnly8GB, nil)
	}
	env := func(string) string { return "" }
	code := run(context.Background(), []string{"--yes", "--model", "tiny", "--watch", "nginx", "--root", b.root}, &out, &errw, env, tweak)
	if code != 0 {
		t.Fatalf("exit %d\n%s\n%s", code, out.String(), errw.String())
	}
	if !strings.Contains(readFile(t, filepath.Join(b.root, "dbee.toml")), `service = "nginx"`) {
		t.Fatal("--watch is honoured")
	}
	code = run(context.Background(), []string{"--uninstall", "--root", b.root}, &out, &errw, env, tweak)
	if code != 0 || exists(b.root) {
		t.Fatalf("uninstall exit %d\n%s", code, errw.String())
	}
	if code := run(context.Background(), []string{"--yes", "--model", "tiny", "--claude"}, &out, &errw, env, tweak); code != 2 {
		t.Fatalf("two minds at once is a usage error, got %d", code)
	}
}

func TestMainServesTheWindowWithNoWindowAndAProfileOverride(t *testing.T) {
	pj := filepath.Join(t.TempDir(), "p.json")
	raw, _ := json.Marshal(cpuOnly8GB)
	os.WriteFile(pj, raw, 0o644)
	t.Setenv("WASP_PROFILE_JSON", pj)
	env := func(k string) string { return os.Getenv(k) }
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pr, pw, _ := os.Pipe()
	done := make(chan int, 1)
	go func() {
		done <- run(ctx, []string{"--no-window", "--root", filepath.Join(t.TempDir(), "r")}, pw, os.Stderr, env,
			func(s *Setup) { s.Lister = nil })
		pw.Close()
	}()
	buf := make([]byte, 512)
	n, _ := pr.Read(buf)
	line := strings.TrimSpace(string(buf[:n]))
	url := strings.TrimPrefix(line, "setup is at ")
	if !strings.HasPrefix(url, "http://127.0.0.1:") {
		t.Fatalf("got %q", line)
	}
	resp, err := httpGet(url)
	if err != nil || !strings.Contains(resp, "DBee") || !strings.Contains(resp, "#38a8ff") {
		t.Fatalf("the window page: %v %.80s", err, resp)
	}
	cancel()
	if c := <-done; c != 0 {
		t.Fatalf("exit %d", c)
	}
}

func TestLauncherAndTomlForWindows(t *testing.T) {
	name, body := Launcher("windows", `C:\D\app`, `C:\D\python\python.exe`, "http://c:1")
	if name != "dbee.cmd" || !strings.Contains(body, `set "PYTHONPATH=C:\D\app"`) || !strings.Contains(body, `"C:\D\python\python.exe" -m dbee %*`) || !strings.Contains(body, "DBEE_COURT") || !strings.Contains(body, `set "PYTHONUNBUFFERED=1"`) {
		t.Fatalf("%s\n%s", name, body)
	}
	toml := Config{Spec: "claude:x", Home: `C:\D\home`}.TOML()
	if !strings.Contains(toml, `home = "C:\\D\\home"`) {
		t.Fatalf("backslashes are escaped:\n%s", toml)
	}
	if got := DefaultRoot("windows", `C:\Users\x`, func(k string) string {
		if k == "LOCALAPPDATA" {
			return `C:\L`
		}
		return ""
	}); got != filepath.Join(`C:\L`, "DBee") {
		t.Fatal(got)
	}
	if got := DefaultRoot("darwin", "/h", func(string) string { return "" }); got != "/h/Library/Application Support/DBee" {
		t.Fatal(got)
	}
	if got := DefaultRoot("linux", "/h", func(string) string { return "" }); got != "/h/.local/share/dbee" {
		t.Fatal(got)
	}
}

func TestAnEngineThatCannotStartHereStopsTheInstallNamingWhatItLacks(t *testing.T) {
	b := newBox(t)
	lacks := errors.New("the model server needs libgomp.so.1, which this machine lacks: install libgomp1 on Debian and Ubuntu, libgomp on Fedora, then Retry")
	s := b.setup(cpuOnly8GB, func(s *Setup) {
		s.ProbeEngine = func(context.Context, string) error { return lacks }
	})
	out, err := install(t, s, localAnswers())
	if err == nil || !strings.Contains(err.Error(), "libgomp1") {
		t.Fatalf("want the missing library named, got %v\n%s", err, out)
	}
	if exists(filepath.Join(b.root, "dbee.toml")) {
		t.Fatal("no service is built on an engine that cannot start")
	}
	if _, err := install(t, b.setup(cpuOnly8GB, nil), localAnswers()); err != nil {
		t.Fatalf("once the library is there, a retry resumes: %v", err)
	}
}

func TestTheHivesMindIsAModelItsCourtServes(t *testing.T) {
	court := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/route/demand" {
			http.NotFound(w, r)
			return
		}
		io.WriteString(w, `{"demand":{},"seats":{"qwen3.5-4b-iq4xs":3,"gemma-4-26b-a4b-iq3s":10,"some-other-model":40}}`)
	}))
	defer court.Close()
	b := newBox(t)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.Hive = Hive{Here: true, Court: court.URL} })
	full, err := catalog.Parse(catalogJSON)
	if err != nil {
		t.Fatal(err)
	}
	box := s.Catalog
	s.Catalog = full
	if got := s.hiveModel(court.URL); got != "gemma-4-26b-a4b-iq3s" {
		t.Fatalf("the best-ranked model the Hive serves: got %q", got)
	}
	s.Catalog = box
	if _, err := install(t, s, wizard.Answers{"mind_kind": "hive", "whole_machine": true}); err != nil {
		t.Fatal(err)
	}
	if toml := readFile(t, filepath.Join(b.root, "dbee.toml")); !strings.Contains(toml, `spec = "some-other-model"`) {
		t.Fatalf("toml:\n%s", toml)
	}
	s.Catalog.Models = nil
	if got := s.hiveModel(court.URL); got != "some-other-model" {
		t.Fatalf("with nothing of the catalog served, the most seats: got %q", got)
	}
	if got := s.hiveModel("http://127.0.0.1:1"); got != HiveModelName {
		t.Fatalf("a court that cannot say: got %q", got)
	}
}

func TestUninstallKeepsTheCasesUnlessPurged(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, nil)
	if out, err := install(t, s, localAnswers()); err != nil {
		t.Fatalf("%v\n%s", err, out)
	}
	c := filepath.Join(b.root, "home", "cases", "20261009-212231-17bc.json")
	os.MkdirAll(filepath.Dir(c), 0o755)
	os.WriteFile(c, []byte(`{"id":"20261009-212231-17bc"}`), 0o644)
	var out bytes.Buffer
	if err := s.Uninstall(context.Background(), &out); err != nil {
		t.Fatalf("%v\n%s", err, out.String())
	}
	if !exists(c) || exists(filepath.Join(b.root, "app")) || exists(filepath.Join(b.root, "dbee.toml")) {
		t.Fatalf("the cases stay and the rest goes:\n%s", out.String())
	}
	if !strings.Contains(out.String(), "kept its 1 case in") {
		t.Fatalf("the uninstall says what it kept:\n%s", out.String())
	}
	s.Purge = true
	if err := s.Uninstall(context.Background(), &out); err != nil || exists(b.root) {
		t.Fatalf("--purge removes the cases and the folder: %v\n%s", err, out.String())
	}
}
