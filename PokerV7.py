# PokerV7.py  –  Visual Poker Assistant (click + drag + bully logic)
from __future__ import annotations

import logging
import random
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Callable, List, Sequence

import tkinter as tk
from tkinter import ttk, messagebox

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)7s | %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional, but recommended, fast evaluator
# ---------------------------------------------------------------------------
try:
    from treys import Card as TCard, Evaluator as TreysEval  # type: ignore

    HAS_TREYS = True
    _TREYS = TreysEval()
except ModuleNotFoundError:
    HAS_TREYS = False
    _TREYS = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RANKS = "23456789TJQKA"
CARD_SIZE = 52
GUI_WIDTH, GUI_HEIGHT = 1280, 820

# Bully multipliers (unchanged from your v5)
POSITION_BULLY_FACTORS = {
    1: 1.0,   # BTN
    2: 0.7,   # SB
    3: 0.5,   # BB
    4: 0.4,   # UTG
    5: 0.6,   # MP
    6: 0.85,  # CO
}
HAND_BULLY_FACTORS = {
    "premium": 1.0,
    "strong": 0.85,
    "decent": 0.70,
    "marginal": 0.55,
    "weak": 0.45,
    "spec": 0.60,
    "trash": 0.30,
}

# ---------------------------------------------------------------------------
# Card models
# ---------------------------------------------------------------------------
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

    def __post_init__(self):
        if self.rank not in RANKS:
            raise ValueError(f"illegal rank {self.rank}")
        if not isinstance(self.suit, Suit):
            raise TypeError("suit must be Suit")

    def __str__(self) -> str:
        return f"{self.rank}{self.suit.value}"

    @property
    def value(self) -> int:
        return RANKS.index(self.rank)


def full_deck() -> list[Card]:
    return [Card(r, s) for s in Suit for r in RANKS]


# ---------------------------------------------------------------------------
# Position / stack
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Hand tier tables (same as before)
# ---------------------------------------------------------------------------
HAND_TIERS = {
    "premium": ["AA", "KK", "QQ", "JJ", "AKs", "AK"],
    "strong": ["TT", "99", "AQs", "AQ", "AJs", "KQs", "ATs"],
    "decent": ["88", "77", "AJ", "KQ", "QJs", "JTs", "A9s", "KJs"],
    "marginal": ["66", "55", "AT", "KJ", "QT", "JT", "A8s", "K9s", "Q9s"],
    "weak": ["44", "33", "22", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s"],
    "spec": ["T9s", "98s", "87s", "76s", "65s", "54s", "K8s", "Q8s", "J9s"],
}


def as_two_card_string(cards: Sequence[Card]) -> str:
    if len(cards) != 2:
        return ""
    a, b = cards
    if a.rank == b.rank:
        return a.rank * 2
    suited = "s" if a.suit == b.suit else ""
    hi, lo = sorted(cards, key=lambda c: c.value, reverse=True)
    return f"{hi.rank}{lo.rank}{suited}"


def hand_tier(two: Sequence[Card]) -> str:
    code = as_two_card_string(two)
    for tier, hands in HAND_TIERS.items():
        if code in hands:
            return tier
    return "trash"


# ---------------------------------------------------------------------------
# Equity & math helpers
# ---------------------------------------------------------------------------
def _to_treys(card: Card) -> int:
    suit_map = {Suit.SPADE: "s", Suit.HEART: "h", Suit.DIAMOND: "d", Suit.CLUB: "c"}
    return TCard.new(card.rank + suit_map[card.suit])


def monte_carlo_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    deck = [c for c in full_deck() if c not in hole and c not in board]
    wins = ties = 0
    for _ in range(600):  # balance precision / speed
        opp = random.sample(deck, 2)
        sample_board = list(board) + random.sample(
            [c for c in deck if c not in opp], 5 - len(board)
        )
        h1 = _TREYS.evaluate([_to_treys(c) for c in sample_board], [_to_treys(c) for c in hole])
        h2 = _TREYS.evaluate([_to_treys(c) for c in sample_board], [_to_treys(c) for c in opp])
        if h1 < h2:
            wins += 1
        elif h1 == h2:
            ties += 1
    return (wins + ties / 2) / 600


def heuristic_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    """Fallback if treys missing."""
    tier = hand_tier(hole)
    return {
        "premium": 0.85,
        "strong": 0.75,
        "decent": 0.6,
        "marginal": 0.45,
        "weak": 0.32,
        "spec": 0.38,
        "trash": 0.15,
    }[tier]


def hand_equity(hole: Sequence[Card], board: Sequence[Card]) -> float:
    if len(hole) != 2:
        return 0.0
    if HAS_TREYS:
        return monte_carlo_equity(hole, board)
    return heuristic_equity(hole, board)


def pot_odds(call: float, pot: float) -> float:
    return call / (pot + call) if call else 0.0


def expected_value(eq: float, pot: float, call: float) -> float:
    return eq * (pot + call) - call


def spr_val(stack: float, pot: float) -> float:
    return stack / pot if pot else float("inf")


# ---------------------------------------------------------------------------
# Simple SQLite persistence
# ---------------------------------------------------------------------------
DB_PATH = Path("poker_sessions.sqlite3")


@contextmanager
def db_conn():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS game_sessions (
               id INTEGER PRIMARY KEY,
               ts TEXT DEFAULT CURRENT_TIMESTAMP,
               position TEXT,
               hole TEXT,
               board TEXT,
               pot REAL,
               stack REAL,
               note TEXT
           )"""
    )
    try:
        yield con
        con.commit()
    finally:
        con.close()


def save_session(pos: Position, hole: str, board: str, pot: float, stack: float):
    with db_conn() as con:
        con.execute(
            "INSERT INTO game_sessions(position,hole,board,pot,stack) VALUES (?,?,?,?,?)",
            (pos.name, hole, board, pot, stack),
        )


# ---------------------------------------------------------------------------
# GUI widgets
# ---------------------------------------------------------------------------
class DraggableCard(tk.Label):
    def __init__(
        self,
        master: tk.Widget,
        card: Card,
        choose_cb: Callable[[Card], None],
    ):
        super().__init__(
            master,
            text=str(card),
            font=("Arial", 11, "bold"),
            fg=card.suit.color,
            bg="white",
            bd=2,
            relief="raised",
            width=4,
            height=3,
        )
        self.card = card
        self._choose_cb = choose_cb
        self._start_xy = (0, 0)
        self._dragged = False

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -----------------
    def _on_press(self, ev):
        self._start_xy = (ev.x, ev.y)
        self._dragged = False
        self.lift()

    def _on_drag(self, ev):
        dx, dy = ev.x - self._start_xy[0], ev.y - self._start_xy[1]
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragged = True
        self.place(x=self.winfo_x() + dx, y=self.winfo_y() + dy)

    def _on_release(self, ev):
        if self._dragged:
            target = self.winfo_containing(ev.x_root, ev.y_root)
            if hasattr(target, "accept"):
                target.accept(self)  # type: ignore
            else:
                self.place_forget()
                self.pack(side="left", padx=1, pady=1)
        else:  # simple click
            self._choose_cb(self.card)


class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, event_root: tk.Widget):
        super().__init__(
            master,
            width=CARD_SIZE + 10,
            height=int(CARD_SIZE * 1.4),
            bg="darkgreen",
            bd=3,
            relief="sunken",
        )
        self.pack_propagate(False)
        self._empty_lbl = tk.Label(self, text=name, bg="darkgreen", fg="white")
        self._empty_lbl.pack(expand=True)
        self.card: Card | None = None
        self._root = event_root

    # drag-and-drop accept ----------------------------------------------------
    def accept(self, widget: DraggableCard):
        if self.card:
            widget.place_forget()
            widget.pack(side="left", padx=1, pady=1)
            return
        self.set_card(widget.card)
        widget.destroy()
        self._root.event_generate("<<CardsChanged>>")

    # helpers -----------------------------------------------------------------
    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children():
            w.destroy()
        lbl = tk.Label(
            self,
            text=str(card),
            font=("Arial", 14, "bold"),
            fg=card.suit.color,
            bg="white",
            bd=2,
            relief="raised",
        )
        lbl.pack(expand=True, fill="both", padx=3, pady=3)
        lbl.bind("<Double-Button-1>", lambda *_: self.clear())

    def clear(self):
        if not self.card:
            return
        removed = self.card
        self.card = None
        for w in self.winfo_children():
            w.destroy()
        self._empty_lbl = tk.Label(self, text="Empty", bg="darkgreen", fg="white")
        self._empty_lbl.pack(expand=True)
        # notify root so it can un-grey the grid card
        self._root.event_generate("<<CardRemoved>>", data=str(removed))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class PokerAssistant(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v7")
        self.geometry(f"{GUI_WIDTH}x{GUI_HEIGHT}")
        self.resizable(False, False)

        # --- shared state ----------------------------------------------------
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.pot_size = tk.DoubleVar(value=10.0)
        self.call_amt = tk.DoubleVar(value=2.0)

        self._used_cards: set[str] = set()  # "As", "K♥", …

        # --- layout ----------------------------------------------------------
        self._make_layout()
        self.bind("<<CardsChanged>>", self._analyse)
        self.bind("<<CardRemoved>>", self._on_card_removed)

    # ---------------------------------------------------------------------
    def _make_layout(self):
        left = tk.Frame(self)
        left.pack(side="left", fill="y", padx=4, pady=4)

        right = tk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        # --- selection grid ------------------------------------------------
        tk.Label(left, text="Card Selection", font=("Arial", 12, "bold")).pack(pady=2)

        self._grid_widgets: dict[str, DraggableCard] = {}
        for suit in Suit:
            frame = tk.LabelFrame(left, text=f"{suit.value} {suit.name.title()}", fg=suit.color)
            frame.pack(padx=2, pady=2)
            for r in RANKS:
                card = Card(r, suit)
                widget = DraggableCard(frame, card, choose_cb=self._choose_card)
                widget.pack(side="left", padx=1, pady=1)
                self._grid_widgets[str(card)] = widget

        # --- table ---------------------------------------------------------
        table = tk.Frame(right, bg="darkgreen", bd=4, relief="ridge")
        table.pack(pady=6)

        self.hole_slots: list[CardSlot] = [CardSlot(table, f"Hole{i+1}", self) for i in range(2)]
        for s in self.hole_slots:
            s.pack(side="left", padx=4, pady=4)

        self.board_slots: list[CardSlot] = [
            CardSlot(table, n, self) for n in ("Flop1", "Flop2", "Flop3", "Turn", "River")
        ]
        for s in self.board_slots:
            s.pack(side="left", padx=3, pady=3)

        # --- controls ------------------------------------------------------
        ctrl = tk.LabelFrame(right, text="Controls")
        ctrl.pack(fill="x", pady=6)

        ttk.Label(ctrl, text="Position").grid(row=0, column=0, padx=4, pady=2)
        pos_combo = ttk.Combobox(
            ctrl, textvariable=self.position, values=[p.name for p in Position], state="readonly", width=8
        )
        pos_combo.grid(row=0, column=1, padx=4, pady=2)
        pos_combo.bind("<<ComboboxSelected>>", lambda *_: self._analyse())

        ttk.Label(ctrl, text="Stack").grid(row=1, column=0, padx=4, pady=2)
        stack_combo = ttk.Combobox(
            ctrl, textvariable=self.stack_type, values=[s.value for s in StackType], state="readonly", width=8
        )
        stack_combo.grid(row=1, column=1, padx=4, pady=2)
        stack_combo.bind("<<ComboboxSelected>>", lambda *_: self._analyse())

        ttk.Label(ctrl, text="Pot").grid(row=0, column=2, padx=4, pady=2)
        ttk.Entry(ctrl, textvariable=self.pot_size, width=8).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(ctrl, text="To Call").grid(row=1, column=2, padx=4, pady=2)
        ttk.Entry(ctrl, textvariable=self.call_amt, width=8).grid(row=1, column=3, padx=4, pady=2)

        ttk.Button(ctrl, text="Clear", command=self._clear_board).grid(row=0, column=4, rowspan=2, padx=8)

        # --- output --------------------------------------------------------
        self.output = tk.Text(right, height=12, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, pady=4)
        self._analyse()

    # ---------------------------------------------------------------------
    # Selection helpers
    # ---------------------------------------------------------------------
    def _choose_card(self, card: Card):
        if str(card) in self._used_cards:
            return

        target_slot = next((s for s in self.hole_slots if s.card is None), None)
        if not target_slot:
            target_slot = next((s for s in self.board_slots if s.card is None), None)
        if not target_slot:
            messagebox.showinfo("No slot", "All slots are already full.")
            return

        target_slot.set_card(card)
        self._mark_used(card)
        self.event_generate("<<CardsChanged>>")

    def _mark_used(self, card: Card):
        self._used_cards.add(str(card))
        self._grid_widgets[str(card)].configure(bg="#c8c8c8", relief="sunken")

    def _on_card_removed(self, ev):
        card_str = ev.data  # type: ignore
        if card_str in self._used_cards:
            self._used_cards.remove(card_str)
            self._grid_widgets[card_str].configure(bg="white", relief="raised")
        self._analyse()

    # ---------------------------------------------------------------------
    def _gather(self) -> tuple[List[Card], List[Card]]:
        hole = [s.card for s in self.hole_slots if s.card]
        board = [s.card for s in self.board_slots if s.card]
        return hole, board

    def _analyse(self, *_):
        hole, board = self._gather()
        self.output.delete(1.0, "end")

        if len(hole) != 2:
            self.output.insert("end", "Select exactly two hole cards …")
            return

        pot = self.pot_size.get()
        call = self.call_amt.get()
        stack_bb = StackType(self.stack_type.get()).default_bb
        pos = Position[self.position.get()]
        tier = hand_tier(hole)

        equity = hand_equity(hole, board)
        req_eq = pot_odds(call, pot)
        ev = expected_value(equity, pot, call)
        spr = spr_val(stack_bb, pot)

        bully = POSITION_BULLY_FACTORS[pos] * HAND_BULLY_FACTORS[tier]
        stack_factor = min(2.0, stack_bb / 100)  # bigger stacks = more leverage
        aggression = bully * stack_factor

        decision = "CALL" if equity >= req_eq else "FOLD"
        if aggression > 1.1 and equity > req_eq:
            decision = "RAISE"

        # --- output box --------------------------------------------------
        self.output.insert(
            "end",
            (
                f"Hand         : {as_two_card_string(hole)}   ({' '.join(map(str, hole))})\n"
                f"Board        : {' '.join(map(str, board)) or '-'}\n"
                f"Position     : {pos.name}\n"
                f"Stack        : {stack_bb} BB ({self.stack_type.get()})\n"
                f"Pot / Call   : {pot:.1f} / {call:.1f}\n"
                f"----------------------------------------------------\n"
                f"Equity       : {equity:6.1%}\n"
                f"Required Eq. : {req_eq:6.1%}\n"
                f"EV (call)    : {ev:+.2f}\n"
                f"SPR          : {spr:4.1f}\n"
                f"Aggression   : {aggression:4.2f}  (pos*hand*stack)\n"
                f"----------------------------------------------------\n"
                f"Suggested    : {decision}\n"
            ),
        )

        # auto-save silently
        save_session(pos, as_two_card_string(hole), "".join(str(c) for c in board), pot, stack_bb)

    # ---------------------------------------------------------------------
    def _clear_board(self):
        for s in (*self.hole_slots, *self.board_slots):
            s.clear()
        # restore grid colours
        for card_str in list(self._used_cards):
            self._grid_widgets[card_str].configure(bg="white", relief="raised")
        self._used_cards.clear()
        self._analyse()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not HAS_TREYS:
        log.warning("Running without 'treys' – equity numbers are approximate.  pip install treys")
    app = PokerAssistant()
    log.info("Poker Assistant ready.")
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)
