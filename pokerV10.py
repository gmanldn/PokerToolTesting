from __future__ import annotations

import itertools
import logging
import math
import random
import sqlite3
import sys
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import List, Sequence, Dict, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ─────────────────────────────────────────────────────────────────────────────
# 0.  Fast, exact evaluator (mandatory)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from treys import Card as TCard, Evaluator as TreysEval  # type: ignore
except ModuleNotFoundError:
    sys.exit("PokerV9 needs the 'treys' package.  pip install treys")

_TREYS = TreysEval()  # singleton

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Globals / constants
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)7s | %(message)s")
log = logging.getLogger(__name__)

RANKS = "23456789TJQKA"
CARD_SIZE = 52
GUI_W, GUI_H = 1400, 900
FULL_DECK: tuple["Card", ...]  # defined after Card class

# ----- Dark GUI palette with high contrast buttons ---------------------------
C_BG = "#1e1f22"      # window background
C_PANEL = "#2d2f33"   # side panels / frames
C_TABLE = "#0f5132"   # poker table
C_CARD = "#fafafa"    # face of a card
C_TEXT = "#ecf0f1"    # normal foreground

# High contrast button colors
C_BTN_PRIMARY = "#0d7377"    # primary action (teal)
C_BTN_SUCCESS = "#14A44D"    # success/GO (green)
C_BTN_DANGER = "#DC2626"     # danger/fold (red)
C_BTN_WARNING = "#F59E0B"    # warning/neutral (amber)
C_BTN_INFO = "#3B82F6"       # info/secondary (blue)
C_BTN_DARK = "#374151"       # clear/reset (dark gray)

# Button hover states (lighter versions)
C_BTN_PRIMARY_HOVER = "#14b8bd"
C_BTN_SUCCESS_HOVER = "#16c658"
C_BTN_DANGER_HOVER = "#ef4444"
C_BTN_WARNING_HOVER = "#fbbf24"
C_BTN_INFO_HOVER = "#60a5fa"
C_BTN_DARK_HOVER = "#4b5563"

# --- Behavioral constants for analysis ---
# These are heuristic base values, adjusted by game state
POSITION_BULLY = {1: 1.0, 2: 0.7, 3: 0.5, 4: 0.4, 5: 0.6, 6: 0.85}
HAND_BULLY = {
    "premium": 1.0,
    "strong": 0.85,
    "decent": 0.70,
    "marginal": 0.55,
    "weak": 0.45,
    "spec": 0.60,
    "trash": 0.30,
}

# ─────────────────────────────────────────────────────────────────────────────
# 2.  Domain model
# ─────────────────────────────────────────────────────────────────────────────
class Suit(str, Enum):
    SPADE = "♠"
    HEART = "♥"
    DIAMOND = "♦"
    CLUB = "♣"

    @property
    def color(self) -> str:
        return "red" if self in (Suit.HEART, Suit.DIAMOND) else "black"


@dataclass(frozen=True, slots=True)
class Card:
    rank: str
    suit: Suit

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise ValueError(f"Illegal rank {self.rank}")
        if not isinstance(self.suit, Suit):
            raise TypeError("suit must be Suit")

    def __str__(self) -> str:
        return f"{self.rank}{self.suit.value}"

    @property
    def value(self) -> int:
        return RANKS.index(self.rank)


FULL_DECK = tuple(Card(r, s) for s in Suit for r in RANKS)


class Position(IntEnum):
    BTN = 1
    SB = 2
    BB = 3
    UTG = 4
    MP = 5
    CO = 6


class StackType(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @property
    def default_bb(self) -> int:
        return {"Low": 40, "Medium": 100, "High": 200}[self.value]


class PlayerAction(str, Enum):
    FOLD = "Fold"
    CHECK = "Check"
    CALL = "Call"
    RAISE = "Raise"


class Street(str, Enum):
    PREFLOP = "Pre-flop"
    FLOP = "Flop"
    TURN = "Turn"
    RIVER = "River"

    @classmethod
    def from_board_len(cls, n_cards: int) -> "Street":
        return {0: cls.PREFLOP, 3: cls.FLOP, 4: cls.TURN, 5: cls.RIVER}[n_cards]


@dataclass(slots=True, frozen=True)
class BoardTexture:
    street: Street
    text: str
    is_paired: bool
    is_monotone: bool
    is_connected: bool
    high_card_rank: int


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Pure poker mathematics – no GUI code
# ─────────────────────────────────────────────────────────────────────────────
HAND_TIERS = {
    "premium": ["AA", "KK", "QQ", "JJ", "AKs", "AK"],
    "strong": ["TT", "99", "AQs", "AQ", "AJs", "KQs", "ATs"],
    "decent": ["88", "77", "AJ", "KQ", "QJs", "JTs", "A9s", "KJs"],
    "marginal": ["66", "55", "AT", "KJ", "QT", "JT", "A8s", "K9s", "Q9s"],
    "weak": ["44", "33", "22", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s"],
    "spec": ["T9s", "98s", "87s", "76s", "65s", "54s", "K8s", "Q8s", "J9s"],
}


def to_two_card_str(two: Sequence[Card]) -> str:
    """Converts two cards to a standard string representation (e.g., 'AKs', '77')."""
    if len(two) != 2:
        return ""
    a, b = two
    if a.rank == b.rank:
        return a.rank * 2
    suited = "s" if a.suit == b.suit else ""
    hi, lo = sorted(two, key=lambda c: c.value, reverse=True)
    return f"{hi.rank}{lo.rank}{suited}"


def hand_tier(two: Sequence[Card]) -> str:
    """Classifies a two-card hand into a tier."""
    code = to_two_card_str(two)
    for tier, hands in HAND_TIERS.items():
        if code in hands:
            return tier
    return "trash"


def analyze_board_texture(board: Sequence[Card]) -> BoardTexture:
    """Analyzes the given board cards for draws, pairs, etc."""
    n = len(board)
    street = Street.from_board_len(n)
    if n == 0:
        return BoardTexture(street, "Pre-flop", False, False, False, -1)

    ranks = sorted([c.value for c in board])
    suits = [c.suit for c in board]

    is_paired = len(set(ranks)) < n
    is_monotone = len(set(suits)) == 1 if n >= 3 else False
    
    # Check for straight possibility (e.g., 3-gap or less)
    is_connected = False
    if n >= 3:
        gaps = [ranks[i+1] - ranks[i] for i in range(n-1)]
        if ranks[-1] - ranks[0] <= 4 or sum(gaps) - len(gaps) <= 2:
            is_connected = True

    # Describe texture
    parts = []
    if is_monotone: parts.append("Monotone")
    elif len(set(suits)) == 2 and n >= 3: parts.append("Two-tone")
    if is_paired: parts.append("Paired")
    if is_connected: parts.append("Connected")
    
    text = ", ".join(parts) if parts else "Dry"
    high_card_rank = ranks[-1]
    
    return BoardTexture(street, text, is_paired, is_monotone, is_connected, high_card_rank)


def _tcard(c: Card) -> int:
    """Converts a Card object to its integer representation for `treys`."""
    suit_map = {Suit.SPADE: "s", Suit.HEART: "h", Suit.DIAMOND: "d", Suit.CLUB: "c"}
    return TCard.new(c.rank + suit_map[c.suit])


def _enumerate_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    """Exact equity when ≤2 unknown board cards (turn or river)."""
    deck = [c for c in FULL_DECK if c not in hole and c not in board]
    wins = ties = total = 0
    hero_hole = [_tcard(c) for c in hole]

    for opp in itertools.combinations(deck, 2):
        opp_hole = [_tcard(c) for c in opp]
        remain_deck = [c for c in deck if c not in opp]
        
        remain_board_count = 5 - len(board)
        for runout_cards in itertools.combinations(remain_deck, remain_board_count):
            total += 1
            board_cards = [_tcard(c) for c in board + list(runout_cards)]
            
            h1 = _TREYS.evaluate(board_cards, hero_hole)
            h2 = _TREYS.evaluate(board_cards, opp_hole)

            if h1 < h2:
                wins += 1
            elif h1 == h2:
                ties += 1
    return (wins + ties / 2) / total if total else 0.0


def adaptive_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    """Smart equity: exact when cheap, adaptive Monte-Carlo otherwise."""
    unknown_cards = 5 - len(board)
    if unknown_cards <= 2:
        return _enumerate_equity(hole, board)

    deck = [c for c in FULL_DECK if c not in hole and c not in board]
    hero_hole = [_tcard(c) for c in hole]
    
    # Rough equity estimate to determine sample size
    rough_win_prob = 1.0 - (_TREYS.get_rank_class(_TREYS.evaluate([], hero_hole)) / 9.0)
    variance_proxy = max(0.05, rough_win_prob * (1 - rough_win_prob))
    n_samples = int(min(5000, max(1000, 1500 / variance_proxy)))
    
    wins = ties = 0
    for _ in range(n_samples):
        runout_and_opp = random.sample(deck, 2 + unknown_cards)
        opp_hole_cards = runout_and_opp[:2]
        runout = runout_and_opp[2:]

        board_cards = [_tcard(c) for c in board + runout]
        opp_hole = [_tcard(c) for c in opp_hole_cards]

        h1 = _TREYS.evaluate(board_cards, hero_hole)
        h2 = _TREYS.evaluate(board_cards, opp_hole)

        if h1 < h2:
            wins += 1
        elif h1 == h2:
            ties += 1

    return (wins + ties / 2) / n_samples


def pot_odds(to_call: float, pot_size: float) -> float:
    return to_call / (pot_size + to_call) if to_call > 0 else 0.0


def expected_value(equity: float, pot_size: float, investment: float) -> float:
    return equity * (pot_size + investment) - investment


def logistic_stack_factor(bb: int) -> float:
    """Smooth 1.0 → 2.0 increase around 80bb, capped at 2.0. Models deep stack aggression."""
    return 1.0 + 1.0 / (1.0 + math.exp(-(bb - 80) / 20))


@dataclass(slots=True)
class Analysis:
    """Container for the results of a hand analysis."""
    equity: float
    required_eq: float
    ev_call: float
    ev_raise: float
    spr: float
    aggression_factor: float
    decision: str
    reason: str
    board_texture: BoardTexture


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Persistence – SQLite
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = Path("poker_assistant_v9.sqlite3")

@contextmanager
def open_db():
    # Note: If changing schema, you may need to delete the old DB file.
    con = sqlite3.connect(DB_PATH, timeout=3.0)
    con.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id           INTEGER PRIMARY KEY,
            ts           TEXT DEFAULT CURRENT_TIMESTAMP,
            position     TEXT,
            tier         TEXT,
            stack_bb     REAL,
            pot          REAL,
            to_call      REAL,
            equity       REAL,
            required_eq  REAL,
            ev_call      REAL,
            ev_raise     REAL,
            street       TEXT,
            board        TEXT,
            decision     TEXT,
            showdown_win INTEGER
        );""")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def record_decision(a: Analysis, pos: Position, tier: str, stack_bb: int,
                    pot: float, to_call: float, board_str: str) -> int:
    """Records a decision and its context into the database."""
    with open_db() as db:
        cur = db.execute("""INSERT INTO decisions
            (position, tier, stack_bb, pot, to_call, equity, required_eq,
             ev_call, ev_raise, street, board, decision)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
             (pos.name, tier, stack_bb, pot, to_call, a.equity, a.required_eq,
              a.ev_call, a.ev_raise, a.board_texture.street.value, board_str, a.decision))
        return cur.lastrowid


def historical_fold_equity(pos: Position, tier: str, street: Street) -> float:
    """Empirical villain-fold frequency after our raise, given context."""
    with open_db() as db:
        cur = db.execute("""SELECT COUNT(*),
                                   SUM(CASE WHEN showdown_win IS NULL THEN 1 ELSE 0 END)
                            FROM decisions
                            WHERE position=? AND tier=? AND street=? AND decision='RAISE'""",
                         (pos.name, tier, street.value))
        total, no_showdown = cur.fetchone()
    # Laplace smoothing to avoid zero-division and provide a reasonable prior
    return (no_showdown + 1) / (total + 4) if total else 0.25 # Prior: 25% fold equity

# ─────────────────────────────────────────────────────────────────────────────
# 5.  Analysis wrapper
# ─────────────────────────────────────────────────────────────────────────────
def analyse_hand(
    hole: Sequence[Card],
    board: Sequence[Card],
    pos: Position,
    stack_bb: int,
    pot: float,
    to_call: float,
) -> Analysis:
    """
    Performs a comprehensive analysis of the poker hand situation.

    This is the core decision-making engine. It evaluates equity, board texture,
    and game state variables to recommend a course of action.
    """
    board_texture = analyze_board_texture(board)
    equity = adaptive_equity(hole, board)
    required_eq = pot_odds(to_call, pot)
    ev_call = expected_value(equity, pot, to_call)
    spr = stack_bb / pot if pot > 0 else float("inf")
    tier = hand_tier(hole)

    # Adjust base aggression by board texture; wet boards encourage more aggression
    # with strong hands to deny equity, and also for semi-bluffs.
    texture_mod = 1.2 if board_texture.is_connected or board_texture.is_monotone else 0.95
    aggression_factor = (
        POSITION_BULLY[pos]
        * HAND_BULLY[tier]
        * logistic_stack_factor(stack_bb)
        * texture_mod
    )
    
    # Model a standard raise
    raise_amt = max(to_call * 2.5, pot * 0.75) if to_call > 0 else pot * 0.75

    # Estimate fold equity using historical data and current situation
    # Scary boards (Ace high, paired, etc.) increase fold equity.
    board_scare_factor = 0.0
    if board_texture.high_card_rank >= 12: board_scare_factor += 0.1 # Ace
    if board_texture.is_paired: board_scare_factor += 0.1
    hist_fe = historical_fold_equity(pos, tier, board_texture.street)
    fold_equity = 0.6 * hist_fe + 0.4 * min(0.40, aggression_factor * 0.20 + board_scare_factor)

    # Calculate EV of raising, considering when opponent folds vs. calls
    ev_raise = (fold_equity * pot) + (1 - fold_equity) * expected_value(equity, pot, raise_amt)

    #--- Decision Logic ---
    decision, reason = "FOLD", "Default action; does not meet call/raise criteria."
    ev_fold = 0.0

    # Primary Decision: Compare EVs
    if ev_raise > ev_call and ev_raise > ev_fold:
        decision = "RAISE"
        reason = f"Raising has the highest EV (${ev_raise:.2f})."
        if equity < 0.5: # Bluff or semi-bluff
            reason += " This is a pressure play (semi-bluff) exploiting fold equity."
        else:
            reason += " This is a play for value with a strong holding."
    elif ev_call > ev_fold:
        decision = "CALL"
        reason = f"Calling is profitable (EV ${ev_call:.2f}) and better than folding."
    
    # Heuristic Overrides for common situations
    
    # 1. Implied Odds: Justify a call with a strong draw even if slightly unprofitable now.
    is_strong_draw = tier == "spec" and board_texture.street != Street.RIVER
    if decision == "FOLD" and is_strong_draw and spr > 5 and required_eq < 0.35:
        if (required_eq - equity) < 0.10: # If we are close
            decision = "CALL"
            reason = "Pot odds are slightly unfavorable, but implied odds with a strong draw and deep stacks justify a call."
    
    # 2. Pot Control: Avoid bloating the pot with a marginal hand out of position.
    is_marginal_made_hand = tier in ("decent", "marginal")
    is_oop = pos in (Position.SB, Position.BB, Position.UTG)
    if decision == "RAISE" and is_marginal_made_hand and is_oop and ev_raise < ev_call * 1.25:
        decision = "CALL"
        reason = "Raising is barely better than calling. Pot control by calling is prudent with a marginal hand out of position."

    # 3. Zero-call check
    if to_call == 0 and decision == "FOLD":
        decision = "CHECK"
        reason = "No cost to see the next card; checking is the obvious choice."

    return Analysis(equity, required_eq, ev_call, ev_raise, spr, aggression_factor, decision, reason, board_texture)
# ─────────────────────────────────────────────────────────────────────────────
# 6.  Advice helpers (Now with more context!)
# ─────────────────────────────────────────────────────────────────────────────
def get_position_advice(pos: Position) -> str:
    advice = {
        Position.BTN: "You're on the Button, the most powerful position. You can play a wide range of hands, steal blinds, and apply maximum pressure post-flop.",
        Position.SB: "You're in the Small Blind, the worst position post-flop. Play a tight, strong range. Avoid speculative hands unless completing for a cheap price multiway.",
        Position.BB: "You're in the Big Blind. You get great pot odds to defend, so play wide. However, be cautious post-flop as you will be out of position.",
        Position.UTG: "You're Under the Gun, the earliest position. Play only your strongest hands. Your range should be very tight here.",
        Position.MP: "You're in Middle Position. Your opening range should be tighter than late position but wider than UTG. Hand selection is key.",
        Position.CO: "You're in the Cutoff, a powerful late position. Open with a wide range, especially if the button is passive. Attack the blinds aggressively."
    }
    return advice.get(pos, "")


def get_hand_advice(tier: str, texture: BoardTexture, spr: float) -> str:
    """Generates dynamic advice based on hand strength and board texture."""
    base_advice = {
        "premium": "You have a premium hand, the nuts of your range. Focus on building the pot. Rarely consider folding.",
        "strong": "You have a strong made hand. Bet for value and to protect your equity against draws.",
        "decent": "A decent hand, but vulnerable. Proceed with caution, especially against aggression or on scary boards. Pot control is often a good idea.",
        "marginal": "A marginal made hand. Try to get to showdown cheaply. Be wary of multiway pots or heavy betting.",
        "weak": "This is a weak made hand, likely for set-mining. If you haven't hit your set, fold to any significant bet.",
        "spec": "A speculative drawing hand. Your play depends on pot odds, implied odds (check SPR!), and position. These hands play best in position.",
        "trash": "A trash hand. This should almost always be folded pre-flop. If you've reached post-flop, don't invest more money without significant improvement."
    }[tier]

    # Add texture-specific refinement
    if texture.street != Street.PREFLOP:
        if texture.is_monotone or texture.is_connected:
            if tier in ('premium', 'strong'):
                base_advice += " The board is very wet and dangerous; be prepared for action and consider larger bet sizes to deny equity to draws."
            if tier == 'spec':
                base_advice += " This wet board is excellent for your speculative hand's potential. You may have a strong draw (or a monster already)."
        elif spr < 4:
             if tier in ('premium', 'strong'):
                base_advice += " With a low SPR, you should be looking to get all-in. Don't slow play."


    return base_advice

# ─────────────────────────────────────────────────────────────────────────────
# 7.  Custom Dialogs and Reusable Button Class (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
class StyledButton(tk.Button):
    """High contrast button with consistent styling"""
    def __init__(self, parent, text="", color=C_BTN_PRIMARY, hover_color=None, **kwargs):
        defaults = {
            "font": ("Arial", 11, "bold"), "fg": "white", "bg": color,
            "activebackground": hover_color or color, "activeforeground": "white",
            "bd": 0, "padx": 15, "pady": 8, "cursor": "hand2", "relief": "flat"
        }
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)
        self._bg = color
        self._hover_bg = hover_color or color
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

class PlayerActionDialog(tk.Toplevel):
    def __init__(self, parent, player_num: int, current_pot: float):
        super().__init__(parent)
        self.title(f"Player {player_num} Action")
        self.geometry("450x220")
        self.configure(bg=C_PANEL)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[Tuple[PlayerAction, float]] = None
        self.current_pot = current_pot
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        self._build_ui(player_num)
    def _build_ui(self, player_num: int):
        header = tk.Label(self, text=f"What did Player {player_num} do?",
                         font=("Arial", 16, "bold"), bg=C_PANEL, fg=C_TEXT)
        header.pack(pady=(20, 10))
        pot_label = tk.Label(self, text=f"Current Pot: ${self.current_pot:.1f}",
                            font=("Arial", 12), bg=C_PANEL, fg=C_TEXT)
        pot_label.pack(pady=5)
        btn_frame = tk.Frame(self, bg=C_PANEL)
        btn_frame.pack(pady=20)
        fold_btn = StyledButton(btn_frame, text="FOLD",
                               color=C_BTN_DANGER, hover_color=C_BTN_DANGER_HOVER,
                               width=10, height=2,
                               command=lambda: self._set_result(PlayerAction.FOLD, 0))
        fold_btn.pack(side="left", padx=10)
        check_btn = StyledButton(btn_frame, text="CHECK/CALL",
                                color=C_BTN_INFO, hover_color=C_BTN_INFO_HOVER,
                                width=12, height=2,
                                command=lambda: self._set_result(PlayerAction.CALL, 0))
        check_btn.pack(side="left", padx=10)
        raise_btn = StyledButton(btn_frame, text="RAISE",
                                color=C_BTN_WARNING, hover_color=C_BTN_WARNING_HOVER,
                                width=10, height=2, command=self._handle_raise)
        raise_btn.pack(side="left", padx=10)
        skip_btn = StyledButton(self, text="Skip (Unknown)",
                               color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER,
                               width=20, command=self.destroy)
        skip_btn.pack(pady=(0, 10))
    def _set_result(self, action: PlayerAction, amount: float):
        self.result = (action, amount)
        self.destroy()
    def _handle_raise(self):
        amount_str = simpledialog.askstring("Raise Amount",
                                           "Enter raise amount:", parent=self)
        if amount_str:
            try:
                amount = float(amount_str)
                self._set_result(PlayerAction.RAISE, amount)
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid number")

# ─────────────────────────────────────────────────────────────────────────────
# 8.  GUI widgets (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
class DraggableCard(tk.Label):
    """Label inside grid – supports click & drag."""
    def __init__(self, master: tk.Widget, card: Card, app: "PokerAssistant"):
        super().__init__(
            master, text=str(card), font=("Arial", 11, "bold"), fg=card.suit.color,
            bg=C_CARD, width=4, height=3, bd=2, relief="raised",
        )
        self.card = card
        self._app = weakref.proxy(app)
        self.bind("<Button-1>", self._click_start)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self._start = (0, 0)
        self._dragging = False
    def _click_start(self, ev):
        self._start = (ev.x, ev.y)
        self._dragging = False
        self.lift()
    def _drag(self, ev):
        dx, dy = ev.x - self._start[0], ev.y - self._start[1]
        if abs(dx) > 3 or abs(dy) > 3: self._dragging = True
        self.place(x=self.winfo_x() + dx, y=self.winfo_y() + dy)
    def _release(self, ev):
        target = self.winfo_containing(ev.x_root, ev.y_root)
        if self._dragging and hasattr(target, "accept"):
            target.accept(self)
        else:
            self.place_forget()
            self.pack(side="left", padx=1, pady=1)
            self._app.place_next_free(self.card)

class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, app: "PokerAssistant"):
        super().__init__(
            master, width=CARD_SIZE + 10, height=int(CARD_SIZE * 1.4),
            bg=C_TABLE, bd=3, relief="sunken",
        )
        self.pack_propagate(False)
        self._label = tk.Label(self, text=name, bg=C_TABLE, fg=C_TEXT)
        self._label.pack(expand=True)
        self.card: Card | None = None
        self._app = weakref.proxy(app)
    def accept(self, widget: DraggableCard):
        if self.card:
            widget.place_forget()
            widget.pack(side="left", padx=1, pady=1)
            return
        self.set_card(widget.card)
        widget.place_forget()
        widget._app.grey_out(widget.card)
        self._app.refresh()
    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children(): w.destroy()
        inner = tk.Label(
            self, text=str(card), font=("Arial", 14, "bold"),
            fg=card.suit.color, bg=C_CARD, bd=2, relief="raised",
        )
        inner.pack(expand=True, fill="both", padx=3, pady=3)
        inner.bind("<Double-Button-1>", lambda *_: self.clear())
    def clear(self):
        if not self.card: return
        self._app.un_grey(self.card)
        self.card = None
        for w in self.winfo_children(): w.destroy()
        self._label = tk.Label(self, text="Empty", bg=C_TABLE, fg=C_TEXT)
        self._label.pack(expand=True)
        self._app.refresh()

# ─────────────────────────────────────────────────────────────────────────────
# 9.  Main Tk window (Logic updated, layout unchanged)
# ─────────────────────────────────────────────────────────────────────────────
class PokerAssistant(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v9 - High Contrast Edition")
        self.geometry(f"{GUI_W}x{GUI_H}")
        self.minsize(1200, 800)
        self.configure(bg=C_BG)

        # shared state
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.small_blind = tk.DoubleVar(value=0.5)
        self.big_blind = tk.DoubleVar(value=1.0)
        self.call_amt = tk.DoubleVar(value=2.0)
        self.num_players = tk.IntVar(value=6)
        
        # Game state
        self.game_started = False
        self.current_pot = 0.0
        self.players_in_hand: List[int] = []
        self.player_actions: Dict[int, tuple[PlayerAction, float]] = {}
        self.action_complete = False

        self.grid_cards: dict[str, DraggableCard] = {}
        self.used: set[str] = set()
        self._last_decision_id: int | None = None

        self._build_gui()
        self.after(100, self.refresh)

    # ─────────────────────────────────────────────────────────────────────
    def _build_gui(self):
        main_frame = tk.Frame(self, bg=C_BG)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel
        left = tk.Frame(main_frame, bg=C_PANEL, width=320)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        tk.Label(left, text="Card Selection", font=("Arial", 14, "bold"),
                 bg=C_PANEL, fg=C_TEXT).pack(pady=(10, 10))
        card_frame = tk.Frame(left, bg=C_PANEL)
        card_frame.pack(fill="both", expand=True)

        for suit in Suit:
            lf = tk.LabelFrame(card_frame, text=f"{suit.value} {suit.name.title()}",
                               fg=suit.color, bg=C_PANEL, font=("Arial", 10, "bold"))
            lf.pack(fill="x", padx=5, pady=3)
            for r in RANKS:
                card = Card(r, suit)
                w = DraggableCard(lf, card, self)
                w.pack(side="left", padx=1, pady=1)
                self.grid_cards[str(card)] = w

        # Right side
        right = tk.Frame(main_frame, bg=C_BG)
        right.pack(side="left", fill="both", expand=True)
        game_frame = tk.Frame(right, bg=C_BG)
        game_frame.pack(fill="x", pady=(0, 10))
        table = tk.Frame(game_frame, bg=C_TABLE, bd=4, relief="ridge")
        table.pack(pady=10)

        hole_frame = tk.Frame(table, bg=C_TABLE); hole_frame.pack(side="left", padx=5)
        tk.Label(hole_frame, text="Your Hand", bg=C_TABLE, fg=C_TEXT, font=("Arial", 10, "bold")).pack()
        hole_slots = tk.Frame(hole_frame, bg=C_TABLE); hole_slots.pack()
        self.hole = [CardSlot(hole_slots, f"Hole{i+1}", self) for i in range(2)]
        for s in self.hole: s.pack(side="left", padx=2, pady=2)

        board_frame = tk.Frame(table, bg=C_TABLE); board_frame.pack(side="left", padx=10)
        tk.Label(board_frame, text="Community Cards", bg=C_TABLE, fg=C_TEXT, font=("Arial", 10, "bold")).pack()
        board_slots = tk.Frame(board_frame, bg=C_TABLE); board_slots.pack()
        self.board = [CardSlot(board_slots, n, self) for n in ("Flop1", "Flop2", "Flop3", "Turn", "River")]
        for s in self.board: s.pack(side="left", padx=2, pady=2)

        # Controls
        ctrl = tk.LabelFrame(game_frame, text="Game Settings", bg=C_PANEL,
                             font=("Arial", 12, "bold"), fg=C_TEXT, bd=2, relief="groove")
        ctrl.pack(fill="x", pady=10)
        top_ctrl = tk.Frame(ctrl, bg=C_PANEL); top_ctrl.pack(fill="x", padx=10, pady=10)
        style = ttk.Style(self); style.theme_use("alt")
        style.configure("HC.TCombobox", fieldbackground=C_BTN_DARK, background=C_BTN_DARK,
                       foreground="white", borderwidth=0, arrowcolor="white",
                       selectbackground=C_BTN_PRIMARY, selectforeground="white")
        style.map("HC.TCombobox", fieldbackground=[("readonly", C_BTN_DARK)], background=[("active", C_BTN_DARK_HOVER)])
        
        tk.Label(top_ctrl, text="Position:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=0, padx=5, sticky="w")
        pos_cb = ttk.Combobox(top_ctrl, textvariable=self.position, values=[p.name for p in Position], state="readonly", width=8, style="HC.TCombobox")
        pos_cb.grid(row=0, column=1, padx=5, sticky="w"); pos_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())
        tk.Label(top_ctrl, text="Stack:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=2, padx=5, sticky="w")
        stack_cb = ttk.Combobox(top_ctrl, textvariable=self.stack_type, values=[s.value for s in StackType], state="readonly", width=8, style="HC.TCombobox")
        stack_cb.grid(row=0, column=3, padx=5, sticky="w"); stack_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())
        tk.Label(top_ctrl, text="Players:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=4, padx=5, sticky="w")
        spin_frame = tk.Frame(top_ctrl, bg=C_BTN_DARK, bd=1, relief="solid"); spin_frame.grid(row=0, column=5, padx=5, sticky="w")
        players_entry = tk.Entry(spin_frame, textvariable=self.num_players, width=3, bg=C_BTN_DARK, fg="white", bd=0, font=("Arial", 11), justify="center"); players_entry.pack(side="left", padx=5, pady=5)
        spin_up = tk.Button(spin_frame, text="▲", bg=C_BTN_DARK, fg="white", bd=0, font=("Arial", 8), width=2, command=lambda: self.num_players.set(min(9, self.num_players.get() + 1))); spin_up.pack(side="top", fill="x")
        spin_down = tk.Button(spin_frame, text="▼", bg=C_BTN_DARK, fg="white", bd=0, font=("Arial", 8), width=2, command=lambda: self.num_players.set(max(2, self.num_players.get() - 1))); spin_down.pack(side="bottom", fill="x")

        bottom_ctrl = tk.Frame(ctrl, bg=C_PANEL); bottom_ctrl.pack(fill="x", padx=10, pady=(0, 10))
        def _validate(num_var: tk.DoubleVar):
            try:
                if num_var.get() < 0: raise ValueError
            except Exception:
                messagebox.showwarning("Input error", "Value must be non-negative"); num_var.set(0.0)
            finally: self.refresh()
        entry_style = {"bg": C_BTN_DARK, "fg": "white", "bd": 1, "insertbackground": "white", "font": ("Arial", 11)}
        tk.Label(bottom_ctrl, text="SB:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=0, padx=5, sticky="w")
        sb_e = tk.Entry(bottom_ctrl, textvariable=self.small_blind, width=8, **entry_style); sb_e.grid(row=0, column=1, padx=5, sticky="w"); sb_e.bind("<FocusOut>", lambda *_: _validate(self.small_blind))
        tk.Label(bottom_ctrl, text="BB:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=2, padx=5, sticky="w")
        bb_e = tk.Entry(bottom_ctrl, textvariable=self.big_blind, width=8, **entry_style); bb_e.grid(row=0, column=3, padx=5, sticky="w"); bb_e.bind("<FocusOut>", lambda *_: _validate(self.big_blind))
        tk.Label(bottom_ctrl, text="To Call:", bg=C_PANEL, fg=C_TEXT, font=("Arial", 11, "bold")).grid(row=0, column=4, padx=5, sticky="w")
        call_e = tk.Entry(bottom_ctrl, textvariable=self.call_amt, width=10, **entry_style); call_e.grid(row=0, column=5, padx=5, sticky="w"); call_e.bind("<FocusOut>", lambda *_: _validate(self.call_amt))
        
        self.go_btn = StyledButton(bottom_ctrl, text="START", color=C_BTN_SUCCESS, hover_color=C_BTN_SUCCESS_HOVER, width=8, height=2, font=("Arial", 12, "bold"), command=self.start_game); self.go_btn.grid(row=0, column=6, padx=10)
        clear_btn = StyledButton(bottom_ctrl, text="CLEAR", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER, width=8, height=2, command=self.clear_all); clear_btn.grid(row=0, column=7, padx=5)

        self.action_frame = tk.Frame(ctrl, bg=C_PANEL); self.action_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.action_btn = StyledButton(self.action_frame, text="RECORD PLAYER ACTIONS", color=C_BTN_PRIMARY, hover_color=C_BTN_PRIMARY_HOVER, font=("Arial", 12, "bold"), command=self.record_player_actions, state="disabled"); self.action_btn.pack()

        # Analysis output frame
        analysis_frame = tk.LabelFrame(right, text="Poker Analysis & Strategy", font=("Arial", 12, "bold"), bg=C_PANEL, fg=C_TEXT, bd=2, relief="groove")
        analysis_frame.pack(fill="both", expand=True, pady=(10, 0))
        header_frame = tk.Frame(analysis_frame, bg=C_BTN_PRIMARY); header_frame.pack(fill="x", padx=5, pady=(5, 0))
        self.out_head = tk.Text(header_frame, height=3, font=("Arial", 11, "bold"), bg=C_BTN_PRIMARY, fg="white", wrap="word", relief="flat", padx=15, pady=10); self.out_head.pack(fill="x")
        
        content_frame = tk.Frame(analysis_frame, bg=C_BG); content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        left_col = tk.Frame(content_frame, bg=C_BG); left_col.pack(side="left", fill="both", expand=True, padx=(0, 5))
        scrollbar = tk.Scrollbar(left_col); scrollbar.pack(side="right", fill="y")
        self.out_body = tk.Text(left_col, font=("Consolas", 10), bg=C_BG, fg=C_TEXT, wrap="word", yscrollcommand=scrollbar.set, relief="solid", bd=1, padx=15, pady=10); self.out_body.pack(side="left", fill="both", expand=True); scrollbar.config(command=self.out_body.yview)
        
        btn_frame = tk.Frame(left_col, bg=C_BG); btn_frame.pack(fill="x", pady=5)
        won_btn = StyledButton(btn_frame, text="MARK AS WON", color=C_BTN_SUCCESS, hover_color=C_BTN_SUCCESS_HOVER, width=15, command=lambda: self._mark_showdown(1)); won_btn.pack(side="left", padx=5)
        lost_btn = StyledButton(btn_frame, text="MARK AS LOST", color=C_BTN_DANGER, hover_color=C_BTN_DANGER_HOVER, width=15, command=lambda: self._mark_showdown(0)); lost_btn.pack(side="left", padx=5)

        right_col = tk.Frame(content_frame, bg=C_PANEL, width=300, bd=2, relief="groove"); right_col.pack(side="right", fill="y", padx=(5, 0)); right_col.pack_propagate(False)
        tk.Label(right_col, text="Quick Stats", font=("Arial", 12, "bold"), bg=C_PANEL, fg=C_TEXT).pack(pady=10)
        self.stats_text = tk.Text(right_col, font=("Consolas", 11), bg=C_PANEL, fg=C_TEXT, wrap="word", relief="flat", padx=15, pady=10); self.stats_text.pack(fill="both", expand=True)

        for tw in (self.out_body, self.stats_text, self.out_head):
            tw.tag_configure("header", font=("Arial", 12, "bold"), foreground=C_BTN_PRIMARY, spacing3=8)
            tw.tag_configure("metric", foreground=C_TEXT)
            tw.tag_configure("positive", foreground=C_BTN_SUCCESS)
            tw.tag_configure("negative", foreground=C_BTN_DANGER)
            tw.tag_configure("decision", font=("Arial", 16, "bold"), foreground=C_BTN_PRIMARY, spacing1=10)
            tw.tag_configure("reason", font=("Arial", 9, "italic"), foreground="#cccccc", spacing1=3)
            tw.tag_configure("advice", foreground="#bbbbbb", spacing1=3)
            tw.tag_configure("warning", font=("Arial", 10, "bold"), foreground=C_BTN_WARNING)

    # ─────────────────────────────────────────────────────────────────────
    # grid helpers
    def grey_out(self, card: Card):
        self.used.add(str(card))
        w = self.grid_cards[str(card)]
        w.configure(bg="#666666", relief="sunken", state="disabled", text=f"{card}\n✕")
    def un_grey(self, card: Card):
        key = str(card)
        if key in self.used:
            self.used.remove(key)
            w = self.grid_cards[key]
            w.configure(bg=C_CARD, relief="raised", state="normal", text=str(card))
    def place_next_free(self, card: Card):
        if str(card) in self.used: return
        for slot in self.hole + self.board:
            if slot.card is None:
                slot.set_card(card); self.grey_out(card); self.refresh(); return
        messagebox.showinfo("No slot", "All card slots are full.")

    # ─────────────────────────────────────────────────────────────────────
    # Game control methods
    def start_game(self):
        self.game_started = True
        self.go_btn.configure(text="PLAYING", state="disabled", bg=C_BTN_DARK)
        self.go_btn._bg = self.go_btn._hover_bg = C_BTN_DARK
        self.action_btn.configure(state="normal")
        self.current_pot = self.small_blind.get() + self.big_blind.get()
        self.players_in_hand = list(range(1, self.num_players.get() + 1))
        self.player_actions.clear()
        messagebox.showinfo("Game Started", f"Game started with {self.num_players.get()} players.\nInitial pot: ${self.current_pot:.1f}")
        self.record_player_actions()
    
    def record_player_actions(self):
        """Record actions for all other players after your turn"""
        if not self.game_started:
            messagebox.showwarning("Not Started", "Please start the game first!")
            return
        your_seat = Position[self.position.get()].value
        actions_recorded = False
        for i in range(1, self.num_players.get() + 1):
            if i == your_seat or i not in self.players_in_hand: continue
            dialog = PlayerActionDialog(self, i, self.current_pot)
            self.wait_window(dialog)
            if dialog.result:
                actions_recorded = True
                action, amount = dialog.result
                self.player_actions[i] = (action, amount)
                if action == PlayerAction.FOLD: self.players_in_hand.remove(i)
                elif action == PlayerAction.CALL: self.current_pot += self.call_amt.get()
                elif action == PlayerAction.RAISE:
                    self.current_pot += amount; self.call_amt.set(amount - self.call_amt.get())
        if actions_recorded:
            self.action_complete = True; self.refresh()
            messagebox.showinfo("Actions Recorded", f"Actions recorded. Players remaining: {len(self.players_in_hand)}. Current pot: ${self.current_pot:.1f}")

    # ─────────────────────────────────────────────────────────────────────
    # analysis cycle
    def refresh(self):
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]
        pos = Position[self.position.get()]
        stack_bb = StackType(self.stack_type.get()).default_bb
        pot = self.current_pot if self.game_started else self.small_blind.get() + self.big_blind.get()
        call = self.call_amt.get()

        for w in (self.out_head, self.out_body, self.stats_text):
            w.configure(state="normal"); w.delete("1.0", "end")

        game_state = f"Position: {pos.name} | Stack: {stack_bb}BB | Pot: ${pot:.1f} | To Call: ${call:.1f}"
        if self.game_started: game_state += f" | Players: {len(self.players_in_hand)}"

        if len(hole) == 2:
            tier = hand_tier(hole)
            board_str = ' '.join(map(str, board))
            analysis = analyse_hand(hole, board, pos, stack_bb, pot, call)
            self._last_decision_id = record_decision(analysis, pos, tier, stack_bb, pot, call, board_str)
            
            self.out_head.insert("end",
                f"Hand: {to_two_card_str(hole)} ({tier.upper()}) | Board: {board_str or 'Pre-flop'}\n"
                f"Board Texture: {analysis.board_texture.text} | {game_state}")

            self.out_body.insert("end", "DECISION RATIONALE\n", "header")
            decision_color = {"RAISE": "warning", "CALL": "positive", "FOLD": "negative", "CHECK": "metric"}[analysis.decision]
            self.out_body.insert("end", f"{analysis.decision}\n", ("decision", decision_color))
            self.out_body.insert("end", f"{analysis.reason}\n", "reason")

            self.out_body.insert("end", "\nEQUITY ANALYSIS\n", "header")
            diff = analysis.equity - analysis.required_eq
            self.out_body.insert("end", f"Your equity      : {analysis.equity:7.1%}\n", "metric")
            self.out_body.insert("end", f"Required equity  : {analysis.required_eq:7.1%}\n", "metric")
            self.out_body.insert("end", f"Edge             : {diff:+7.1%}\n", "positive" if diff >= 0 else "negative")

            self.out_body.insert("end", "\nEXPECTED VALUE (EV)\n", "header")
            self.out_body.insert("end", f"EV Call   : ${analysis.ev_call:+8.2f}\n", "positive" if analysis.ev_call >= 0 else "negative")
            self.out_body.insert("end", f"EV Raise  : ${analysis.ev_raise:+8.2f}\n", "positive" if analysis.ev_raise >= 0 else "negative")

            self.out_body.insert("end", "\nCONTEXTUAL ADVICE\n", "header")
            self.out_body.insert("end", get_position_advice(pos) + "\n", "advice")
            self.out_body.insert("end", get_hand_advice(tier, analysis.board_texture, analysis.spr), "advice")
        else:
            self.out_head.insert("end", f"⚠ Select two hole cards\n{game_state}")
            self.out_body.insert("end", "Press START when ready, then drag two cards to the 'Your Hand' slots to begin analysis.", "advice")

        # quick stats
        self.stats_text.insert("end", "SESSION STATS\n", "header")
        with open_db() as db:
            wins, total = db.execute(
                "SELECT SUM(showdown_win), COUNT(showdown_win) FROM decisions WHERE showdown_win IS NOT NULL"
            ).fetchone()
        self.stats_text.insert("end", f"\nMarked Hands Won: {wins or 0}/{total or 0}\n", "metric")
        if total: self.stats_text.insert("end", f"Win Rate: {wins/total:7.1%}\n", "metric")

        with open_db() as db:
            recent = db.execute(
                "SELECT decision, COUNT(*) FROM decisions WHERE id > (SELECT MAX(id) - 20 FROM decisions) GROUP BY decision"
            ).fetchall()
        if recent:
            self.stats_text.insert("end", "\nRecent Decisions (20):\n", "header")
            for dec, cnt in recent: self.stats_text.insert("end", f"{dec:<6}: {cnt}\n", "metric")

        for w in (self.out_head, self.out_body, self.stats_text): w.configure(state="disabled")

    def _mark_showdown(self, won: int):
        if self._last_decision_id is None:
            messagebox.showinfo("No Decision", "Please analyze a hand first before marking the result.")
            return
        with open_db() as db:
            db.execute("UPDATE decisions SET showdown_win=? WHERE id=?", (won, self._last_decision_id))
        log.info(f"Marked decision ID {self._last_decision_id} as {'WON' if won else 'LOST'}")
        self.refresh()

    def clear_all(self):
        for s in self.hole + self.board:
            if s.card: s.clear()
        self.game_started = False
        self.go_btn.configure(state="normal", text="START", bg=C_BTN_SUCCESS)
        self.go_btn._bg = C_BTN_SUCCESS
        self.go_btn._hover_bg = C_BTN_SUCCESS_HOVER
        self.action_btn.configure(state="disabled")
        self.current_pot = 0.0
        self.players_in_hand.clear()
        self.player_actions.clear()
        self.action_complete = False
        self.refresh()

# ─────────────────────────────────────────────────────────────────────────────
# 10.  Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info("Starting Poker Assistant v9 (High Contrast Edition)")
    # Ensure database is created on first run
    with open_db() as db:
        log.info(f"Database at '{DB_PATH.resolve()}' is ready.")
    app = PokerAssistant()
    app.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error in application")
        sys.exit(1)
