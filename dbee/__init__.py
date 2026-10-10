"""DBee, the doctor bee. Its loop is Wasp's (waspdoctor): installed, staged beside
this package by DBee Setup, or found in a Wasp checkout (WASP_DIR, or a `wasp`
beside this repo or in the home directory) when run from a DBee checkout."""
import os as _os
import sys as _sys
from pathlib import Path as _Path

PROBES = _Path(__file__).resolve().parents[1] / "assets" / "probes.jsonl"   # the Hive's probes, as first looks

try:
    import waspdoctor as _wd  # noqa: F401
except ImportError:
    for _d in (_os.environ.get("WASP_DIR", ""), _Path(__file__).resolve().parents[2] / "wasp", _Path.home() / "wasp"):
        if _d and (_Path(_d) / "doctor" / "waspdoctor" / "__init__.py").is_file():
            _sys.path.insert(0, str(_Path(_d) / "doctor"))
            break
