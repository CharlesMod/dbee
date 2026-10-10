"""The Hive's court, for the doctor's triage of a Hive frame: the frame held while
it is mended (the fleet's work goes round it; work addressed to it by name, the
doctor's own looks and cures, still lands) and returned once it is. A hold is
undone by its return; both land on the court's spine with the case and why."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class Court:
    def __init__(self, url: str, frame: str, *, timeout: float = 10):
        self.url, self.frame, self.timeout = url.rstrip("/"), frame, timeout

    def word(self, verb: str, case: str, why: str) -> tuple[bool, str]:
        """POST /v1/drones/{frame}/{hold|return}: (taken, what the court said)."""
        req = urllib.request.Request(f"{self.url}/v1/drones/{self.frame}/{verb}", method="POST",
                                     data=json.dumps({"case": case, "why": why}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return True, r.read().decode(errors="replace")[:300]
        except urllib.error.HTTPError as e:
            return False, f"the court refused the {verb} ({e.code}): {e.read().decode(errors='replace')[:300]}"
        except OSError as e:
            return False, f"the court did not take the {verb}: {e}"
