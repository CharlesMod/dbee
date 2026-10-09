package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
)

// Unit is one service found on this machine.
type Unit struct {
	Name  string `json:"name"`
	State string `json:"state"` // failed, running, stopped
	About string `json:"about,omitempty"`
}

// UnitLister lists the services of this machine. Tests fake it.
type UnitLister interface {
	List(ctx context.Context) ([]Unit, error)
}

// Runner runs one command and returns its output.
type Runner func(ctx context.Context, name string, args ...string) ([]byte, error)

// ExecLister lists the real machine's services with the platform's own tool.
type ExecLister struct {
	GOOS string
	Run  Runner
	// LaunchDaemons is where macOS keeps system job files (default /Library/LaunchDaemons).
	LaunchDaemons string
}

// List implements UnitLister.
func (l ExecLister) List(ctx context.Context) ([]Unit, error) {
	switch l.GOOS {
	case "linux":
		out, err := l.Run(ctx, "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain", "--no-legend")
		if err != nil {
			return nil, fmt.Errorf("systemctl: %w", err)
		}
		return rank(ParseSystemctl(string(out))), nil
	case "darwin":
		out, err := l.Run(ctx, "launchctl", "list")
		if err != nil {
			return nil, fmt.Errorf("launchctl: %w", err)
		}
		dir := l.LaunchDaemons
		if dir == "" {
			dir = "/Library/LaunchDaemons"
		}
		var labels []string
		ents, _ := os.ReadDir(dir)
		for _, e := range ents {
			if n, ok := strings.CutSuffix(e.Name(), ".plist"); ok {
				labels = append(labels, n)
			}
		}
		return rank(ParseLaunchctl(string(out), labels)), nil
	case "windows":
		out, err := l.Run(ctx, "powershell", "-NoProfile", "-NonInteractive", "-Command",
			"Get-Service | Select-Object Name,DisplayName,Status | ConvertTo-Json -Compress")
		if err != nil {
			return nil, fmt.Errorf("powershell: %w", err)
		}
		return rank(ParseGetService(out)), nil
	}
	return nil, fmt.Errorf("no way to list services on %q", l.GOOS)
}

// ParseSystemctl reads `systemctl list-units --type=service --all --plain
// --no-legend`: UNIT LOAD ACTIVE SUB DESCRIPTION. Units that are not loaded
// (stale references) are left out.
func ParseSystemctl(out string) []Unit {
	var us []Unit
	for _, line := range strings.Split(out, "\n") {
		f := strings.Fields(strings.TrimLeft(line, "●* \t"))
		if len(f) < 4 || !strings.HasSuffix(f[0], ".service") || f[1] != "loaded" {
			continue
		}
		u := Unit{Name: strings.TrimSuffix(f[0], ".service"), About: strings.Join(f[4:], " ")}
		switch {
		case f[2] == "failed":
			u.State = "failed"
		case f[2] == "active" && f[3] == "running":
			u.State = "running"
		default:
			u.State = "stopped"
		}
		us = append(us, u)
	}
	return us
}

// ParseLaunchctl reads `launchctl list` (PID, last exit status, label) and
// adds the labels of system job files that are not loaded as stopped.
func ParseLaunchctl(out string, plistLabels []string) []Unit {
	var us []Unit
	seen := map[string]bool{}
	for _, line := range strings.Split(out, "\n") {
		f := strings.Fields(line)
		if len(f) != 3 || f[0] == "PID" {
			continue
		}
		u := Unit{Name: f[2]}
		switch {
		case f[0] != "-":
			u.State = "running"
		case f[1] != "0":
			u.State, u.About = "failed", "last exit "+f[1]
		default:
			u.State = "stopped"
		}
		seen[u.Name] = true
		us = append(us, u)
	}
	for _, l := range plistLabels {
		if !seen[l] {
			us = append(us, Unit{Name: l, State: "stopped"})
		}
	}
	return us
}

// ParseGetService reads `Get-Service | ConvertTo-Json`: one object or an
// array; Status is a number (PowerShell 5) or a word (7).
func ParseGetService(out []byte) []Unit {
	type svc struct {
		Name        string
		DisplayName string
		Status      any
	}
	var many []svc
	if err := json.Unmarshal(out, &many); err != nil {
		var one svc
		if json.Unmarshal(out, &one) != nil {
			return nil
		}
		many = []svc{one}
	}
	var us []Unit
	for _, s := range many {
		if s.Name == "" {
			continue
		}
		st := "stopped"
		switch v := s.Status.(type) {
		case float64:
			if int(v) == 4 {
				st = "running"
			}
		case string:
			if strings.EqualFold(v, "running") {
				st = "running"
			}
		}
		us = append(us, Unit{Name: s.Name, State: st, About: s.DisplayName})
	}
	return us
}

// rank puts failed first, then running, then the rest, each by name, and
// leaves DBee's own two services out.
func rank(us []Unit) []Unit {
	order := map[string]int{"failed": 0, "running": 1, "stopped": 2}
	out := us[:0:0]
	for _, u := range us {
		if u.Name == MindService || u.Name == DBeeService || strings.HasPrefix(u.Name, "wasp."+MindService) || strings.HasPrefix(u.Name, "wasp."+DBeeService) {
			continue
		}
		out = append(out, u)
	}
	sort.SliceStable(out, func(i, j int) bool {
		if order[out[i].State] != order[out[j].State] {
			return order[out[i].State] < order[out[j].State]
		}
		return strings.ToLower(out[i].Name) < strings.ToLower(out[j].Name)
	})
	return out
}

// execEnv runs a command with extra environment variables.
func execEnv(ctx context.Context, env []string, name string, args ...string) ([]byte, error) {
	c := exec.CommandContext(ctx, name, args...)
	c.Env = append(os.Environ(), env...)
	return c.CombinedOutput()
}
