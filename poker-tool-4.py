from __future__ import annotations
"""PokerTool4 – Enhanced with table visualization and advanced metrics
--------------------------------------------------------------------------------------
Features:
- Graphical table representation
- Advanced metrics (pot odds, SPR, equity calculations)
- Improved strategy recommendations
- Opponent profiling
"""

import logging
import random
import math
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Dict, Callable, Any
from itertools import combinations
from dataclasses import dataclass
from enum import Enum

import tkinter as tk
from tkinter import ttk, messagebox, font

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import Session, declarative_base, scoped_session, sessionmaker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("pokertool")

# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

# Position definitions for 6-max table
POSITION_NAMES = {
    1: "UTG",
    2: "MP",
    3: "CO",
    4: "BTN",
    5: "SB",
    6: "BB"
}

POSITION_MULTIPLIERS = {
    1: 0.85,
    2: 0.90,
    3: 0.95,
    4: 1.10,
    5: 0.95,
    6: 1.00
}

# Enhanced position factors for various strategies
POSITION_BULLY_FACTORS = {
    1: 0.4,   # UTG - Very limited bullying potential
    2: 0.6,   # MP - Some bullying potential
    3: 0.85,  # CO - Strong bullying position
    4: 1.0,   # BTN - Best bullying position
    5: 0.7,   # SB - Moderate (out of position post-flop)
    6: 0.5    # BB - Limited (worst position post-flop)
}

# Stack size categories
STACK_CATEGORIES = {
    'short': (0, 20),      # 0-20 BB
    'medium': (20, 80),    # 20-80 BB
    'deep': (80, 150),     # 80-150 BB
    'very_deep': (150, 999) # 150+ BB
}

# Bullying effectiveness based on stack dynamics
STACK_BULLY_MATRIX = {
    ('very_deep', 'short'): 0.6,
    ('very_deep', 'medium'): 1.0,
    ('very_deep', 'deep'): 0.7,
    ('very_deep', 'very_deep'): 0.5,
    ('deep', 'short'): 0.6,
    ('deep', 'medium'): 0.9,
    ('deep', 'deep'): 0.6,
    ('medium', 'short'): 0.5,
    ('medium', 'medium'): 0.4,
    ('short', 'short'): 0.2,
}

HAND_TIERS = {
    'premium': ['AA', 'KK', 'QQ', 'JJ', 'AKs', 'AK'],
    'strong': ['TT', '99', 'AQs', 'AQ', 'AJs', 'KQs', 'ATs'],
    'decent': ['88', '77', 'AJ', 'KQ', 'QJs', 'JTs', 'A9s', 'KJs'],
    'marginal': ['66', '55', 'AT', 'KJ', 'QT', 'JT', 'A8s', 'K9s', 'Q9s'],
    'weak': ['44', '33', '22', 'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s'],
    'speculative': ['T9s', '98s', '87s', '76s', '65s', '54s', 'K8s', 'Q8s', 'J9s']
}

# Hand strength factors
HAND_BULLY_FACTORS = {
    'premium': 1.0,
    'strong': 0.85,
    'decent': 0.7,
    'marginal': 0.55,
    'weak': 0.45,
    'speculative': 0.6,
    'trash': 0.3
}

# Opponent types
class OpponentType(Enum):
    TIGHT_PASSIVE = "Tight-Passive (Rock)"
    TIGHT_AGGRESSIVE = "Tight-Aggressive (TAG)"
    LOOSE_PASSIVE = "Loose-Passive (Calling Station)"
    LOOSE_AGGRESSIVE = "Loose-Aggressive (LAG)"
    UNKNOWN = "Unknown"

@dataclass
class TableMetrics:
    """Advanced table metrics for decision making"""
    pot_size: float = 0.0
    pot_odds: float = 0.0
    implied_odds: float = 0.0
    spr: float = 0.0  # Stack-to-pot ratio
    m_ratio: float = 0.0  # Tournament metric
    fold_equity: float = 0.0
    ev: float = 0.0  # Expected value
    hand_equity: float = 0.0
    bluff_to_value_ratio: float = 0.0

class Card:
    def __init__(self, rank: str, suit: str) -> None:
        self.rank = rank
        self.suit = suit
        self.value = RANK_VALUES[rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return f"Card({self.rank}, {self.suit})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))

def create_deck() -> List[Card]:
    return [Card(r, s) for s in SUITS for r in RANKS]

# ... (rest of the code unchanged) ...

# Main
def main():
    try:
        root = tk.Tk()
        app = PokerAssistant(root)
        log.info("Enhanced Poker Assistant with Table Visualization started successfully")
        root.mainloop()
    except Exception as e:
        log.error(f"Failed to start application: {e}")
        messagebox.showerror("Startup Error", f"Failed to start Enhanced Poker Assistant: {e}")

if __name__ == "__main__":
    main()
