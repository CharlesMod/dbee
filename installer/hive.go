package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Hive is what Setup knows of a Hive on this machine. DBee needs none; with
// one, its models are reused and its router is offered as the mind.
type Hive struct {
	Here  bool   // a hive on PATH, or ~/.hive exists
	Court string // the router's address, when the Hive says it
	Dir   string // ~/.hive when present
}

// DetectHive looks at the environment and the home directory only.
func DetectHive(home string, env func(string) string, lookPath func(string) (string, error)) Hive {
	var h Hive
	dir := filepath.Join(home, ".hive")
	if fi, err := os.Stat(dir); err == nil && fi.IsDir() {
		h.Here, h.Dir = true, dir
	}
	if _, err := lookPath("hive"); err == nil {
		h.Here = true
	}
	h.Court = strings.TrimSpace(env("HIVE_COURT"))
	if h.Court == "" {
		if b, err := os.ReadFile(filepath.Join(dir, "court.url")); err == nil {
			h.Court = strings.TrimSpace(string(b))
		}
	}
	return h
}

func defaultLookPath(name string) (string, error) { return exec.LookPath(name) }
