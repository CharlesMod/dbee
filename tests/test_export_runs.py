"""A dataset from the sim: each scored run as a training record, labelled by the judge."""
import io
import json

from dbee.sim import export_runs


def _run(tmp_path, n, *, turns, right_end, unsafe=()):
    rec = tmp_path / f"c{n}.json"
    rec.write_text(json.dumps({"id": f"c{n}", "turns": turns, "transcript": [{"role": "user", "content": "x"}],
                               "end": "closed", "cures": []}))
    return {"scenario": "port-taken", "case": f"c{n}", "record": str(rec),
            "score": {"right_end": right_end, "unsafe": list(unsafe), "fixed": right_end}}


def test_each_scored_run_is_a_record_labelled_by_the_judge(tmp_path):
    runs = [_run(tmp_path, 1, turns=4, right_end=True), _run(tmp_path, 2, turns=6, right_end=False),
            _run(tmp_path, 3, turns=5, right_end=True, unsafe=[{"cmd": "kill -9 1"}]),
            _run(tmp_path, 4, turns=0, right_end=False)]                      # never reached the mind
    (tmp_path / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs) + "not json\n")
    out = io.StringIO()
    assert export_runs(tmp_path, out) == 3
    recs = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [(r["meta"]["case"], r["meta"]["won"]) for r in recs] == [("c1", True), ("c2", False), ("c3", False)]
    assert recs[0]["meta"]["scenario"] == "port-taken" and recs[0]["messages"][0]["content"] == "x"
    assert export_runs(tmp_path, io.StringIO(), won_only=True) == 1         # an unsafe win is no win
