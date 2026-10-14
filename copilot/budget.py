"""Durable atomic admission on one machine/shared local SQLite filesystem.

Unsettled reservations never expire automatically: crashes retain the full hold.
This is an application guardrail, not a provider billing cap.
"""
import math
import sqlite3
import time
import uuid
from datetime import datetime, time as midnight, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BUDGET_TIMEZONE = "America/Los_Angeles"
PACIFIC = ZoneInfo(BUDGET_TIMEZONE)


class AdmissionDenied(Exception):
    pass


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, day TEXT, visitor TEXT, started REAL, reserved REAL, charged REAL, active INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS replays (id TEXT PRIMARY KEY, payload TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS request_limits (bucket TEXT, window INTEGER, hits INTEGER, PRIMARY KEY (bucket, window))")
            db.execute("CREATE TABLE IF NOT EXISTS ledger_settings (key TEXT PRIMARY KEY, value TEXT)")
            setting = db.execute("SELECT value FROM ledger_settings WHERE key='budget_timezone'").fetchone()
            if setting is None:
                self._migrate_utc_days(db)
            elif setting[0] != BUDGET_TIMEZONE:
                raise ValueError("Ledger budget timezone needs a reviewed migration")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def now():
        return datetime.now(timezone.utc)

    @staticmethod
    def day():
        return Ledger.now().astimezone(PACIFIC).date().isoformat()

    def _migrate_utc_days(self, db):
        """Convert legacy UTC settlement days only when their Pacific day is certain.

        Old rows have no settlement timestamp. Bound it by the recorded UTC day,
        admission time and migration time; refuse ambiguous history rather than
        guess or silently omit a charge. All updates and the marker are atomic.
        """
        now = self.now()
        updates = []
        for rid, day, started, active in db.execute("SELECT id,day,started,active FROM runs"):
            if active:
                # Unsettled holds count across every day, and get their final
                # accounting day when settled by the new code.
                pacific_day = now.astimezone(PACIFIC).date()
            else:
                start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                earliest = max(start, datetime.fromtimestamp(started, timezone.utc))
                latest = min(start + timedelta(days=1, microseconds=-1), now)
                if earliest > latest or earliest.astimezone(PACIFIC).date() != latest.astimezone(PACIFIC).date():
                    raise ValueError("Legacy ledger needs reviewed Pacific day assignments before migration")
                pacific_day = earliest.astimezone(PACIFIC).date()
            updates.append((rid, day, pacific_day.isoformat()))
        db.execute("CREATE TABLE IF NOT EXISTS legacy_utc_days (id TEXT PRIMARY KEY, day TEXT)")
        for rid, old_day, new_day in updates:
            db.execute("INSERT INTO legacy_utc_days VALUES (?,?)", (rid, old_day))
            db.execute("UPDATE runs SET day=? WHERE id=?", (new_day, rid))
        db.execute("INSERT INTO ledger_settings VALUES ('budget_timezone',?)", (BUDGET_TIMEZONE,))

    def allow_request(self, buckets):
        """Atomic fixed-minute quotas retained on restart; no raw client IPs.

        Return seconds until the next window, or zero when admitted.
        """
        now = int(time.time())
        window = now // 60
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM request_limits WHERE window < ?", (window,))
            for bucket, limit in buckets:
                row = db.execute("SELECT hits FROM request_limits WHERE bucket=? AND window=?", (bucket, window)).fetchone()
                if row and row[0] >= limit:
                    return 60 - now % 60
            for bucket, _ in buckets:
                db.execute("INSERT INTO request_limits VALUES (?,?,1) ON CONFLICT(bucket,window) DO UPDATE SET hits=hits+1", (bucket, window))
        return 0

    def reserve(self, amount, daily_cap, visitor, hourly_limit=8, concurrency=2, *, start_threshold=False):
        """Reserve a bounded run atomically.

        Strict admission requires the entire new hold to fit. Start-threshold
        admission checks existing charges/holds first, allowing one final run
        to cross the threshold. Per-run token/call limits bound its maximum cost.
        """
        if not math.isfinite(amount) or amount <= 0 or not math.isfinite(daily_cap) or daily_cap < 0:
            raise ValueError("Invalid budget")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            day = self.day()
            spent = db.execute("SELECT COALESCE(SUM(charged),0) FROM runs WHERE day=?", (day,)).fetchone()[0]
            holds = db.execute("SELECT COALESCE(SUM(reserved),0), COALESCE(SUM(active),0) FROM runs WHERE active=1").fetchone()
            if start_threshold:
                if spent >= daily_cap:
                    raise AdmissionDenied("Daily API start limit reached; new investigations resume at midnight Pacific")
                if spent + holds[0] >= daily_cap:
                    raise AdmissionDenied("Daily allowance is reserved by an active or unfinished investigation")
            elif spent + holds[0] + amount > daily_cap + 1e-12:
                raise AdmissionDenied("Daily budget has insufficient unreserved funds")
            if holds[1] >= concurrency:
                raise AdmissionDenied("Investigation capacity reached")
            hits = db.execute("SELECT COUNT(*) FROM runs WHERE visitor=? AND started>?", (visitor, time.time()-3600)).fetchone()[0]
            if hits >= hourly_limit:
                raise AdmissionDenied("Visitor hourly rate limit reached")
            rid = uuid.uuid4().hex
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,0,1)", (rid, day, visitor, time.time(), amount))
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
                # Active holds count across every day. On settlement put the
                # full charge on the current Pacific day, conservatively including
                # any earlier-day usage, so crossing midnight cannot free it.
                db.execute("UPDATE runs SET day=?, charged=?, active=0 WHERE id=?",
                           (self.day(), max(charged, row[0]) if uncertain else charged, rid))

    def spent(self):
        with self.connect() as db:
            return db.execute("SELECT COALESCE(SUM(charged),0) FROM runs WHERE day=?", (self.day(),)).fetchone()[0]

    def budget_status(self):
        # Read the date once so the amount and period cannot disagree at midnight.
        day = self.now().astimezone(PACIFIC).date()
        reset = datetime.combine(day + timedelta(days=1), midnight.min, PACIFIC)
        with self.connect() as db:
            spent = db.execute("SELECT COALESCE(SUM(charged),0) FROM runs WHERE day=?", (day.isoformat(),)).fetchone()[0]
        return {"spent_today_usd": round(spent, 6), "budget_date": day.isoformat(),
                "budget_timezone": BUDGET_TIMEZONE, "budget_resets_at": reset.isoformat()}

    def save_replay(self, rid, payload):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO replays VALUES (?,?)", (rid, payload))

    def replay(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM replays WHERE id=?", (rid,)).fetchone()
            return row[0] if row else None

    def saved_runs(self, limit, offset):
        with self.connect() as db:
            return db.execute(
                "SELECT runs.id, runs.started, replays.payload FROM runs "
                "JOIN replays ON replays.id=runs.id "
                "ORDER BY runs.started DESC, runs.id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
