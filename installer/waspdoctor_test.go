package main

import (
	"os"
	"path/filepath"
	"testing"
	"testing/fstest"
)

func TestTheDoctorsLoopIsLaidFromWasp(t *testing.T) {
	dest := filepath.Join(t.TempDir(), "app")
	src := fstest.MapFS{"dbee/__init__.py": {Data: []byte("")}, "dbee/__pycache__/x.pyc": {Data: []byte("x")}}
	if _, err := copyPayload(src, dest); err != nil {
		t.Fatal(err)
	}
	for _, f := range []string{"dbee/__init__.py", "waspdoctor/__init__.py", "waspdoctor/doctor.py", "waspdoctor/protocol.py"} {
		if _, err := os.Stat(filepath.Join(dest, f)); err != nil {
			t.Errorf("%s not laid: %v", f, err)
		}
	}
	if _, err := os.Stat(filepath.Join(dest, "dbee/__pycache__")); err == nil {
		t.Error("bytecode laid")
	}
}
