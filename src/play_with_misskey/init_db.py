#!/usr/bin/env python3
"""
Initialize SQLite database and required tables for play_with_misskey.

Creates `misskey.sqlite` in the repository root (if missing) and ensures
the following tables exist:
 - notelist(text TEXT, noteid TEXT, timestamp TEXT)
 - reactionlist(noteid TEXT, userid TEXT, username TEXT, host TEXT)

Run:
    python3 scripts/init_db.py
"""

import sqlite3
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "misskey.sqlite"


NOTELIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS notelist (
    text TEXT,
    noteid TEXT,
    timestamp TEXT
);
"""

REACTIONLIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS reactionlist (
    noteid TEXT,
    userid TEXT,
    username TEXT,
    host TEXT
);
"""


def init_db(path: str):
    created = not Path(path).exists()
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.executescript(NOTELIST_SCHEMA)
        cur.executescript(REACTIONLIST_SCHEMA)
        # helpful indices
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_notelist_noteid ON notelist(noteid);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_notelist_timestamp ON notelist(timestamp);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_reactionlist_noteid ON reactionlist(noteid);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_reactionlist_userid ON reactionlist(userid);"
        )
        conn.commit()
    return created


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    existed_before = init_db(str(DB_PATH))
    if existed_before:
        print(f"Created new database: {DB_PATH}")
    else:
        print(f"Initialized (or already existed) database: {DB_PATH}")


if __name__ == "__main__":
    main()
