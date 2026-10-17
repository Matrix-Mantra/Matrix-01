"""Copy users and reviews from the local SQLite file (local.db) to Firestore.

    python -m scripts.migrate_to_firestore            # copy
    python -m scripts.migrate_to_firestore --dry-run  # just count

Needs Firestore credentials (GOOGLE_APPLICATION_CREDENTIALS in .env, see README). Safe to run twice:
documents are written with the same ids, so a second run overwrites rather than duplicates.
"""

from __future__ import annotations

import argparse
import sqlite3

from app import config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    c = sqlite3.connect(config.SQLITE_PATH)
    c.row_factory = sqlite3.Row
    users = [dict(r) for r in c.execute("SELECT * FROM users")]
    reviews = [dict(r) for r in c.execute("SELECT * FROM reviews")]
    print(f"local.db: {len(users)} users, {len(reviews)} reviews")
    if args.dry_run:
        return
    from google.cloud import firestore

    db = firestore.Client()
    for u in users:
        db.collection("users").document(u["uid"]).set(u)
    for r in reviews:
        db.collection("hospitals").document(r["hospital_id"]).collection("reviews").document(r["uid"]).set(r)
    print(f"Copied to Firestore project {db.project}.")


if __name__ == "__main__":
    main()
