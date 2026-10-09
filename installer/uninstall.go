package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// Uninstall stops and removes both services and the install root. A model
// file that lives outside the root (a Hive's, or one the person kept) is never
// touched, and neither is the Claude key file. The root is only removed when
// it looks like a DBee install, so a mistyped --root cannot take a home folder.
func (s *Setup) Uninstall(ctx context.Context, out io.Writer) error {
	root := filepath.Clean(s.Root)
	if root == "" || root == "." || root == string(filepath.Separator) || root == filepath.Clean(s.Home) || filepath.Dir(root) == root {
		return fmt.Errorf("refusing to remove %q: that is not a DBee folder", s.Root)
	}
	m := s.manager()
	var errs []error
	for _, n := range []string{DBeeService, MindService} {
		if err := m.Stop(ctx, n); err != nil {
			fmt.Fprintf(out, "note: stopping %s: %v\n", n, err)
		}
		if err := m.Uninstall(ctx, n); err != nil {
			errs = append(errs, fmt.Errorf("removing service %s: %w", n, err))
			continue
		}
		fmt.Fprintf(out, "removed service %s\n", n)
	}
	if _, err := os.Stat(root); err == nil {
		if !exists(filepath.Join(root, "dbee.toml")) && !exists(filepath.Join(root, "state.json")) && !exists(filepath.Join(root, "app", "dbee")) {
			errs = append(errs, fmt.Errorf("%s does not look like a DBee folder (no dbee.toml, state.json or app); left alone", root))
		} else if err := os.RemoveAll(root); err != nil {
			errs = append(errs, err)
		} else {
			fmt.Fprintf(out, "removed %s\n", root)
		}
	}
	if HasSecret(s.Home, "ANTHROPIC_API_KEY") {
		fmt.Fprintf(out, "kept %s (it holds a key; delete it yourself if you want it gone)\n", SecretsPath(s.Home))
	}
	return errors.Join(errs...)
}
