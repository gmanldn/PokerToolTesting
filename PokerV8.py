# PokerV8.py – Visual Poker Assistant, polished version
from __future__ import annotations

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
from typing import List, Sequence

import tkinter as tk
from tkinter import ttk, messagebox

# ─────────────────────────────────────────────────────────────────────────────
# 0.  Fast, exact evaluator (mandatory)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from treys import Card as TCard, Evaluator as TreysEval  # type: ignore
except ModuleNotFoundError as exc:
    sys.exit("PokerV8 needs the 'treys' package.  pip install treys")

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
    if len(two) != 2:
        return ""
    a, b = two
    if a.rank == b.rank:
        return a.rank * 2
    suited = "s" if a.suit == b.suit else ""
    hi, lo = sorted(two, key=lambda c: c.value, reverse=True)
    return f"{hi.rank}{lo.rank}{suited}"


def hand_tier(two: Sequence[Card]) -> str:
    code = to_two_card_str(two)
    for tier, hands in HAND_TIERS.items():
        if code in hands:
            return tier
    return "trash"


def _tcard(c: Card) -> int:
    suit_map = {Suit.SPADE: "s", Suit.HEART: "h", Suit.DIAMOND: "d", Suit.CLUB: "c"}
    return TCard.new(c.rank + suit_map[c.suit])


def adaptive_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    """Monte-Carlo simulation with adaptive sample size."""
    deck = [c for c in FULL_DECK if c not in hole and c not in board]
    # rough equity guess via treys deterministic score to guide sample size
    base = _TREYS.evaluate([], [_tcard(c) for c in hole])
    rough = 1.0 - base / _TREYS.MAX_SCORE
    n_samples = int(min(2500, max(400, 1000 / max(0.05, rough * (1 - rough)))))
    wins = ties = 0
    for _ in range(n_samples):
        opp = random.sample(deck, 2)
        rest = 5 - len(board)
        rnd_board = list(board) + random.sample([c for c in deck if c not in opp], rest)
        h1 = _TREYS.evaluate([_tcard(c) for c in rnd_board], [_tcard(c) for c in hole])
        h2 = _TREYS.evaluate([_tcard(c) for c in rnd_board], [_tcard(c) for c in opp])
        if h1 < h2:
            wins += 1
        elif h1 == h2:
            ties += 1
    return (wins + ties / 2) / n_samples


def pot_odds(call: float, pot: float) -> float:
    return call / (pot + call) if call else 0.0


def expected_value(eq: float, pot: float, invest: float) -> float:
    return eq * (pot + invest) - invest


def logistic_stack_factor(bb: int) -> float:
    """Smooth 1.0 → 2.0 increase around 80bb, capped at 2.0"""
    return 1.0 + 1.0 / (1.0 + math.exp(-(bb - 80) / 20))


@dataclass(slots=True)
class Analysis:
    equity: float
    required_eq: float
    ev_call: float
    ev_push: float
    spr: float
    aggression: float
    decision: str


def analyse_hand(
    hole: Sequence[Card],
    board: Sequence[Card],
    pos: Position,
    stack_bb: int,
    pot: float,
    to_call: float,
) -> Analysis:
    equity = adaptive_equity(hole, board)
    required = pot_odds(to_call, pot)
    ev_call = expected_value(equity, pot, to_call)

    tier = hand_tier(hole)
    aggression = (
        POSITION_BULLY[pos]
        * HAND_BULLY[tier]
        * logistic_stack_factor(stack_bb)
    )

    # simple raise model: min-raise 2×call
    raise_amt = max(to_call * 2, pot * 0.75)
    fold_equity = min(0.30, aggression * 0.25)  # up to 30 %
    ev_push = fold_equity * pot + (1 - fold_equity) * expected_value(equity, pot, raise_amt)

    decision = "CALL" if equity >= required else "FOLD"
    if aggression > 1.05 and ev_push > 0:
        decision = "RAISE"

    spr = stack_bb / pot if pot else float("inf")

    return Analysis(equity, required, ev_call, ev_push, spr, aggression, decision)


def get_position_advice(pos: Position) -> str:
    """Get position-specific advice."""
    advice = {
        Position.BTN: "Button - Most powerful position. Wide opening range, aggressive 3-betting.",
        Position.SB: "Small Blind - Worst position. Play tight, complete selectively.",
        Position.BB: "Big Blind - Defend wide vs steals, but careful postflop OOP.",
        Position.UTG: "Under the Gun - Tightest range. Premium hands only.",
        Position.MP: "Middle Position - Moderate range. Balance value and playability.",
        Position.CO: "Cutoff - Second best position. Open wide, attack blinds."
    }
    return advice.get(pos, "")


def get_hand_advice(tier: str, board_texture: str) -> str:
    """Get hand-specific strategic advice."""
    if tier == "premium":
        return "Premium hand - Build the pot, rarely fold. Watch for set-mining boards."
    elif tier == "strong":
        return "Strong hand - Value bet often, protect against draws on wet boards."
    elif tier == "decent":
        return "Decent hand - Play cautiously multiway, aggressive heads-up."
    elif tier == "marginal":
        return "Marginal hand - Pot control, avoid bloated pots without improvement."
    elif tier == "weak":
        return "Weak hand - Set mine cheaply, fold to aggression without sets."
    elif tier == "spec":
        return "Speculative hand - Play in position, look for multiway pots."
    else:
        return "Trash hand - Fold preflop unless defending BB or stealing."


def analyze_board_texture(board: Sequence[Card]) -> str:
    """Analyze board texture for strategic insights."""
    if not board:
        return "Preflop"
    
    if len(board) == 3:
        # Flop analysis
        ranks = [c.rank for c in board]
        suits = [c.suit for c in board]
        
        if len(set(suits)) == 1:
            return "Monotone flop - Flush possible"
        elif len(set(ranks)) == 1:
            return "Trips on board - Play cautiously"
        elif sorted([RANKS.index(r) for r in ranks]) == list(range(min(RANKS.index(r) for r in ranks), max(RANKS.index(r) for r in ranks) + 1)):
            return "Connected flop - Many draws possible"
        else:
            return "Dry flop - Few draws available"
    
    return f"{len(board)} cards on board"


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Persistence – thin SQLite wrapper
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = Path("poker_sessions.sqlite3")


@contextmanager
def open_db():
    con = sqlite3.connect(DB_PATH, timeout=3.0)
    con.execute(
        """CREATE TABLE IF NOT EXISTS game_sessions (
               id INTEGER PRIMARY KEY,
               ts TEXT DEFAULT CURRENT_TIMESTAMP,
               position TEXT,
               hole TEXT,
               board TEXT,
               pot REAL,
               stack REAL
           );"""
    )
    try:
        yield con
        con.commit()
    finally:
        con.close()


def save_session(pos: Position, hole: str, board: str, pot: float, stack: int) -> None:
    with open_db() as db:
        db.execute(
            "INSERT INTO game_sessions(position,hole,board,pot,stack) VALUES (?,?,?,?,?)",
            (pos.name, hole, board, pot, stack),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5.  GUI widgets
# ─────────────────────────────────────────────────────────────────────────────
class DraggableCard(tk.Label):
    """Label inside grid – supports click & drag."""

    def __init__(self, master: tk.Widget, card: Card, app: "PokerAssistant"):
        super().__init__(
            master,
            text=str(card),
            font=("Arial", 11, "bold"),
            fg=card.suit.color,
            bg="white",
            width=4,
            height=3,
            bd=2,
            relief="raised",
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
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragging = True
        self.place(x=self.winfo_x() + dx, y=self.winfo_y() + dy)

    def _release(self, ev):
        target = self.winfo_containing(ev.x_root, ev.y_root)
        if self._dragging and hasattr(target, "accept"):
            target.accept(self)  # type: ignore
        else:
            self.place_forget()
            self.pack(side="left", padx=1, pady=1)
            self._app.place_next_free(self.card)


class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, app: "PokerAssistant"):
        super().__init__(
            master,
            width=CARD_SIZE + 10,
            height=int(CARD_SIZE * 1.4),
            bg="darkgreen",
            bd=3,
            relief="sunken",
        )
        self.pack_propagate(False)
        self._label = tk.Label(self, text=name, bg="darkgreen", fg="white")
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
        widget._app.grey_out(widget.card)  # type: ignore
        self._app.refresh()

    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children():
            w.destroy()
        inner = tk.Label(
            self,
            text=str(card),
            font=("Arial", 14, "bold"),
            fg=card.suit.color,
            bg="white",
            bd=2,
            relief="raised",
        )
        inner.pack(expand=True, fill="both", padx=3, pady=3)
        inner.bind("<Double-Button-1>", lambda *_: self.clear())

    def clear(self):
        if not self.card:
            return
        self._app.un_grey(self.card)
        self.card = None
        for w in self.winfo_children():
            w.destroy()
        self._label = tk.Label(self, text="Empty", bg="darkgreen", fg="white")
        self._label.pack(expand=True)
        self._app.refresh()


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Main Tk window
# ─────────────────────────────────────────────────────────────────────────────
class PokerAssistant(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v8")
        self.geometry(f"{GUI_W}x{GUI_H}")
        self.resizable(True, True)  # Allow resizing
        self.minsize(1200, 800)  # Set minimum size

        # shared state
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.pot_size = tk.DoubleVar(value=10.0)
        self.call_amt = tk.DoubleVar(value=2.0)

        self.grid_cards: dict[str, DraggableCard] = {}
        self.used: set[str] = set()

        self._build_gui()
        self.after(100, self.refresh)  # Initial refresh after GUI is built

    # ─────────────────────────────────────────────────────────────────────
    def _build_gui(self):
        # Main container with proper weights
        main_frame = tk.Frame(self, bg="#f0f0f0")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left panel for cards (fixed width)
        left = tk.Frame(main_frame, bg="#f5f5f5", width=320)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        
        # Right panel for game and analysis (expandable)
        right = tk.Frame(main_frame, bg="#f5f5f5")
        right.pack(side="left", fill="both", expand=True)

        # Card selection grid
        tk.Label(left, text="Card Selection", font=("Arial", 14, "bold"), bg="#f5f5f5").pack(pady=(0, 10))
        
        card_frame = tk.Frame(left, bg="#f5f5f5")
        card_frame.pack(fill="both", expand=True)
        
        for suit in Suit:
            frame = tk.LabelFrame(card_frame, text=f"{suit.value} {suit.name.title()}", 
                                 fg=suit.color, bg="#f5f5f5", font=("Arial", 10, "bold"))
            frame.pack(fill="x", padx=2, pady=2)
            for r in RANKS:
                card = Card(r, suit)
                w = DraggableCard(frame, card, self)
                w.pack(side="left", padx=1, pady=1)
                self.grid_cards[str(card)] = w

        # Game area
        game_frame = tk.Frame(right, bg="#f5f5f5")
        game_frame.pack(fill="x", pady=(0, 10))
        
        # Table
        table = tk.Frame(game_frame, bg="darkgreen", bd=4, relief="ridge")
        table.pack(pady=10)

        # Hole cards
        hole_frame = tk.Frame(table, bg="darkgreen")
        hole_frame.pack(side="left", padx=5)
        
        tk.Label(hole_frame, text="Your Hand", bg="darkgreen", fg="white", 
                font=("Arial", 10, "bold")).pack()
        hole_slots = tk.Frame(hole_frame, bg="darkgreen")
        hole_slots.pack()
        
        self.hole = [CardSlot(hole_slots, f"Hole{i+1}", self) for i in range(2)]
        for s in self.hole:
            s.pack(side="left", padx=2, pady=2)

        # Board cards
        board_frame = tk.Frame(table, bg="darkgreen")
        board_frame.pack(side="left", padx=10)
        
        tk.Label(board_frame, text="Community Cards", bg="darkgreen", fg="white", 
                font=("Arial", 10, "bold")).pack()
        board_slots = tk.Frame(board_frame, bg="darkgreen")
        board_slots.pack()
        
        self.board = [CardSlot(board_slots, n, self) for n in ("Flop1", "Flop2", "Flop3", "Turn", "River")]
        for s in self.board:
            s.pack(side="left", padx=2, pady=2)

        # Controls
        ctrl = tk.LabelFrame(game_frame, text="Game Settings", bg="#f5f5f5", 
                            font=("Arial", 12, "bold"))
        ctrl.pack(fill="x", pady=10)
        
        # Position and stack controls
        top_ctrl = tk.Frame(ctrl, bg="#f5f5f5")
        top_ctrl.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_ctrl, text="Position:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        pos_cb = ttk.Combobox(top_ctrl, textvariable=self.position, 
                             values=[p.name for p in Position], state="readonly", width=8)
        pos_cb.grid(row=0, column=1, padx=5, sticky="w")
        pos_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        ttk.Label(top_ctrl, text="Stack:").grid(row=0, column=2, padx=5, pady=2, sticky="w")
        stack_cb = ttk.Combobox(top_ctrl, textvariable=self.stack_type, 
                               values=[s.value for s in StackType], state="readonly", width=8)
        stack_cb.grid(row=0, column=3, padx=5, sticky="w")
        stack_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        # Pot and call controls
        bottom_ctrl = tk.Frame(ctrl, bg="#f5f5f5")
        bottom_ctrl.pack(fill="x", padx=10, pady=5)

        def _validate(num_var: tk.DoubleVar):
            try:
                if num_var.get() < 0:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Input error", "Value must be non-negative")
                num_var.set(0.0)
            finally:
                self.refresh()

        ttk.Label(bottom_ctrl, text="Pot Size:").grid(row=0, column=0, padx=5, sticky="w")
        pot_e = ttk.Entry(bottom_ctrl, textvariable=self.pot_size, width=10)
        pot_e.grid(row=0, column=1, padx=5, sticky="w")
        pot_e.bind("<FocusOut>", lambda *_: _validate(self.pot_size))

        ttk.Label(bottom_ctrl, text="To Call:").grid(row=0, column=2, padx=5, sticky="w")
        call_e = ttk.Entry(bottom_ctrl, textvariable=self.call_amt, width=10)
        call_e.grid(row=0, column=3, padx=5, sticky="w")
        call_e.bind("<FocusOut>", lambda *_: _validate(self.call_amt))

        ttk.Button(bottom_ctrl, text="Clear All", command=self.clear_all).grid(row=0, column=4, padx=10)

        # Analysis output area
        analysis_frame = tk.LabelFrame(right, text="Poker Analysis & Strategy", 
                                      font=("Arial", 12, "bold"), bg="#f5f5f5")
        analysis_frame.pack(fill="both", expand=True, pady=(10, 0))

        # Create notebook for tabbed interface
        notebook = ttk.Notebook(analysis_frame)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Analysis tab
        analysis_tab = tk.Frame(notebook, bg="#fafafa")
        notebook.add(analysis_tab, text="Analysis")

        # Header info
        header_frame = tk.Frame(analysis_tab, bg="#e8f4fd", relief="solid", bd=1)
        header_frame.pack(fill="x", padx=5, pady=5)
        
        self.out_head = tk.Text(
            header_frame, 
            height=3, 
            font=("Arial", 11, "bold"), 
            bg="#e8f4fd",
            fg="#2c3e50",
            wrap="word",
            relief="flat",
            padx=15,
            pady=10
        )
        self.out_head.pack(fill="x")

        # Main analysis with scrollbar
        body_frame = tk.Frame(analysis_tab, bg="#fafafa")
        body_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        scrollbar = tk.Scrollbar(body_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.out_body = tk.Text(
            body_frame,
            font=("Consolas", 10),
            bg="#fafafa",
            fg="#2c3e50",
            wrap="word",
            yscrollcommand=scrollbar.set,
            relief="solid",
            bd=1,
            padx=15,
            pady=10
        )
        self.out_body.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.out_body.yview)

        # Quick Stats tab
        stats_tab = tk.Frame(notebook, bg="#fafafa")
        notebook.add(stats_tab, text="Quick Stats")
        
        self.stats_text = tk.Text(
            stats_tab,
            font=("Consolas", 11),
            bg="#fafafa",
            fg="#2c3e50",
            wrap="word",
            relief="flat",
            padx=15,
            pady=10
        )
        self.stats_text.pack(fill="both", expand=True)

        # Configure text tags for styling
        for text_widget in [self.out_body, self.stats_text]:
            text_widget.tag_configure("header", font=("Arial", 12, "bold"), foreground="#2980b9", spacing3=8)
            text_widget.tag_configure("subheader", font=("Arial", 11, "bold"), foreground="#34495e", spacing3=5)
            text_widget.tag_configure("metric", font=("Consolas", 10), foreground="#2c3e50")
            text_widget.tag_configure("positive", foreground="#27ae60", font=("Consolas", 10, "bold"))
            text_widget.tag_configure("negative", foreground="#e74c3c", font=("Consolas", 10, "bold"))
            text_widget.tag_configure("neutral", foreground="#f39c12", font=("Consolas", 10, "bold"))
            text_widget.tag_configure("decision", font=("Arial", 16, "bold"), foreground="#2980b9", spacing1=10)
            text_widget.tag_configure("advice", font=("Arial", 10), foreground="#555555", spacing1=3)
            text_widget.tag_configure("warning", font=("Arial", 10, "bold"), foreground="#e67e22")
            text_widget.tag_configure("tip", font=("Arial", 10, "italic"), foreground="#8e44ad")

    # ─────────────────────────────────────────────────────────────────────
    # grid helpers
    def grey_out(self, card: Card):
        self.used.add(str(card))
        w = self.grid_cards[str(card)]
        w.configure(bg="#d0d0d0", relief="sunken", state="disabled", text=f"{card}\n✕")

    def un_grey(self, card: Card):
        key = str(card)
        if key in self.used:
            self.used.remove(key)
            w = self.grid_cards[key]
            w.configure(bg="white", relief="raised", state="normal", text=str(card))

    # placement by click
    def place_next_free(self, card: Card):
        if str(card) in self.used:
            return
        for slot in self.hole + self.board:
            if slot.card is None:
                slot.set_card(card)
                self.grey_out(card)
                self.refresh()
                return
        messagebox.showinfo("No slot", "All card slots are full.")

    # ─────────────────────────────────────────────────────────────────────
    # analysis cycle
    def refresh(self):
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]
        
        pos = Position[self.position.get()]
        stack_bb = StackType(self.stack_type.get()).default_bb  # Fixed line
        pot = self.pot_size.get()
        call = self.call_amt.get()

        # Clear all text areas
        for widget in [self.out_head, self.out_body, self.stats_text]:
            widget.configure(state="normal")
            widget.delete(1.0, "end")

        # Always show header info
        game_state = f"Position: {pos.name} | Stack: {stack_bb}BB | Pot: {pot:.1f} | To Call: {call:.1f}"
        if len(hole) == 2:
            tier = hand_tier(hole)
            hand_info = f"Hand: {to_two_card_str(hole)} ({tier.upper()})"
            board_info = f"Board: {' '.join(map(str, board)) or 'Preflop'}"
            self.out_head.insert("end", f"{hand_info} | {board_info}\n{game_state}")
        else:
            self.out_head.insert("end", f"⚠ Select two hole cards to start analysis\n{game_state}")

        # Quick stats - always show useful info
        self.stats_text.insert("end", "QUICK REFERENCE\n", "header")
        self.stats_text.insert("end", f"Position: {pos.name} - {get_position_advice(pos)}\n\n", "advice")
        
        self.stats_text.insert("end", "STACK SIZES\n", "subheader")
        self.stats_text.insert("end", f"Current Stack: {stack_bb}BB\n", "metric")
        if pot > 0:
            spr = stack_bb / pot
            self.stats_text.insert("end", f"Stack-to-Pot Ratio: {spr:.1f}\n", "metric")
            if spr < 3:
                self.stats_text.insert("end", "⚠ Low SPR - Commit or fold strategy\n", "warning")
            elif spr > 15:
                self.stats_text.insert("end", "⚠ Deep stacked - Position crucial\n", "warning")
        
        self.stats_text.insert("end", "\nPOT ODDS\n", "subheader")
        if call > 0 and pot > 0:
            odds = pot_odds(call, pot)
            self.stats_text.insert("end", f"Pot Odds: {odds:.1%} ({call:.1f} to win {pot:.1f})\n", "metric")
            self.stats_text.insert("end", f"Breakeven Equity: {odds:.1%}\n", "metric")
        else:
            self.stats_text.insert("end", "No current betting action\n", "metric")

        # Main analysis
        if len(hole) != 2:
            self.out_body.insert("end", "GETTING STARTED\n", "header")
            self.out_body.insert("end", "1. Drag two cards to 'Hole1' and 'Hole2' slots\n", "advice")
            self.out_body.insert("end", "2. Optionally add community cards (Flop, Turn, River)\n", "advice")
            self.out_body.insert("end", "3. Set your table position and stack size\n", "advice")
            self.out_body.insert("end", "4. Enter current pot size and amount to call\n", "advice")
            self.out_body.insert("end", "5. Get instant analysis and recommendations!\n", "advice")
            
            self.out_body.insert("end", f"\nCURRENT POSITION: {pos.name}\n", "subheader")
            self.out_body.insert("end", f"{get_position_advice(pos)}\n\n", "advice")
            
            self.out_body.insert("end", "GENERAL STRATEGY TIPS\n", "subheader")
            self.out_body.insert("end", "• Play tight in early position, looser in late position\n", "tip")
            self.out_body.insert("end", "• Consider pot odds vs hand equity for calling decisions\n", "tip")
            self.out_body.insert("end", "• Adjust aggression based on stack depth and position\n", "tip")
            self.out_body.insert("end", "• Pay attention to board texture and drawing potential\n", "tip")
        else:
            # Full analysis with cards
            analysis = analyse_hand(hole, board, pos, stack_bb, pot, call)
            tier = hand_tier(hole)

            # Equity analysis
            self.out_body.insert("end", "EQUITY ANALYSIS\n", "header")
            self.out_body.insert("end", f"Your Equity:        {analysis.equity:7.1%}\n", "metric")
            self.out_body.insert("end", f"Required Equity:    {analysis.required_eq:7.1%}\n", "metric")
            
            equity_diff = analysis.equity - analysis.required_eq
            equity_tag = "positive" if equity_diff > 0 else "negative"
            self.out_body.insert("end", f"Equity Edge:        {equity_diff:+7.1%}\n", equity_tag)
            
            # Expected value
            self.out_body.insert("end", "\nEXPECTED VALUE\n", "header")
            ev_call_tag = "positive" if analysis.ev_call > 0 else "negative"
            ev_push_tag = "positive" if analysis.ev_push > 0 else "negative"
            self.out_body.insert("end", f"EV of Call:         {analysis.ev_call:+8.2f} chips\n", ev_call_tag)
            self.out_body.insert("end", f"EV of Raise:        {analysis.ev_push:+8.2f} chips\n", ev_push_tag)
            
            # Game dynamics
            self.out_body.insert("end", "\nGAME DYNAMICS\n", "header")
            self.out_body.insert("end", f"Stack-to-Pot:       {analysis.spr:7.1f}\n", "metric")
            self.out_body.insert("end", f"Aggression Factor:  {analysis.aggression:7.2f}\n", "metric")
            self.out_body.insert("end", f"Pot Odds:           {pot_odds(call, pot)*100:6.1f}%\n", "metric")
            
            # Hand strength
            self.out_body.insert("end", "\nHAND STRENGTH\n", "header")
            self.out_body.insert("end", f"Hand Category:      {tier.upper()}\n", "metric")
            self.out_body.insert("end", f"Hand Notation:      {to_two_card_str(hole)}\n", "metric")
            
            # Decision
            self.out_body.insert("end", "\n" + "="*50 + "\n", "metric")
            decision_color = "positive" if analysis.decision == "RAISE" else "neutral" if analysis.decision == "CALL" else "negative"
            self.out_body.insert("end", f"RECOMMENDED ACTION: {analysis.decision}\n", "decision")
            self.out_body.insert("end", "="*50 + "\n", "metric")
            
            # Strategic advice
            self.out_body.insert("end", "\nSTRATEGIC ADVICE\n", "header")
            
            # Position-specific advice
            self.out_body.insert("end", f"Position Strategy: {get_position_advice(pos)}\n\n", "advice")
            
            # Hand-specific advice
            board_texture = analyze_board_texture(board)
            hand_advice = get_hand_advice(tier, board_texture)
            self.out_body.insert("end", f"Hand Strategy: {hand_advice}\n\n", "advice")
            
            # Board texture advice
            if board:
                self.out_body.insert("end", f"Board Analysis: {board_texture}\n\n", "advice")
            
            # Contextual warnings and tips
            if analysis.spr < 3:
                self.out_body.insert("end", "⚠ Low SPR Situation: Consider commitment threshold. Avoid small bets.\n", "warning")
            elif analysis.spr > 15:
                self.out_body.insert("end", "⚠ Deep Stack Play: Focus on position and implied odds.\n", "warning")
                
            if analysis.equity > 0.70:
                self.out_body.insert("end", "💪 Strong Equity: Bet for value and protection!\n", "positive")
            elif analysis.equity < 0.30 and call > 0:
                self.out_body.insert("end", "⚠ Weak Equity: Consider folding unless great implied odds.\n", "warning")
                
            if tier in ["premium", "strong"] and not board:
                self.out_body.insert("end", "💡 Premium Preflop: Consider 3-betting or 4-betting for value.\n", "tip")

        # Disable editing
        for widget in [self.out_head, self.out_body, self.stats_text]:
            widget.configure(state="disabled")

        # Save session if we have hole cards
        if len(hole) == 2:
            save_session(pos, to_two_card_str(hole), "".join(str(c) for c in board), pot, stack_bb)

    # ─────────────────────────────────────────────────────────────────────
    def clear_all(self):
        for s in self.hole + self.board:
            if s.card:
                s.clear()
        self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info("Starting Poker Assistant v8 …")
    app = PokerAssistant()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)
