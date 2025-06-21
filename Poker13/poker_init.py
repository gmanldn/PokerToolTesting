#!/usr/bin/env python3
"""
Initialisation / persistence layer for Poker-Assistant.

* Creates the sqlite database the first time the app is launched
* Offers open_db() + record_decision() helpers that the GUI can import
"""
import sqlite3
import logging
from pathlib import Path
from typing import Optional

# Local imports after project structure is clear
from poker_modules import HandAnalysis, Position

log = logging.getLogger(__name__)
DB_FILE = "poker_decisions.db"

# ──────────────────────────────────────────────────────
#  Database bootstrap
# ──────────────────────────────────────────────────────
def _create_schema(conn: sqlite3.Connection) -> None:
    """Create tables – called exactly once when the file did not exist."""
    log.info("Creating DB schema for new version...")
    conn.execute("""
        CREATE TABLE decisions (
            id            INTEGER PRIMARY KEY,
            timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
            position      TEXT,
            hand_tier     TEXT,
            stack_bb      INTEGER,
            pot           REAL,
            to_call       REAL,
            board         TEXT,
            decision      TEXT,
            showdown_win  INTEGER,
            spr           REAL,      -- Added
            board_texture TEXT       -- Added
        );
    """)
    conn.commit()


def open_db() -> sqlite3.Connection:
    """Return a live sqlite3 connection."""
    initialise_db_if_needed()
    return sqlite3.connect(DB_FILE)


def initialise_db_if_needed() -> None:
    """Create the database file / schema if we have never run before."""
    if not Path(DB_FILE).exists():
        with sqlite3.connect(DB_FILE) as conn:
            _create_schema(conn)


# ──────────────────────────────────────────────────────
#  Public helpers used by the rest of the program
# ──────────────────────────────────────────────────────
def record_decision(
    analysis: HandAnalysis, position: Position, tier: str,
    stack_bb: int, pot: float, to_call: float, board: str
) -> int:
    """Persist a decision and return its row-id."""
    with open_db() as db:
        cur = db.execute(
            """INSERT INTO decisions
               (position, hand_tier, stack_bb, pot, to_call, board, decision, spr, board_texture)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position.name, tier, stack_bb, pot, to_call, board,
                analysis.decision, analysis.spr, analysis.board_texture
            )
        )
        return cur.lastrowid

# Make sure the DB exists right after import
initialise_db_if_needed()

if __name__ == "__main__":
    print("Database ready at", Path(DB_FILE).absolute())
