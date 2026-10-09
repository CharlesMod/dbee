package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/CharlesMod/wasp/catalog"
	"github.com/CharlesMod/wasp/profile"
)

// realCatalogSetup is a Setup over the embedded catalog and a posed machine.
func realCatalogSetup(t *testing.T, p profile.Profile) (*Setup, *fakeBox) {
	b := newBox(t)
	s := b.setup(p, func(s *Setup) {
		cat, err := catalog.Parse(catalogJSON)
		if err != nil {
			t.Fatal(err)
		}
		s.Catalog = cat
	})
	return s, b
}

func cardsOf(t *testing.T, d *driver) map[string]map[string]any {
	t.Helper()
	data := d.page("mind")
	out := map[string]map[string]any{}
	for _, c := range data["cards"].([]any) {
		m := c.(map[string]any)
		out[m["name"].(string)] = m
	}
	return out
}

func TestA4GBLaptopSeesThe26BRecommendedWithExpertsInRAM(t *testing.T) {
	s, _ := realCatalogSetup(t, laptop4GB)
	d := serve(t, s)
	defer d.stop()
	cards := cardsOf(t, d)
	g := cards["gemma-4-26b-a4b-iq3s"]
	if g["recommended"] != true || g["locked"] != false {
		t.Fatalf("26B should be the recommended: %v", g)
	}
	if !strings.Contains(g["shape"].(string), "experts in system RAM") {
		t.Fatalf("shape in words: %v", g["shape"])
	}
	q := cards["swift-qwen3.8-27b-iq3xs"]
	if q["locked"] != true || !strings.Contains(q["reason"].(string), "needs") {
		t.Fatalf("27B should be locked with the fit's reason: %v", q)
	}
	var recommended int
	for _, c := range cards {
		if c["recommended"] == true {
			recommended++
		}
	}
	if recommended != 1 {
		t.Fatalf("exactly one recommended, got %d", recommended)
	}
	if msg := d.check("mind", map[string]any{"mind_kind": "local", "model": "swift-qwen3.8-27b-iq3xs"}); !strings.Contains(msg, "cannot run here") {
		t.Fatalf("a locked card must not be selectable, got %q", msg)
	}
	if msg := d.check("mind", map[string]any{"mind_kind": "local", "model": "gemma-4-26b-a4b-iq3s"}); msg != "" {
		t.Fatal(msg)
	}
}

func TestAMachineWithNoGPUAnd8GBSeesOnlyThe4BOnTheProcessor(t *testing.T) {
	s, _ := realCatalogSetup(t, cpuOnly8GB)
	d := serve(t, s)
	defer d.stop()
	cards := cardsOf(t, d)
	var open []string
	for n, c := range cards {
		if c["locked"] == false {
			open = append(open, n)
		}
	}
	if len(open) != 1 || open[0] != "qwen3.5-4b-iq4xs" {
		t.Fatalf("only the 4B should be open, got %v", open)
	}
	if !strings.Contains(cards["qwen3.5-4b-iq4xs"]["shape"].(string), "on the processor") {
		t.Fatalf("shape: %v", cards["qwen3.5-4b-iq4xs"]["shape"])
	}
	m := d.page("machine")
	if !strings.Contains(fmt.Sprint(m["rows"]), "none found") {
		t.Fatalf("the machine page should say no graphics card: %v", m["rows"])
	}
}

func TestAModelAlreadyOnTheMachineIsSaidSo(t *testing.T) {
	b := newBox(t)
	outside := filepath.Join(b.home, "elsewhere")
	os.MkdirAll(outside, 0o755)
	os.WriteFile(filepath.Join(outside, "whatever.bin"), b.model, 0o644)
	s := b.setup(cpuOnly8GB, func(s *Setup) { s.ModelRoots = []string{outside} })
	d := serve(t, s)
	defer d.stop()
	if cards := cardsOf(t, d); cards["tiny"]["already"] != true {
		t.Fatalf("Find by sha256 should have matched: %v", cards["tiny"])
	}
}

func TestMindPageTakesAServerOnlyAfterOneCallAnswers(t *testing.T) {
	b := newBox(t)
	d := serve(t, b.setup(cpuOnly8GB, nil))
	defer d.stop()
	if msg := d.check("mind", map[string]any{"mind_kind": "url", "mind_url": "http://127.0.0.1:1/v1"}); !strings.Contains(msg, "Nothing answered") {
		t.Fatalf("a dead address must be refused, got %q", msg)
	}
	if msg := d.check("mind", map[string]any{"mind_kind": "url", "mind_url": "not a url"}); msg == "" {
		t.Fatal("a non-URL must be refused")
	}
	if msg := d.check("mind", map[string]any{"mind_kind": "url", "mind_url": b.srv.URL + "/v1", "mind_model": "m"}); msg != "" {
		t.Fatalf("a live server must pass: %s", msg)
	}
}

func TestTheClaudeKeyIsNeverKeptInTheAnswers(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, nil)
	d := serve(t, s)
	defer d.stop()
	if msg := d.check("mind", map[string]any{"mind_kind": "claude"}); msg == "" {
		t.Fatal("no key and none saved must be refused")
	}
	if msg := d.check("mind", map[string]any{"mind_kind": "claude", "claude_key": "sk-secret-123"}); msg != "" {
		t.Fatal(msg)
	}
	for _, id := range []string{"mind", "watch", "ready"} {
		raw, _ := json.Marshal(d.page(id))
		if strings.Contains(string(raw), "sk-secret-123") {
			t.Fatalf("the key came back on the %s page", id)
		}
	}
}

func TestTheHiveIsOfferedOnlyWithACourt(t *testing.T) {
	b := newBox(t)
	s := b.setup(cpuOnly8GB, nil)
	d := serve(t, s)
	h := d.page("mind")["hive"].(map[string]any)
	d.stop()
	if h["available"] != false {
		t.Fatal("no Hive, no offer")
	}
	s = b.setup(cpuOnly8GB, func(s *Setup) { s.Hive = Hive{Here: true, Court: "http://court.invalid:1"} })
	d = serve(t, s)
	defer d.stop()
	h = d.page("mind")["hive"].(map[string]any)
	if h["available"] != true || h["court"] != "http://court.invalid:1" {
		t.Fatalf("a Hive with a court is offered: %v", h)
	}
}

func TestDetectHiveReadsTheEnvironmentOrTheCourtFile(t *testing.T) {
	home := t.TempDir()
	none := func(string) (string, error) { return "", os.ErrNotExist }
	if h := DetectHive(home, func(string) string { return "" }, none); h.Here || h.Court != "" {
		t.Fatalf("nothing here: %+v", h)
	}
	if h := DetectHive(home, func(k string) string {
		if k == "HIVE_COURT" {
			return " http://c:1 "
		}
		return ""
	}, none); h.Court != "http://c:1" {
		t.Fatalf("env: %+v", h)
	}
	os.MkdirAll(filepath.Join(home, ".hive"), 0o755)
	os.WriteFile(filepath.Join(home, ".hive", "court.url"), []byte("http://file:2\n"), 0o644)
	if h := DetectHive(home, func(string) string { return "" }, none); !h.Here || h.Court != "http://file:2" {
		t.Fatalf("file: %+v", h)
	}
}

func TestWatchPageListsFailedFirstAndNeedsAChoice(t *testing.T) {
	b := newBox(t)
	b.units = rank(ParseSystemctl("nginx.service loaded active running web\nbroken.service loaded failed failed oops\nidle.service loaded inactive dead idle\ndbee.service loaded active running me\n"))
	d := serve(t, b.setup(cpuOnly8GB, nil))
	defer d.stop()
	d.check("mind", map[string]any{"mind_kind": "local", "model": "tiny"})
	us := d.page("watch")["units"].([]any)
	if len(us) != 3 || us[0].(map[string]any)["name"] != "broken" || us[1].(map[string]any)["name"] != "nginx" {
		t.Fatalf("failed, then running, DBee's own left out: %v", us)
	}
	if msg := d.check("watch", map[string]any{"watch": []string{}, "whole_machine": false}); msg == "" {
		t.Fatal("watching nothing must be refused")
	}
	if msg := d.check("watch", map[string]any{"watch": []string{"nginx"}, "health": "nonsense"}); msg == "" {
		t.Fatal("a bad health URL must be refused")
	}
	if msg := d.check("watch", map[string]any{"watch": []string{"nginx"}, "health": "http://127.0.0.1:8080/"}); msg != "" {
		t.Fatal(msg)
	}
	if msg := d.check("watch", map[string]any{"whole_machine": true, "watch": []string{}}); msg != "" {
		t.Fatal(msg)
	}
}

func TestReadyPageRefusesWhatTheDiskCannotHold(t *testing.T) {
	b := newBox(t)
	p := cpuOnly8GB
	p.DiskFree = 1 << 20
	d := serve(t, b.setup(p, nil))
	defer d.stop()
	d.check("mind", map[string]any{"mind_kind": "local", "model": "tiny"})
	d.check("watch", map[string]any{"whole_machine": true})
	if msg := d.check("ready", map[string]any{}); !strings.Contains(msg, "disk has") {
		t.Fatalf("got %q", msg)
	}
}

func TestPagesAreTheSixTheSpecNames(t *testing.T) {
	s, _ := realCatalogSetup(t, laptop4GB)
	var ids []string
	for _, p := range s.Pages() {
		ids = append(ids, p.ID)
	}
	if got := strings.Join(ids, ","); got != "welcome,machine,mind,watch,ready,done" {
		t.Fatal(got)
	}
	if !strings.Contains(s.Pages()[0].HTML, "data:image/png;base64,") {
		t.Fatal("the welcome page carries the banner")
	}
	if s.Info().Accent != "#38a8ff" {
		t.Fatal("accent")
	}
}

func TestThinkingModelsGetEffort(t *testing.T) {
	s, _ := realCatalogSetup(t, laptop4GB)
	v, _ := s.verdict("swift-qwen3.8-27b-iq3xs")
	cfg := s.config(choice{Kind: KindLocal, Entry: v.Entry, Whole: true}, 9000)
	if !strings.Contains(cfg.TOML(), `effort = { diagnose = "medium", treat = "medium", triage = "low" }`) {
		t.Fatalf("effort missing:\n%s", cfg.TOML())
	}
	v, _ = s.verdict("qwen3.5-4b-iq4xs")
	if strings.Contains(s.config(choice{Kind: KindLocal, Entry: v.Entry, Whole: true}, 9000).TOML(), "effort") {
		t.Fatal("a plain model has no effort")
	}
}

func TestParsersReadEachPlatformsListing(t *testing.T) {
	mac := ParseLaunchctl("PID\tStatus\tLabel\n123\t0\tcom.a.run\n-\t78\tcom.b.dead\n-\t0\tcom.c.idle\n", []string{"com.c.idle", "com.d.off"})
	got := map[string]string{}
	for _, u := range mac {
		got[u.Name] = u.State
	}
	want := map[string]string{"com.a.run": "running", "com.b.dead": "failed", "com.c.idle": "stopped", "com.d.off": "stopped"}
	if fmt.Sprint(got) != fmt.Sprint(want) {
		t.Fatalf("launchctl: %v", got)
	}
	arr := ParseGetService([]byte(`[{"Name":"Spooler","DisplayName":"Print Spooler","Status":4},{"Name":"Foo","DisplayName":"Foo","Status":1}]`))
	one := ParseGetService([]byte(`{"Name":"Solo","DisplayName":"Solo","Status":"Running"}`))
	if len(arr) != 2 || arr[0].State != "running" || arr[1].State != "stopped" || len(one) != 1 || one[0].State != "running" {
		t.Fatalf("get-service: %v %v", arr, one)
	}
	l := ExecLister{GOOS: "windows", Run: func(ctx context.Context, name string, args ...string) ([]byte, error) {
		if name != "powershell" {
			t.Fatalf("windows lists with powershell, not %s", name)
		}
		return []byte(`{"Name":"Solo","DisplayName":"Solo","Status":4}`), nil
	}}
	if us, err := l.List(context.Background()); err != nil || len(us) != 1 {
		t.Fatal(us, err)
	}
}
