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
    sys.exit("PokerV8 needs the ‘treys’ package.  pip install treys")

_TREYS = TreysEval()  # singleton

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Globals / constants
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)7s | %(message)s")
log = logging.getLogger(__name__)

RANKS = "23456789TJQKA"
CARD_SIZE = 52
GUI_W, GUI_H = 1280, 830
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
        self.resizable(False, False)

        # shared state
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.pot_size = tk.DoubleVar(value=10.0)
        self.call_amt = tk.DoubleVar(value=2.0)

        self.grid_cards: dict[str, DraggableCard] = {}
        self.used: set[str] = set()

        self._build_gui()
        self.refresh()

    # ─────────────────────────────────────────────────────────────────────
    def _build_gui(self):
        left = tk.Frame(self)
        left.pack(side="left", fill="y", padx=4, pady=4)
        right = tk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        # grid
        tk.Label(left, text="Card Selection", font=("Arial", 12, "bold")).pack()
        for suit in Suit:
            frame = tk.LabelFrame(left, text=f"{suit.value} {suit.name.title()}", fg=suit.color)
            frame.pack(padx=2, pady=2)
            for r in RANKS:
                card = Card(r, suit)
                w = DraggableCard(frame, card, self)
                w.pack(side="left", padx=1, pady=1)
                self.grid_cards[str(card)] = w

        # table
        table = tk.Frame(right, bg="darkgreen", bd=4, relief="ridge")
        table.pack(pady=6)

        self.hole = [CardSlot(table, f"Hole{i+1}", self) for i in range(2)]
        for s in self.hole:
            s.pack(side="left", padx=4, pady=4)

        self.board = [CardSlot(table, n, self) for n in ("Flop1", "Flop2", "Flop3", "Turn", "River")]
        for s in self.board:
            s.pack(side="left", padx=3, pady=3)

        # controls
        ctrl = tk.LabelFrame(right, text="Controls")
        ctrl.pack(fill="x", pady=6)
        ttk.Label(ctrl, text="Position").grid(row=0, column=0, padx=4, pady=2)
        pos_cb = ttk.Combobox(ctrl, textvariable=self.position, values=[p.name for p in Position], state="readonly")
        pos_cb.grid(row=0, column=1, padx=4)
        pos_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        ttk.Label(ctrl, text="Stack").grid(row=1, column=0, padx=4, pady=2)
        stack_cb = ttk.Combobox(ctrl, textvariable=self.stack_type, values=[s.value for s in StackType], state="readonly")
        stack_cb.grid(row=1, column=1, padx=4)
        stack_cb.bind("<<ComboboxSelected>>", lambda *_: self.refresh())

        def _validate(num_var: tk.DoubleVar):
            try:
                if num_var.get() < 0:
                    raise ValueError
            except Exception:
                messagebox.showwarning("Input error", "Value must be non-negative")
                num_var.set(0.0)
            finally:
                self.refresh()

        ttk.Label(ctrl, text="Pot").grid(row=0, column=2, padx=4)
        pot_e = ttk.Entry(ctrl, textvariable=self.pot_size, width=9)
        pot_e.grid(row=0, column=3, padx=4)
        pot_e.bind("<FocusOut>", lambda *_: _validate(self.pot_size))

        ttk.Label(ctrl, text="To Call").grid(row=1, column=2, padx=4)
        call_e = ttk.Entry(ctrl, textvariable=self.call_amt, width=9)
        call_e.grid(row=1, column=3, padx=4)
        call_e.bind("<FocusOut>", lambda *_: _validate(self.call_amt))

        ttk.Button(ctrl, text="Clear", command=self.clear_all).grid(row=0, column=4, rowspan=2, padx=8)

        # output
        self.out_head = tk.Text(right, height=4, font=("Consolas", 10), state="disabled", bg="#f0f0f0")
        self.out_body = tk.Text(right, font=("Consolas", 10), wrap="word")
        self.out_head.pack(fill="x")
        self.out_body.pack(fill="both", expand=True, pady=4)

    # ─────────────────────────────────────────────────────────────────────
    # grid helpers
    def grey_out(self, card: Card):
        self.used.add(str(card))
        w = self.grid_cards[str(card)]
        w.configure(bg="#b0b0b0", relief="sunken", state="disabled", text=f"{card}\n✕")

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

        self.out_head.configure(state="normal")
        self.out_head.delete(1.0, "end")
        self.out_body.delete(1.0, "end")

        if len(hole) != 2:
            self.out_head.insert("end", "Select exactly two hole cards …")
            self.out_head.configure(state="disabled")
            return

        pos = Position[self.position.get()]
        stack_bb = StackType[self.stack_type.get()].default_bb
        pot = self.pot_size.get()
        call = self.call_amt.get()

        analysis = analyse_hand(hole, board, pos, stack_bb, pot, call)

        # header
        self.out_head.insert(
            "end",
            (
                f"Hand {to_two_card_str(hole):<4}  "
                f"Board: {' '.join(map(str, board)) or '-'}  "
                f"Pos: {pos.name:3}  "
                f"Stack: {stack_bb} BB  "
                f"Pot: {pot:.1f}  Call: {call:.1f}\n"
            ),
        )
        self.out_head.configure(state="disabled")

        # body
        self.out_body.insert(
            "end",
            (
                f"Equity            : {analysis.equity:6.1%}\n"
                f"Required equity    : {analysis.required_eq:6.1%}\n"
                f"EV (call)          : {analysis.ev_call:+.2f}\n"
                f"EV (raise) *model* : {analysis.ev_push:+.2f}\n"
                f"SPR                : {analysis.spr:4.1f}\n"
                f"Aggression score   : {analysis.aggression:4.2f}\n"
                f"---------------------------------------------\n"
                f"Suggested action   : {analysis.decision}\n"
            ),
        )

        # save quietly
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
