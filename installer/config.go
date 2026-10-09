package main

import (
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// Service names Setup installs.
const (
	MindService = "dbee-mind"
	DBeeService = "dbee"
)

// DefaultRoot is where DBee goes on each platform.
func DefaultRoot(goos, home string, env func(string) string) string {
	switch goos {
	case "windows":
		base := env("LOCALAPPDATA")
		if base == "" {
			base = filepath.Join(home, "AppData", "Local")
		}
		return filepath.Join(base, "DBee")
	case "darwin":
		return filepath.Join(home, "Library", "Application Support", "DBee")
	}
	base := env("XDG_DATA_HOME")
	if base == "" {
		base = filepath.Join(home, ".local", "share")
	}
	return filepath.Join(base, "dbee")
}

func tomlStr(s string) string {
	r := strings.NewReplacer(`\`, `\\`, `"`, `\"`, "\n", `\n`, "\r", `\r`, "\t", `\t`)
	return `"` + r.Replace(s) + `"`
}

// Config is what dbee.toml says.
type Config struct {
	Spec    string
	Court   string
	Effort  map[string]string // phase -> effort, thinking models only
	Watches []Watch
	Home    string
}

// Watch is one [[watch]] table.
type Watch struct{ Service, Health string }

// TOML renders dbee.toml in the shape dbee/config.py reads.
func (c Config) TOML() string {
	var b strings.Builder
	b.WriteString("# dbee.toml: how DBee runs on this machine. Written by DBee Setup; edit freely.\n\n[mind]\n")
	b.WriteString("# where its thoughts go: the ride-along server, a hive model, claude:..., or any OpenAI-compatible URL\n")
	b.WriteString("spec = " + tomlStr(c.Spec) + "\nmax_tokens = 1024\n")
	if len(c.Effort) > 0 {
		keys := make([]string, 0, len(c.Effort))
		for k := range c.Effort {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var parts []string
		for _, k := range keys {
			parts = append(parts, k+" = "+tomlStr(c.Effort[k]))
		}
		b.WriteString("# thinking model: light while looking, careful when deciding\n")
		b.WriteString("effort = { " + strings.Join(parts, ", ") + " }\n")
	}
	if c.Court != "" {
		b.WriteString("# the Hive's router; the launcher and the service export it as DBEE_COURT\n")
		b.WriteString("court = " + tomlStr(c.Court) + "\n")
	}
	b.WriteString("\n# one table per service; with none, DBee watches the whole machine\n")
	for _, w := range c.Watches {
		b.WriteString("[[watch]]\n")
		if w.Service != "" {
			b.WriteString("service = " + tomlStr(w.Service) + "\n")
		}
		if w.Health != "" {
			b.WriteString("health = " + tomlStr(w.Health) + "\n")
		}
		b.WriteString("\n")
	}
	b.WriteString("[doctor]\nhome = " + tomlStr(c.Home) + "\n")
	return b.String()
}

func shQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }

// Launcher is <root>/bin/dbee (dbee.cmd on Windows): it runs DBee with the
// private Python and exports the court when a Hive's router is the mind. Its
// output is unbuffered: under a service it goes to a log file, which Python
// would otherwise fill only in blocks, leaving the log empty while DBee sleeps.
func Launcher(goos, app, python, court string) (name, body string) {
	if goos == "windows" {
		var b strings.Builder
		b.WriteString("@echo off\r\n")
		b.WriteString("set \"PYTHONPATH=" + app + "\"\r\n")
		b.WriteString("set \"PYTHONUNBUFFERED=1\"\r\n")
		if court != "" {
			b.WriteString("set \"DBEE_COURT=" + court + "\"\r\n")
		}
		b.WriteString("\"" + python + "\" -m dbee %*\r\n")
		return "dbee.cmd", b.String()
	}
	var b strings.Builder
	b.WriteString("#!/bin/sh\n")
	b.WriteString("PYTHONPATH=" + shQuote(app) + "${PYTHONPATH:+:$PYTHONPATH}\nexport PYTHONPATH\nPYTHONUNBUFFERED=1\nexport PYTHONUNBUFFERED\n")
	if court != "" {
		b.WriteString("DBEE_COURT=" + shQuote(court) + "\nexport DBEE_COURT\n")
	}
	b.WriteString("exec " + shQuote(python) + " -m dbee \"$@\"\n")
	return "dbee", b.String()
}

// SecretsPath is where DBee's mind code reads the Claude key.
func SecretsPath(home string) string {
	return filepath.Join(home, ".config", "dbee", "secrets.env")
}

// WriteSecret sets name=value in the secrets file (mode 600), keeping other
// lines. The value is never returned, echoed or logged.
func WriteSecret(home, name, value string) error {
	p := SecretsPath(home)
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		return err
	}
	var keep []string
	if b, err := os.ReadFile(p); err == nil {
		for _, l := range strings.Split(strings.TrimRight(string(b), "\n"), "\n") {
			if l != "" && !strings.HasPrefix(strings.TrimSpace(l), name+"=") {
				keep = append(keep, l)
			}
		}
	}
	keep = append(keep, name+"="+value)
	tmp := p + ".tmp"
	if err := os.WriteFile(tmp, []byte(strings.Join(keep, "\n")+"\n"), 0o600); err != nil {
		return err
	}
	if err := os.Chmod(tmp, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, p)
}

// HasSecret reports whether the secrets file already holds name.
func HasSecret(home, name string) bool {
	b, err := os.ReadFile(SecretsPath(home))
	if err != nil {
		return false
	}
	for _, l := range strings.Split(string(b), "\n") {
		k, v, _ := strings.Cut(strings.TrimSpace(l), "=")
		if k == name && strings.TrimSpace(v) != "" {
			return true
		}
	}
	return false
}

func itoa(n int) string { return strconv.Itoa(n) }
