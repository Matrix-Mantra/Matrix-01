"""Storage for hospital reviews and user accounts.

Reviews: one per user per hospital (posting again replaces it).
Users: one row per login account (name, email, first and last login, number of logins).

SqliteStore  - local development and tests (file on disk).
FirestoreStore - Cloud Run (Cloud Run disks are temporary, so production must use Firestore).
             Layout: hospitals/{hospital_id}/reviews/{uid}, users/{uid}
"""

from __future__ import annotations

import sqlite3
import threading
import time
from functools import lru_cache

from . import config


def _public(r: dict) -> dict:
    return {"hospital_id": r["hospital_id"], "author": r["author"], "rating": r["rating"], "comment": r["comment"],
            "created_at": r["created_at"], "updated_at": r["updated_at"], "uid": r["uid"]}


def _user(r: dict) -> dict:
    return {"uid": r["uid"], "name": r["name"], "email": r.get("email") or "", "created_at": r["created_at"],
            "last_login_at": r["last_login_at"], "login_count": r["login_count"]}


class SqliteStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS reviews (
                    hospital_id TEXT NOT NULL, uid TEXT NOT NULL, author TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5), comment TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY (hospital_id, uid))"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL, last_login_at REAL NOT NULL, login_count INTEGER NOT NULL DEFAULT 0)"""
            )

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def upsert_review(self, hospital_id: str, uid: str, author: str, rating: int, comment: str) -> dict:
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO reviews (hospital_id, uid, author, rating, comment, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(hospital_id, uid) DO UPDATE SET author=excluded.author, rating=excluded.rating,
                   comment=excluded.comment, updated_at=excluded.updated_at""",
                (hospital_id, uid, author, rating, comment, now, now),
            )
            row = c.execute("SELECT * FROM reviews WHERE hospital_id=? AND uid=?", (hospital_id, uid)).fetchone()
        return _public(dict(row))

    def delete_review(self, hospital_id: str, uid: str) -> bool:
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM reviews WHERE hospital_id=? AND uid=?", (hospital_id, uid)).rowcount > 0

    def list_reviews(self, hospital_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM reviews WHERE hospital_id=? ORDER BY updated_at DESC LIMIT ?",
                             (hospital_id, limit)).fetchall()
        return [_public(dict(r)) for r in rows]

    def summaries(self) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT hospital_id, AVG(rating) a, COUNT(*) n FROM reviews GROUP BY hospital_id").fetchall()
        return {r["hospital_id"]: {"avg": round(r["a"], 1), "count": r["n"]} for r in rows}

    def record_login(self, uid: str, name: str, email: str = "") -> dict:
        """Create the user on first login, otherwise update name, last login and count. Empty email keeps the old one."""
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO users (uid, name, email, created_at, last_login_at, login_count) VALUES (?, ?, ?, ?, ?, 1)
                   ON CONFLICT(uid) DO UPDATE SET name=excluded.name, last_login_at=excluded.last_login_at,
                   login_count=users.login_count + 1,
                   email=CASE WHEN excluded.email != '' THEN excluded.email ELSE users.email END""",
                (uid, name, email, now, now),
            )
            row = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return _user(dict(row))

    def get_user(self, uid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return _user(dict(row)) if row else None

    def set_email(self, uid: str, email: str) -> dict | None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE users SET email=? WHERE uid=?", (email, uid))
            row = c.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return _user(dict(row)) if row else None


class FirestoreStore:
    """Same interface, backed by Firestore. Summaries are cached for 60 s to keep reads low."""

    def __init__(self):
        from google.cloud import firestore  # optional dependency

        self._fs = firestore
        self.db = firestore.Client()
        self._cache: tuple[float, dict] | None = None

    def _ref(self, hospital_id: str, uid: str):
        return self.db.collection("hospitals").document(hospital_id).collection("reviews").document(uid)

    def upsert_review(self, hospital_id: str, uid: str, author: str, rating: int, comment: str) -> dict:
        ref = self._ref(hospital_id, uid)
        now = time.time()
        snap = ref.get()
        created = snap.to_dict().get("created_at", now) if snap.exists else now
        doc = {"hospital_id": hospital_id, "uid": uid, "author": author, "rating": rating, "comment": comment,
               "created_at": created, "updated_at": now}
        ref.set(doc)
        self._cache = None
        return _public(doc)

    def delete_review(self, hospital_id: str, uid: str) -> bool:
        ref = self._ref(hospital_id, uid)
        if not ref.get().exists:
            return False
        ref.delete()
        self._cache = None
        return True

    def list_reviews(self, hospital_id: str, limit: int = 50) -> list[dict]:
        q = (self.db.collection("hospitals").document(hospital_id).collection("reviews")
             .order_by("updated_at", direction=self._fs.Query.DESCENDING).limit(limit))
        return [_public(d.to_dict()) for d in q.stream()]

    def summaries(self) -> dict[str, dict]:
        if self._cache and time.time() - self._cache[0] < 60:
            return self._cache[1]
        acc: dict[str, list[int]] = {}
        for d in self.db.collection_group("reviews").select(["hospital_id", "rating"]).stream():
            x = d.to_dict()
            acc.setdefault(x["hospital_id"], []).append(x["rating"])
        out = {h: {"avg": round(sum(v) / len(v), 1), "count": len(v)} for h, v in acc.items()}
        self._cache = (time.time(), out)
        return out

    def record_login(self, uid: str, name: str, email: str = "") -> dict:
        ref = self.db.collection("users").document(uid)
        now = time.time()
        snap = ref.get()
        old = snap.to_dict() if snap.exists else {}
        doc = {"uid": uid, "name": name, "email": email or old.get("email", ""), "created_at": old.get("created_at", now),
               "last_login_at": now, "login_count": old.get("login_count", 0) + 1}
        ref.set(doc)
        return _user(doc)

    def get_user(self, uid: str) -> dict | None:
        snap = self.db.collection("users").document(uid).get()
        return _user(snap.to_dict()) if snap.exists else None

    def set_email(self, uid: str, email: str) -> dict | None:
        ref = self.db.collection("users").document(uid)
        if not ref.get().exists:
            return None
        ref.update({"email": email})
        return self.get_user(uid)


@lru_cache(maxsize=1)
def get_store():
    if config.STORE == "firestore":
        return FirestoreStore()
    return SqliteStore(config.SQLITE_PATH)
