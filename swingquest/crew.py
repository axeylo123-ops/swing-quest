"""The crew log: what each agent in the nightly pipeline did, for the
dashboard's Agents view. Every number here is real output from the run.

docs/data/agents.json      this run's pipeline agents (rewritten every run)
docs/data/reviews.json     reviewer agents' findings and proposals (edited by the review routine)
"""
import json
import time
from datetime import datetime, timezone

from swingquest.config import DATA_OUT_DIR

FILE = DATA_OUT_DIR / "agents.json"


class Crew:
    def __init__(self, mode: str):
        self.mode, self.agents = mode, []
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._t = time.monotonic()

    def done(self, id: str, name: str, job: str, stat: str, lines=(), status: str = "done") -> None:
        """One agent finished its step. stat = the headline; lines = up to 4 log lines."""
        now = time.monotonic()
        self.agents.append({"id": id, "name": name, "job": job, "stat": stat, "lines": [str(x) for x in lines][:4],
                            "status": status, "secs": round(now - self._t, 1)})
        self._t = now

    def write(self, as_of: str | None) -> None:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        out = {"started": self.started, "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "as_of": as_of, "mode": self.mode, "agents": self.agents}
        FILE.write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8", newline="\n")


def append(id: str, name: str, job: str, stat: str, lines=(), status: str = "done") -> None:
    """Adds a step that runs after the board is written (the record keeper)."""
    try:
        out = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    out["agents"] = [a for a in out["agents"] if a["id"] != id] + [
        {"id": id, "name": name, "job": job, "stat": stat, "lines": [str(x) for x in lines][:4], "status": status, "secs": None}]
    FILE.write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8", newline="\n")
