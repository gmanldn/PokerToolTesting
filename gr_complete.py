from __future__ import annotations
"""PokerTool2 – Enhanced version with position-aware calculations and opponent tracking
---------------------------------------------------------------------------------
This script combines database setup, GUI, and plugin functionality in one file.
Run it directly to launch the Poker Assistant GUI.
"""

import logging
import random
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox

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
    1: 0.85,  # UTG - tightest
    2: 0.90,  # MP
    3: 0.95,  # CO
    4: 1.10,  # BTN - best position
    5: 0.95,  # SB
    6: 1.00   # BB - baseline
}

class Card:
    """Simple playing‑card object."""

    def __init__(self, rank: str, suit: str) -> None:
        self.rank = rank
        self.suit = suit
        self.value = RANK_VALUES[rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return f"Card({self.rank}, {self.suit})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))


def create_deck() -> List[Card]:
    """Return a full 52‑card deck."""
    return [Card(r, s) for s in SUITS for r in RANKS]


def evaluate_hand(hole_cards: List[Card], community_cards: List[Card]) -> str:
    """Evaluate the best 5-card hand from hole + community cards."""
    if len(hole_cards) != 2:
        return "Invalid hand"
    
    all_cards = hole_cards + community_cards
    if len(all_cards) < 2:
        return "Insufficient cards"
    
    # For pre-flop, just describe hole cards
    if not community_cards:
        rank_a, rank_b = hole_cards
        is_pair = rank_a.rank == rank_b.rank
        is_suited = rank_a.suit == rank_b.suit
        
        if is_pair:
            return f"Pair of {rank_a.rank}s"
        else:
            high = max(hole_cards, key=lambda c: c.value)
            low = min(hole_cards, key=lambda c: c.value)
            suited_text = " suited" if is_suited else ""
            return f"{high.rank}{low.rank}{suited_text}"
    
    # Simple post-flop hand evaluation
    # Check for pairs, two pair, trips, etc.
    rank_counts = {}
    for card in all_cards:
        rank_counts[card.rank] = rank_counts.get(card.rank, 0) + 1
    
    # Sort by count, then by rank value
    sorted_ranks = sorted(rank_counts.items(), key=lambda x: (x[1], RANK_VALUES[x[0]]), reverse=True)
    
    if sorted_ranks[0][1] >= 4:
        return f"Four of a kind - {sorted_ranks[0][0]}s"
    elif sorted_ranks[0][1] == 3:
        if len(sorted_ranks) > 1 and sorted_ranks[1][1] >= 2:
            return f"Full house - {sorted_ranks[0][0]}s over {sorted_ranks[1][0]}s"
        else:
            return f"Three of a kind - {sorted_ranks[0][0]}s"
    elif sorted_ranks[0][1] == 2:
        if len(sorted_ranks) > 1 and sorted_ranks[1][1] == 2:
            return f"Two pair - {sorted_ranks[0][0]}s and {sorted_ranks[1][0]}s"
        else:
            return f"Pair of {sorted_ranks[0][0]}s"
    else:
        high_card = max(all_cards, key=lambda c: c.value)
        return f"High card {high_card.rank}"


def calculate_win_probability(
    hole_cards: List[Card], 
    community_cards: List[Card], 
    position: int = 6,
    active_opponents: int = 1
) -> float:
    """Enhanced equity calculation considering position and active opponents."""
    if len(hole_cards) != 2:
        return 0.0

    rank_a, rank_b = hole_cards
    is_pair = rank_a.rank == rank_b.rank
    is_suited = rank_a.suit == rank_b.suit
    high_card = max(rank_a.value, rank_b.value)
    low_card = min(rank_a.value, rank_b.value)
    
    # Base strength calculation
    strength = 0.0
    
    # Pair bonus (stronger for higher pairs)
    if is_pair:
        pair_rank = rank_a.value
        if pair_rank >= 10:  # JJ+
            strength += 0.35
        elif pair_rank >= 7:  # 88-TT
            strength += 0.25
        else:  # 22-77
            strength += 0.15
    else:
        # High card value
        strength += high_card * 0.025  # up to +0.3 for Ace
        strength += low_card * 0.015   # up to +0.18 for King
        
        # Connected cards bonus
        gap = abs(rank_a.value - rank_b.value)
        if gap == 1:  # Connected
            strength += 0.08
        elif gap == 2:  # One gap
            strength += 0.04
        elif gap == 3:  # Two gap
            strength += 0.02
    
    # Suited bonus
    strength += 0.08 if is_suited else 0.0
    
    # Broadway cards bonus (T, J, Q, K, A)
    broadway_count = sum(1 for card in hole_cards if card.value >= 8)
    strength += broadway_count * 0.03
    
    # Position adjustment
    position_mult = POSITION_MULTIPLIERS.get(position, 1.0)
    strength *= position_mult
    
    # Community cards adjustment
    if community_cards:
        # Simple heuristic: if we have overcards to the board
        board_high = max(card.value for card in community_cards) if community_cards else -1
        our_high = max(card.value for card in hole_cards)
        if our_high > board_high:
            strength += 0.05 * len(community_cards)
        else:
            strength += 0.02 * len(community_cards)
    
    # Opponent adjustment (more opponents = lower win rate)
    if active_opponents > 0:
        opponent_factor = 1.0 - (active_opponents - 1) * 0.12
        strength *= max(0.3, opponent_factor)
    
    return max(0.02, min(strength, 0.98))

# ---------------------------------------------------------------------------
# Database / ORM
# ---------------------------------------------------------------------------
Base = declarative_base()

class HandHistory(Base):
    """Stores recorded hands."""

    __tablename__ = "hand_history"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    position = Column(Integer, nullable=False)
    hole_cards = Column(String(10), nullable=False)
    community_cards = Column(String(25))
    predicted_win_prob = Column(Float, nullable=False)
    actual_result = Column(String(10), nullable=False)
    chip_stack = Column(String(10), nullable=False)
    active_opponents = Column(Integer, nullable=False, default=1)
    notes = Column(Text)

# SQLite path under user home
DB_DIR = Path.home() / ".pokertool"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "pokertool.db"

ENGINE = create_engine(f"sqlite:///{DB_PATH}", future=True, echo=False)
SessionLocal = scoped_session(
    sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)
)

@contextmanager
def session_context() -> Generator[Session, None, None]:
    """Provide a SQLAlchemy session, auto‑committing or rolling back on error."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        log.error(f"Database error: {e}")
        session.rollback()
        raise
    finally:
        session.close()

# Ensure tables exist
try:
    Base.metadata.create_all(ENGINE)
    log.info(f"Database initialized at {DB_PATH}")
except Exception as e:
    log.error(f"Failed to initialize database: {e}")

# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------
PLUGIN_REGISTRY: Dict[str, Callable[["PokerAssistant"], None]] = {}

def register_plugin(name: str):
    def decorator(func: Callable[["PokerAssistant"], None]):
        if name in PLUGIN_REGISTRY:
            raise ValueError(f"Plugin '{name}' already registered")
        PLUGIN_REGISTRY[name] = func
        return func
    return decorator

@register_plugin("Hand History")
def plugin_hand_history(app: "PokerAssistant") -> None:
    try:
        win = tk.Toplevel(app.root)
        win.title("Hand History")
        win.geometry("800x500")

        cols = ("Time", "Pos", "Hole", "Comm", "Pred", "Result", "Active")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, anchor="center", width=100)
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        with session_context() as s:
            hands = s.scalars(select(HandHistory).order_by(HandHistory.timestamp.desc())).all()
            for hh in hands:
                tree.insert(
                    "",
                    "end",
                    values=(
                        hh.timestamp.strftime("%Y-%m-%d %H:%M") if hh.timestamp else "Unknown",
                        f"{hh.position} ({POSITION_NAMES.get(hh.position, '?')})",
                        hh.hole_cards,
                        hh.community_cards or "",
                        f"{hh.predicted_win_prob:.1%}",
                        hh.actual_result,
                        getattr(hh, 'active_opponents', 'N/A'),
                    ),
                )
    except Exception as e:
        log.error(f"Error opening hand history: {e}")
        messagebox.showerror("Error", f"Failed to open hand history: {e}")

@register_plugin("Clear History")
def plugin_clear_history(app: "PokerAssistant") -> None:
    try:
        if not messagebox.askyesno(
            "Confirm Delete", "Delete ALL recorded hand history? This cannot be undone."
        ):
            return
        with session_context() as s:
            deleted = s.query(HandHistory).delete()
        messagebox.showinfo("History Cleared", f"Deleted {deleted} records.")
    except Exception as e:
        log.error(f"Error clearing history: {e}")
        messagebox.showerror("Error", f"Failed to clear history: {e}")

# ---------------------------------------------------------------------------
# GUI class
# ---------------------------------------------------------------------------
class PokerAssistant:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.deck: List[Card] = create_deck()
        random.shuffle(self.deck)

        # State vars
        self.position = tk.IntVar(value=1)
        self.num_opponents = tk.IntVar(value=5)
        self.chip_stack = tk.StringVar(value="medium")
        self.hole_cards: List[Card] = []
        self.community_cards: List[Card] = []
        self.current_win_prob = 0.0
        self.dragging_card: Optional[Card] = None
        self.card_buttons: Dict[str, tk.Button] = {}
        self.hole_labels: List[tk.Label] = []
        self.community_labels: List[tk.Label] = []
        self.opponent_labels: List[tk.Label] = []
        self.opponent_states: List[bool] = []  # True = active, False = folded
        self.prob_label = None
        self.advice_lbl = None
        self.hand_lbl = None

        self._build_ui()
        self._init_opponents()

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.title("Poker Assistant - Enhanced")
        self.root.geometry("1200x850")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        for i in range(6):
            main.rowconfigure(i, weight=0)
        main.columnconfigure(1, weight=1)

        self._create_deck_area(main)
        self._create_controls(main)
        self._create_opponents_area(main)
        self._create_hole_area(main)
        self._create_community_area(main)
        self._create_probability_area(main)
        self._create_action_buttons(main)
        self._create_menu()

    # Deck grid of clickable buttons
    def _create_deck_area(self, parent: ttk.Frame) -> None:
        deck_frame = ttk.LabelFrame(parent, text="Deck (dbl‑click = auto‑place)")
        deck_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        for row, suit in enumerate(SUITS):
            suit_frame = ttk.Frame(deck_frame)
            suit_frame.grid(row=row, column=0, sticky="w")
            for col, rank in enumerate(RANKS):
                card = Card(rank, suit)
                btn = tk.Button(
                    suit_frame,
                    text=f"{('10' if rank == 'T' else rank)}\n{suit}",
                    width=5,
                    height=2,
                    font=("Helvetica", 8, "bold"),
                    fg="#CC0000" if suit in "♥♦" else "#000000",
                )
                btn.grid(row=0, column=col, padx=1, pady=1)
                btn.bind("<Double-Button-1>", lambda e, c=card: self._auto_place(c))
                self.card_buttons[str(card)] = btn

    # Position / opponent / stack controls
    def _create_controls(self, parent: ttk.Frame) -> None:
        ctrl = ttk.LabelFrame(parent, text="Table Info", padding=5)
        ctrl.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(ctrl, text="Position:").grid(row=0, column=0, sticky="w")
        pos_spin = ttk.Spinbox(ctrl, from_=1, to=6, textvariable=self.position, width=5)
        pos_spin.grid(row=0, column=1, padx=5, sticky="w")
        pos_spin.bind("<KeyRelease>", lambda e: self._position_changed())
        pos_spin.bind("<<Increment>>", lambda e: self._position_changed())
        pos_spin.bind("<<Decrement>>", lambda e: self._position_changed())

        # Position name label
        self.pos_name_lbl = ttk.Label(ctrl, text=f"({POSITION_NAMES[1]})", font=("Helvetica", 9))
        self.pos_name_lbl.grid(row=0, column=2, sticky="w")

        ttk.Label(ctrl, text="Total Opponents:").grid(row=0, column=3, padx=(20, 0), sticky="w")
        opp_spin = ttk.Spinbox(ctrl, from_=1, to=9, textvariable=self.num_opponents, width=5)
        opp_spin.grid(row=0, column=4, padx=5, sticky="w")
        opp_spin.bind("<KeyRelease>", lambda e: self._opponents_changed())
        opp_spin.bind("<<Increment>>", lambda e: self._opponents_changed())
        opp_spin.bind("<<Decrement>>", lambda e: self._opponents_changed())

        ttk.Label(ctrl, text="Stack:").grid(row=0, column=5, padx=(20, 0), sticky="w")
        stack_combo = ttk.Combobox(
            ctrl,
            textvariable=self.chip_stack,
            values=("low", "medium", "high"),
            width=8,
            state="readonly",
        )
        stack_combo.grid(row=0, column=6, padx=5, sticky="w")

    def _create_opponents_area(self, parent: ttk.Frame) -> None:
        opp_frame = ttk.LabelFrame(parent, text="Opponents (dbl‑click to fold/unfold)")
        opp_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.opponents_inner = ttk.Frame(opp_frame)
        self.opponents_inner.pack(pady=5)

    def _create_hole_area(self, parent: ttk.Frame) -> None:
        hole = ttk.LabelFrame(parent, text="Hole Cards")
        hole.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        
        hole_inner = ttk.Frame(hole)
        hole_inner.pack(pady=5)
        
        self.hole_labels = []
        for i in range(2):
            lbl = tk.Label(
                hole_inner,
                text="Empty",
                width=10,
                height=4,
                relief="sunken",
                bg="lightgray",
                font=("Helvetica", 10, "bold")
            )
            lbl.grid(row=0, column=i, padx=5)
            self.hole_labels.append(lbl)

    def _create_community_area(self, parent: ttk.Frame) -> None:
        comm = ttk.LabelFrame(parent, text="Community Cards")
        comm.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        
        comm_inner = ttk.Frame(comm)
        comm_inner.pack(pady=5)
        
        self.community_labels = []
        for i in range(5):
            lbl = tk.Label(
                comm_inner,
                text="Empty",
                width=10,
                height=4,
                relief="sunken",
                bg="lightblue",
                font=("Helvetica", 10, "bold")
            )
            lbl.grid(row=0, column=i, padx=3)
            self.community_labels.append(lbl)

    def _create_probability_area(self, parent: ttk.Frame) -> None:
        prob_frame = ttk.LabelFrame(parent, text="Hand Analysis", padding=5)
        prob_frame.grid(row=1, column=1, rowspan=3, sticky="new", padx=(10, 0))
        prob_frame.columnconfigure(0, weight=1)

        # Current best hand
        self.hand_lbl = tk.Label(prob_frame, text="--", font=("Arial", 12, "bold"), wraplength=180)
        self.hand_lbl.grid(row=0, column=0, pady=(0, 5), sticky="ew")

        # Win probability (smaller)
        self.prob_label = tk.Label(prob_frame, text="--", font=("Arial", 20, "bold"))
        self.prob_label.grid(row=1, column=0, pady=(0, 5))

        # Advice
        self.advice_lbl = tk.Label(prob_frame, text="Add hole cards", wraplength=180, justify="center", font=("Arial", 10))
        self.advice_lbl.grid(row=2, column=0, pady=(0, 5))

        # Active opponents display
        self.active_lbl = tk.Label(prob_frame, text="Active: --", font=("Arial", 10))
        self.active_lbl.grid(row=3, column=0)

    def _create_action_buttons(self, parent: ttk.Frame) -> None:
        act = ttk.Frame(parent)
        act.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(act, text="Clear All", command=self._clear_cards).grid(row=0, column=0, padx=5)
        ttk.Button(act, text="Reset Opponents", command=self._reset_opponents).grid(row=0, column=1, padx=5)
        ttk.Button(act, text="Record Win", command=lambda: self._record("win")).grid(row=0, column=2, padx=5)
        ttk.Button(act, text="Record Loss", command=lambda: self._record("loss")).grid(row=0, column=3, padx=5)
        ttk.Button(act, text="Record Tie", command=lambda: self._record("tie")).grid(row=0, column=4, padx=5)

    def _create_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        stats = tk.Menu(menubar, tearoff=False)
        for name, func in PLUGIN_REGISTRY.items():
            stats.add_command(label=name, command=lambda f=func: f(self))
        menubar.add_cascade(label="Statistics", menu=stats)

    # ------------------------------------------------------------------
    # Opponent management
    # ------------------------------------------------------------------
    def _init_opponents(self) -> None:
        """Initialize opponent tracking."""
        self._opponents_changed()

    def _opponents_changed(self) -> None:
        """Handle change in number of opponents."""
        try:
            # Clear existing opponent widgets
            for widget in self.opponents_inner.winfo_children():
                widget.destroy()
            
            num_opp = self.num_opponents.get()
            self.opponent_labels = []
            self.opponent_states = [True] * num_opp  # All start active
            
            for i in range(num_opp):
                lbl = tk.Label(
                    self.opponents_inner,
                    text=f"P{i+1}\n🃏",
                    width=8,
                    height=3,
                    relief="raised",
                    bg="lightgreen",
                    font=("Helvetica", 9, "bold"),
                    cursor="hand2"
                )
                lbl.grid(row=0, column=i, padx=3, pady=3)
                lbl.bind("<Double-Button-1>", lambda e, idx=i: self._toggle_opponent(idx))
                self.opponent_labels.append(lbl)
            
            self._update_probability()
        except Exception as e:
            log.error(f"Error updating opponents: {e}")

    def _toggle_opponent(self, index: int) -> None:
        """Toggle opponent between active and folded."""
        try:
            if index >= len(self.opponent_states):
                return
                
            self.opponent_states[index] = not self.opponent_states[index]
            lbl = self.opponent_labels[index]
            
            if self.opponent_states[index]:
                # Active
                lbl.config(
                    text=f"P{index+1}\n🃏",
                    bg="lightgreen",
                    relief="raised"
                )
            else:
                # Folded
                lbl.config(
                    text=f"P{index+1}\n❌",
                    bg="lightcoral",
                    relief="sunken"
                )
            
            self._update_probability()
        except Exception as e:
            log.error(f"Error toggling opponent {index}: {e}")

    def _reset_opponents(self) -> None:
        """Reset all opponents to active state."""
        try:
            for i in range(len(self.opponent_states)):
                self.opponent_states[i] = True
                if i < len(self.opponent_labels):
                    self.opponent_labels[i].config(
                        text=f"P{i+1}\n🃏",
                        bg="lightgreen",
                        relief="raised"
                    )
            self._update_probability()
        except Exception as e:
            log.error(f"Error resetting opponents: {e}")

    def _position_changed(self) -> None:
        """Handle position change."""
        try:
            pos = self.position.get()
            pos_name = POSITION_NAMES.get(pos, "?")
            self.pos_name_lbl.config(text=f"({pos_name})")
            self._update_probability()
        except Exception as e:
            log.error(f"Error updating position: {e}")

    def _get_active_opponents(self) -> int:
        """Get count of active (non-folded) opponents."""
        return sum(1 for state in self.opponent_states if state)

    # ------------------------------------------------------------------
    # Card management helpers
    # ------------------------------------------------------------------
    def _auto_place(self, card: Card) -> None:
        try:
            if card in self.hole_cards or card in self.community_cards:
                return
            if len(self.hole_cards) < 2:
                self.hole_cards.append(card)
            elif len(self.community_cards) < 5:
                self.community_cards.append(card)
            else:
                return
            self._update_ui_after_card_change(card)
        except Exception as e:
            log.error(f"Error placing card {card}: {e}")

    def _update_ui_after_card_change(self, card: Card) -> None:
        try:
            # Disable button
            btn = self.card_buttons.get(str(card))
            if btn:
                btn.config(state="disabled")
            
            # Update hole card labels
            for i, lbl in enumerate(self.hole_labels):
                if i < len(self.hole_cards):
                    card_text = str(self.hole_cards[i])
                    suit = self.hole_cards[i].suit
                    color = "#CC0000" if suit in "♥♦" else "#000000"
                    lbl.config(text=card_text, bg="#FFFFFF", fg=color)
                else:
                    lbl.config(text="Empty", bg="lightgray", fg="black")
            
            # Update community card labels
            for i, lbl in enumerate(self.community_labels):
                if i < len(self.community_cards):
                    card_text = str(self.community_cards[i])
                    suit = self.community_cards[i].suit
                    color = "#CC0000" if suit in "♥♦" else "#000000"
                    lbl.config(text=card_text, bg="#FFFFFF", fg=color)
                else:
                    lbl.config(text="Empty", bg="lightblue", fg="black")
            
            self._update_probability()
        except Exception as e:
            log.error(f"Error updating UI after card change: {e}")

    def _update_probability(self) -> None:
        try:
            active_opponents = self._get_active_opponents()
            self.active_lbl.config(text=f"Active: {active_opponents}")
            
            if len(self.hole_cards) == 2:
                # Update best hand evaluation
                best_hand = evaluate_hand(self.hole_cards, self.community_cards)
                self.hand_lbl.config(text=f"Best Hand: {best_hand}")
                
                prob = calculate_win_probability(
                    self.hole_cards, 
                    self.community_cards, 
                    self.position.get(),
                    active_opponents
                )
                self.current_win_prob = prob
                self.prob_label.config(text=f"{prob:.1%}")
                
                # Enhanced advice based on position and opponents
                pos_name = POSITION_NAMES.get(self.position.get(), "?")
                
                if prob > 0.75:
                    advice = f"Very strong ({pos_name}) – bet for value"
                    color = "darkgreen"
                elif prob > 0.60:
                    advice = f"Strong ({pos_name}) – consider betting"
                    color = "green"
                elif prob > 0.45:
                    advice = f"Decent ({pos_name}) – position matters"
                    color = "blue"
                elif prob > 0.30:
                    advice = f"Marginal ({pos_name}) – proceed carefully"
                    color = "orange"
                else:
                    advice = f"Weak ({pos_name}) – consider folding"
                    color = "red"
                
                self.advice_lbl.config(text=advice, fg=color)
            else:
                self.hand_lbl.config(text="Best Hand: --")
                self.prob_label.config(text="--")
                self.advice_lbl.config(text="Add hole cards", fg="black")
        except Exception as e:
            log.error(f"Error updating probability: {e}")

    def _clear_cards(self) -> None:
        try:
            # Re-enable all used card buttons
            for card in self.hole_cards + self.community_cards:
                btn = self.card_buttons.get(str(card))
                if btn:
                    btn.config(state="normal")
            
            # Clear card lists
            self.hole_cards.clear()
            self.community_cards.clear()
            
            # Update UI
            for lbl in self.hole_labels:
                lbl.config(text="Empty", bg="lightgray", fg="black")
            for lbl in self.community_labels:
                lbl.config(text="Empty", bg="lightblue", fg="black")
            
            # Reset opponents
            self._reset_opponents()
            
            self._update_probability()
        except Exception as e:
            log.error(f"Error clearing cards: {e}")

    def _record(self, result: str) -> None:
        try:
            if len(self.hole_cards) != 2:
                messagebox.showwarning("Invalid", "Need exactly 2 hole cards to record")
                return
            
            active_opponents = self._get_active_opponents()
            
            with session_context() as s:
                hh = HandHistory(
                    position=self.position.get(),
                    hole_cards="".join(str(c) for c in self.hole_cards),
                    community_cards=" ".join(str(c) for c in self.community_cards) if self.community_cards else None,
                    predicted_win_prob=self.current_win_prob,
                    actual_result=result,
                    chip_stack=self.chip_stack.get(),
                    active_opponents=active_opponents,
                )
                s.add(hh)
            
            pos_name = POSITION_NAMES.get(self.position.get(), "?")
            messagebox.showinfo("Recorded", f"Hand saved as {result}\nPosition: {pos_name}, Active opponents: {active_opponents}")
            self._clear_cards()
        except Exception as e:
            log.error(f"Error recording hand: {e}")
            messagebox.showerror("Error", f"Failed to record hand: {e}")

    # ------------------------------------------------------------------
    # Backward‑compat helper
    # ------------------------------------------------------------------
    def _create_deck(self, parent: ttk.Frame) -> None:
        """Alias for older call sites – forwards to _create_deck_area."""
        self._create_deck_area(parent)

# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        root = tk.Tk()
        app = PokerAssistant(root)
        log.info("Enhanced Poker Assistant started successfully")
        root.mainloop()
    except Exception as e:
        log.error(f"Failed to start application: {e}")
        if 'root' in locals():
            messagebox.showerror("Startup Error", f"Failed to start Enhanced Poker Assistant: {e}")

if __name__ == "__main__":
    main()