// dbee-setup installs DBee: a private Python, DBee itself, a model server and a
// model that fit this machine (or another mind of your choosing), a config,
// and two background services. It is built on Wasp's wizard.
//
//	dbee-setup                      the setup window
//	dbee-setup --no-window          serve the window's address only
//	dbee-setup --yes [--model NAME | --mind-url URL[#model] | --claude | --hive]
//	           [--watch svc,svc | --whole-machine] [--root DIR]
//	dbee-setup --uninstall [--purge] [--root DIR]
//
// Build: ./stage.sh && CGO_ENABLED=0 go build -o dbee-setup .
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/CharlesMod/wasp/catalog"
	"github.com/CharlesMod/wasp/engine"
	"github.com/CharlesMod/wasp/profile"
	"github.com/CharlesMod/wasp/service"
	"github.com/CharlesMod/wasp/wizard"
)

// Version is set at build time with -ldflags "-X main.Version=...".
var Version = "0.1.0"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr, os.Getenv, nil)
	stop()
	os.Exit(code)
}

// newSetup is Setup wired to this machine. tweak (tests) may replace any part.
func newSetup(root, dbeeSrc string, env func(string) string, tweak func(*Setup)) (*Setup, error) {
	home, _ := os.UserHomeDir()
	if root == "" {
		root = DefaultRoot(runtime.GOOS, home, env)
	}
	cat, err := catalog.Parse(catalogJSON)
	if err != nil {
		return nil, err
	}
	prof := profile.Detect()
	override := false
	for _, e := range profile.OverrideEnv {
		if env(e) != "" {
			override = true
		}
	}
	if !override {
		prof.DiskFree = profile.DiskFree(root)
	}
	s := &Setup{
		Root: root, Home: home, Profile: prof, Catalog: cat, Version: Version, Env: env,
		Hive:        DetectHive(home, env, defaultLookPath),
		Svc:         service.Default(),
		Lister:      ExecLister{GOOS: runtime.GOOS, Run: service.ExecRunner},
		Payload:     payloadFrom(dbeeSrc),
		EngineRoots: engine.DefaultRoots(),
		ModelRoots:  []string{filepath.Join(home, ".hive", "models"), filepath.Join(profile.InstallRoot(), "models")},
	}
	if tweak != nil {
		tweak(s)
	}
	return s, nil
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer, env func(string) string, tweak func(*Setup)) int {
	fs := flag.NewFlagSet("dbee-setup", flag.ContinueOnError)
	fs.SetOutput(stderr)
	yes := fs.Bool("yes", false, "install now with no window, with the recommended choices filled in")
	model := fs.String("model", "", "with --yes: a catalog model by name")
	mindURL := fs.String("mind-url", "", "with --yes: an OpenAI-compatible server you already run, URL[#model]")
	claude := fs.Bool("claude", false, "with --yes: Claude as the mind (the key is read from ANTHROPIC_API_KEY, or the saved one is kept)")
	hive := fs.Bool("hive", false, "with --yes: this Hive's minds")
	watch := fs.String("watch", "", "with --yes: services to watch, comma separated")
	whole := fs.Bool("whole-machine", false, "with --yes: watch the whole machine (the default)")
	root := fs.String("root", "", "the install folder")
	noWindow := fs.Bool("no-window", false, "serve the setup only; print its address")
	dbeeSrc := fs.String("dbee-src", "", "a DBee checkout (with dbee/ in it) to install instead of the copy in this binary")
	uninstall := fs.Bool("uninstall", false, "stop and remove DBee's services and folder (its cases are kept)")
	purge := fs.Bool("purge", false, "with --uninstall: remove the cases too")
	version := fs.Bool("version", false, "print the version")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *version {
		fmt.Fprintln(stdout, "dbee-setup", Version)
		return 0
	}
	s, err := newSetup(*root, *dbeeSrc, env, tweak)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	if *uninstall {
		s.Purge = *purge
		if err := s.Uninstall(ctx, stdout); err != nil {
			fmt.Fprintln(stderr, "uninstall:", err)
			return 1
		}
		return 0
	}
	opts := wizard.Options{Root: s.Root, Profile: &s.Profile, NoWindow: *noWindow, Stdout: stdout}
	if *yes {
		a, err := s.quietAnswers(*model, *mindURL, *claude, *hive, *watch, *whole)
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 2
		}
		opts.Answers = a
		if err := wizard.Run(ctx, s, opts); err != nil {
			fmt.Fprintf(stderr, "failed: %v\n", err)
			return 1
		}
		fmt.Fprintln(stdout, "DBee is installed in", s.Root)
		return 0
	}
	srv, err := wizard.New(s, opts)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	fmt.Fprintf(stdout, "setup is at %s\n", srv.URL())
	if !*noWindow {
		info := s.Info()
		if err := wizard.OpenWindow(srv.URL(), info.WindowW, info.WindowH); err != nil {
			fmt.Fprintf(stdout, "could not open a window (%v); open the address above in a browser\n", err)
		}
	}
	if err := srv.Serve(ctx); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

// quietAnswers are the answers --yes stands for: the flags, else the
// recommended mind and the whole machine.
func (s *Setup) quietAnswers(model, mindURL string, claude, hive bool, watch string, whole bool) (wizard.Answers, error) {
	a := wizard.Answers{}
	picks := 0
	for _, b := range []bool{model != "", mindURL != "", claude, hive} {
		if b {
			picks++
		}
	}
	if picks > 1 {
		return nil, errors.New("choose one of --model, --mind-url, --claude, --hive")
	}
	switch {
	case mindURL != "":
		a["mind_kind"], a["mind_url"] = KindURL, mindURL
	case claude:
		a["mind_kind"] = KindClaude
		if k := strings.TrimSpace(s.Env("ANTHROPIC_API_KEY")); k != "" {
			a["claude_key"] = k
		}
	case hive:
		a["mind_kind"] = KindHive
	default:
		a["mind_kind"] = KindLocal
		if model == "" {
			r := s.recommendation()
			if r.Pick < 0 {
				return nil, errors.New("no model in the catalog fits this machine; use --mind-url or --claude")
			}
			model = r.Verdicts[r.Pick].Entry.Name
		}
		a["model"] = model
	}
	if watch != "" && !whole {
		a["watch"] = strings.Split(watch, ",")
	} else {
		a["whole_machine"] = true
	}
	return a, nil
}
