package main

import (
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/CharlesMod/wasp/doctor"
)

//go:generate sh stage.sh

// payloadFS holds the DBee package staged by stage.sh: payload/dbee/ (the
// Python package) and payload/assets/ (what it reads at run time). A build
// made before staging holds only payload/.keep and still compiles.
//
//go:embed all:payload
var payloadFS embed.FS

// embeddedPayload is the staged copy inside this binary, rooted at dbee/.
func embeddedPayload() fs.FS {
	sub, err := fs.Sub(payloadFS, "payload")
	if err != nil {
		return emptyFS{}
	}
	return sub
}

type emptyFS struct{}

func (emptyFS) Open(string) (fs.File, error) { return nil, fs.ErrNotExist }

// payloadFrom is the payload a run installs: a DBee checkout named by
// --dbee-src (a directory holding dbee/ and, optionally, assets/), else the
// copy in the binary.
func payloadFrom(srcDir string) fs.FS {
	if srcDir != "" {
		return os.DirFS(srcDir)
	}
	return embeddedPayload()
}

// copyPayload lays dbee/ and assets/ from src, and Wasp's waspdoctor/, under dest, without bytecode
// caches. A payload with no dbee/__init__.py is refused with what to do.
func copyPayload(src fs.FS, dest string) (files int, err error) {
	if _, err := fs.Stat(src, "dbee/__init__.py"); err != nil {
		return 0, errors.New("this build carries no DBee package: run stage.sh and rebuild, or pass --dbee-src DIR")
	}
	if err := os.RemoveAll(dest); err != nil {
		return 0, err
	}
	for _, top := range []string{"dbee", "assets"} {
		n, err := layTree(src, top, dest)
		files += n
		if err != nil {
			return files, err
		}
	}
	// the doctor's loop is Wasp's: the version this build's go.mod pins
	n, err := layTree(doctor.Python, "waspdoctor", dest)
	return files + n, err
}

// layTree copies top (a directory of src) under dest, without bytecode caches;
// a top src does not hold is skipped.
func layTree(src fs.FS, top, dest string) (files int, err error) {
	if _, err := fs.Stat(src, top); err != nil {
		return 0, nil
	}
	err = fs.WalkDir(src, top, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() && d.Name() == "__pycache__" {
			return fs.SkipDir
		}
		out := filepath.Join(dest, filepath.FromSlash(p))
		if d.IsDir() {
			return os.MkdirAll(out, 0o755)
		}
		if strings.HasSuffix(p, ".pyc") || !d.Type().IsRegular() {
			return nil
		}
		b, err := fs.ReadFile(src, p)
		if err != nil {
			return err
		}
		mode := os.FileMode(0o644)
		if path.Ext(p) == ".sh" {
			mode = 0o755
		}
		if err := os.WriteFile(out, b, mode); err != nil {
			return err
		}
		files++
		return nil
	})
	if err != nil {
		return files, fmt.Errorf("copying %s: %w", top, err)
	}
	return files, nil
}
