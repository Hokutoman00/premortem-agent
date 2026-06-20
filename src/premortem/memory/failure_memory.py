"""FailureMemory — append-only store of past failures that seeds future pre-mortems.

This is the v8 displacement (AMPLIFY): the engine's failure-mode enumeration is not
purely model-imagined; it is seeded by *what actually went wrong before*. Every block,
human override, and post-hoc-discovered miss is appended here (invariant I4), and the
next enumeration for a similar action pulls those modes back in as exogenous seed.

Append-only by construction: there is no UPDATE/DELETE path. Learning is monotone.
Backed by SQLite so it survives restarts and is inspectable with any sqlite client.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterable

from ..types import FailureMode, FailureOutcome, Severity

_SCHEMA = """
CREATE TABLE IF NOT EXISTS failures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    action_fp   TEXT    NOT NULL,
    failure_mode TEXT   NOT NULL,
    evidence    TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    source      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failures_fp ON failures(action_fp);
CREATE INDEX IF NOT EXISTS idx_failures_mode ON failures(failure_mode);
"""


class FailureMemory:
    def __init__(self, db_path: str = ":memory:"):
        # check_same_thread=False: the FastAPI app holds one process-global FailureMemory,
        # but uvicorn runs sync endpoints in a threadpool, so the connection is touched from
        # worker threads. A single lock serialises every write/read so the append-only store
        # stays consistent under that concurrency (and the same path the TestClient exercises).
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- write (append-only) -------------------------------------------
    def append(self, outcome: FailureOutcome) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO failures (ts, action_fp, failure_mode, evidence, label, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), outcome.action_fp, outcome.failure_mode,
                 outcome.evidence, outcome.label, outcome.source),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    # --- read (seed lookup) --------------------------------------------
    def seed_modes_for(self, action_fp: str, vendor_id: str | None = None) -> list[FailureMode]:
        """Return failure modes seen before for this action or vendor, as seed.

        Matches on exact action fingerprint OR on the vendor prefix (so a fraud against
        a vendor at $48k still seeds a $5k payment to the same vendor)."""
        prefix = (vendor_id + ":") if vendor_id else action_fp.split(":")[0] + ":"
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT failure_mode, evidence FROM failures"
                " WHERE action_fp = ? OR action_fp LIKE ?"
                " ORDER BY failure_mode",
                (action_fp, prefix + "%"),
            ).fetchall()
        modes: list[FailureMode] = []
        seen: set[str] = set()
        for r in rows:
            mid = r["failure_mode"]
            if mid in seen:
                continue
            seen.add(mid)
            modes.append(FailureMode(
                # A remembered mode reuses its own id as the probe name by convention; the
                # engine's _wire_memory_probes() rewires it to the canonical registry probe
                # when one exists, and leaves it unprobeable -> ESCALATE (I5) when none does.
                id=mid,
                desc=f"過去に発生: {r['evidence']}",
                probe=mid,
                severity=Severity.HIGH,
                seed_source="memory",
            ))
        return modes

    def all(self) -> Iterable[sqlite3.Row]:
        with self._lock:
            return self._conn.execute("SELECT * FROM failures ORDER BY id").fetchall()

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) AS c FROM failures").fetchone()["c"])

    def close(self) -> None:
        self._conn.close()
