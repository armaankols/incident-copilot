"""Durable atomic admission on one machine/shared local SQLite filesystem.

Unsettled reservations never expire automatically: crashes retain the full hold.
This is an application guardrail, not a provider billing cap.
"""
import math
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


class AdmissionDenied(Exception):
    pass


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, day TEXT, visitor TEXT, started REAL, reserved REAL, charged REAL, active INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS replays (id TEXT PRIMARY KEY, payload TEXT)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def day():
        return datetime.now(timezone.utc).date().isoformat()

    def reserve(self, amount, daily_cap, visitor, hourly_limit=8, concurrency=2):
        if not math.isfinite(amount) or amount <= 0 or not math.isfinite(daily_cap) or daily_cap < 0:
            raise ValueError("Invalid budget")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(charged),0) FROM runs WHERE day=?", (self.day(),)).fetchone()[0]
            holds = db.execute("SELECT COALESCE(SUM(reserved),0), COALESCE(SUM(active),0) FROM runs WHERE active=1").fetchone()
            if spent + holds[0] + amount > daily_cap + 1e-12:
                raise AdmissionDenied("Daily budget has insufficient unreserved funds")
            if holds[1] >= concurrency:
                raise AdmissionDenied("Investigation capacity reached")
            hits = db.execute("SELECT COUNT(*) FROM runs WHERE visitor=? AND started>?", (visitor, time.time()-3600)).fetchone()[0]
            if hits >= hourly_limit:
                raise AdmissionDenied("Visitor hourly rate limit reached")
            rid = uuid.uuid4().hex
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,0,1)", (rid, self.day(), visitor, time.time(), amount))
            return rid

    def settle(self, rid, charged, uncertain=False):
        if not math.isfinite(charged) or charged < 0:
            raise ValueError("Invalid charge")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved, active FROM runs WHERE id=?", (rid,)).fetchone()
            if row is None:
                raise ValueError("Unknown reservation")
            if row[1]:
                db.execute("UPDATE runs SET charged=?, active=0 WHERE id=?", (max(charged, row[0]) if uncertain else charged, rid))

    def spent(self):
        with self.connect() as db:
            return db.execute("SELECT COALESCE(SUM(charged),0) FROM runs WHERE day=?", (self.day(),)).fetchone()[0]

    def save_replay(self, rid, payload):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO replays VALUES (?,?)", (rid, payload))

    def replay(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM replays WHERE id=?", (rid,)).fetchone()
            return row[0] if row else None
