"""Hospital reviews storage. One review per user per hospital (posting again replaces it).

SqliteStore  - local development and tests (file on disk).
FirestoreStore - Cloud Run (Cloud Run disks are temporary, so production must use Firestore).
             Layout: hospitals/{hospital_id}/reviews/{uid}
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


@lru_cache(maxsize=1)
def get_store():
    if config.STORE == "firestore":
        return FirestoreStore()
    return SqliteStore(config.SQLITE_PATH)
