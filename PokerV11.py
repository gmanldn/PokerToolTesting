#!/usr/bin/env python3
"""
Poker Assistant v11 - Complete Fixed Version
A comprehensive poker hand analysis tool with GUI
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. Standard Library Imports
# ─────────────────────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import ttk, messagebox
import weakref
from typing import List, Dict, Tuple, Optional
import logging
import sqlite3
from enum import Enum
from dataclasses import dataclass
import random

# ─────────────────────────────────────────────────────────────────────────────
# 2. Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Core Poker Classes and Enums
# ─────────────────────────────────────────────────────────────────────────────

class Suit(Enum):
    """Card suits with display properties"""
    SPADE = "♠"
    HEART = "♥"
    DIAMOND = "♦"
    CLUB = "♣"
    
    @property
    def color(self):
        return "red" if self in (Suit.HEART, Suit.DIAMOND) else "black"

class Rank(Enum):
    """Card ranks"""
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "T"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"

# Define RANKS for compatibility
RANKS = [r.value for r in Rank]

@dataclass
class Card:
    """Playing card with rank and suit"""
    rank: str
    suit: Suit
    
    def __str__(self):
        return f"{self.rank}{self.suit.value}"

class Position(Enum):
    """Table positions"""
    BTN = 9  # Button
    SB = 1   # Small Blind
    BB = 2   # Big Blind
    UTG = 3  # Under the Gun
    MP1 = 4  # Middle Position 1
    MP2 = 5  # Middle Position 2
    CO = 7   # Cutoff
    HJ = 6   # Hijack
    UTG1 = 8 # UTG+1

class StackType(Enum):
    """Stack size categories"""
    SHORT = "Short (10-30BB)"
    MEDIUM = "Medium (30-60BB)"
    DEEP = "Deep (60-100BB)"
    VERY_DEEP = "Very Deep (100+BB)"
    
    @property
    def default_bb(self):
        """Get default big blind amount for stack type"""
        mapping = {
            "Short (10-30BB)": 20,
            "Medium (30-60BB)": 50,
            "Deep (60-100BB)": 80,
            "Very Deep (100+BB)": 150
        }
        return mapping.get(self.value, 50)

class PlayerAction(Enum):
    """Possible player actions"""
    FOLD = "Fold"
    CALL = "Call"
    RAISE = "Raise"
    CHECK = "Check"
    ALL_IN = "All-in"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Hand Analysis Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HandAnalysis:
    """Results of hand analysis"""
    decision: str
    reason: str
    equity: float
    required_eq: float
    ev_call: float
    ev_raise: float
    board_texture: str = "Unknown"
    spr: float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# 5. Core Poker Functions
# ─────────────────────────────────────────────────────────────────────────────

def hand_tier(hole_cards: List[Card]) -> str:
    """Categorize hand strength into tiers"""
    if len(hole_cards) != 2:
        return "UNKNOWN"
    
    # Simplified hand tier logic
    r1, r2 = hole_cards[0].rank, hole_cards[1].rank
    suited = hole_cards[0].suit == hole_cards[1].suit
    
    # Premium hands
    premium = {"A", "K", "Q"}
    if r1 in premium and r2 in premium:
        return "PREMIUM"
    
    # Strong hands
    strong = {"A", "K", "Q", "J", "T"}
    if r1 in strong and r2 in strong:
        return "STRONG"
    
    # Pairs
    if r1 == r2:
        if r1 in {"A", "K", "Q", "J"}:
            return "PREMIUM"
        elif r1 in {"T", "9", "8", "7"}:
            return "STRONG"
        else:
            return "MEDIUM"
    
    # Suited connectors
    if suited and abs(RANKS.index(r1) - RANKS.index(r2)) == 1:
        return "PLAYABLE"
    
    # Default
    return "MARGINAL" if suited else "WEAK"

def analyse_hand(hole_cards: List[Card], board: List[Card], position: Position, 
                stack_bb: int, pot: float, to_call: float) -> HandAnalysis:
    """Analyze hand and provide decision recommendation"""
    # Simplified analysis logic
    tier = hand_tier(hole_cards)
    pot_odds = to_call / (pot + to_call) if pot + to_call > 0 else 0
    
    # Simple equity estimation based on tier
    equity_map = {
        "PREMIUM": 0.75,
        "STRONG": 0.65,
        "MEDIUM": 0.55,
        "PLAYABLE": 0.45,
        "MARGINAL": 0.35,
        "WEAK": 0.25,
        "UNKNOWN": 0.50
    }
    
    equity = equity_map.get(tier, 0.5)
    
    # Adjust for position
    if position in [Position.BTN, Position.CO]:
        equity += 0.05
    elif position in [Position.SB, Position.BB]:
        equity -= 0.05
    
    # Make decision
    if equity > pot_odds + 0.1:
        decision = "RAISE"
        reason = f"Strong hand ({tier}) with good equity"
    elif equity > pot_odds:
        decision = "CALL"
        reason = f"Positive expected value with {tier} hand"
    else:
        decision = "FOLD"
        reason = f"Insufficient equity with {tier} hand"
    
    # Calculate EVs
    ev_call = (equity * (pot + to_call)) - to_call
    ev_raise = (equity * (pot + to_call * 2.5)) - (to_call * 2.5)
    
    return HandAnalysis(
        decision=decision,
        reason=reason,
        equity=equity,
        required_eq=pot_odds,
        ev_call=ev_call,
        ev_raise=ev_raise,
        board_texture="Mixed",
        spr=stack_bb / (pot / 2) if pot > 0 else 10
    )

def to_two_card_str(cards: List[Card]) -> str:
    """Convert two cards to string representation"""
    if len(cards) != 2:
        return "??"
    return f"{cards[0]}{cards[1]}"

def get_position_advice(position: Position) -> str:
    """Get position-specific advice"""
    advice_map = {
        Position.BTN: "You have position advantage. Be aggressive with a wide range.",
        Position.CO: "Good position. Open with strong hands and some speculative hands.",
        Position.SB: "Poor position. Play tight and be careful post-flop.",
        Position.BB: "You'll be out of position. Defend selectively.",
        Position.UTG: "Early position. Play only premium hands.",
    }
    return advice_map.get(position, "Play according to your position.")

def get_hand_advice(tier: str, board_texture: str, spr: float) -> str:
    """Get hand-specific advice"""
    if tier in ["PREMIUM", "STRONG"]:
        return "Strong hand. Consider raising for value. Protect your hand on wet boards."
    elif tier in ["MEDIUM", "PLAYABLE"]:
        return "Decent hand. Play cautiously and consider pot control."
    else:
        return "Weak hand. Look for good spots to bluff or fold if facing aggression."

# ─────────────────────────────────────────────────────────────────────────────
# 6. Database Functions
# ─────────────────────────────────────────────────────────────────────────────

def open_db():
    """Open database connection and ensure tables exist"""
    conn = sqlite3.connect("poker_decisions.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            position TEXT,
            hand_tier TEXT,
            stack_bb INTEGER,
            pot REAL,
            to_call REAL,
            board TEXT,
            decision TEXT,
            showdown_win INTEGER
        )
    """)
    conn.commit()
    return conn

def record_decision(analysis: HandAnalysis, position: Position, tier: str,
                   stack_bb: int, pot: float, to_call: float, board: str) -> int:
    """Record decision in database"""
    with open_db() as db:
        cursor = db.execute("""
            INSERT INTO decisions (position, hand_tier, stack_bb, pot, to_call, board, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (position.name, tier, stack_bb, pot, to_call, board, analysis.decision))
        return cursor.lastrowid

# ─────────────────────────────────────────────────────────────────────────────
# 7.  Custom Dialogs and Reusable Button Class (IMPROVED)
# ─────────────────────────────────────────────────────────────────────────────

# Enhanced color palette for better contrast and visual hierarchy
C_BG = "#1a1a1a"         # Darker background
C_PANEL = "#242424"       # Slightly lighter panels
C_TABLE = "#1a5f3f"       # Darker poker table green
C_CARD = "#ffffff"        # Pure white cards
C_CARD_INACTIVE = "#3a3a3a"  # Greyed out cards
C_TEXT = "#e8e8e8"        # Light text
C_TEXT_DIM = "#888888"    # Dimmed text
C_BORDER = "#3a3a3a"      # Subtle borders

# Button colors with better contrast
C_BTN_PRIMARY = "#0e7490"     # Teal - primary actions
C_BTN_SUCCESS = "#10b981"     # Green - positive actions
C_BTN_DANGER = "#ef4444"      # Red - negative actions
C_BTN_WARNING = "#f59e0b"     # Amber - caution
C_BTN_INFO = "#3b82f6"        # Blue - information
C_BTN_DARK = "#374151"        # Gray - neutral

# Hover states (20% lighter)
C_BTN_PRIMARY_HOVER = "#0ea5c5"
C_BTN_SUCCESS_HOVER = "#34d399"
C_BTN_DANGER_HOVER = "#f87171"
C_BTN_WARNING_HOVER = "#fbbf24"
C_BTN_INFO_HOVER = "#60a5fa"
C_BTN_DARK_HOVER = "#4b5563"

class StyledButton(tk.Button):
    """High contrast button with consistent styling"""
    def __init__(self, parent, text="", color=C_BTN_PRIMARY, hover_color=None, **kwargs):
        # Extract fg color if provided, otherwise default to white
        fg_color = kwargs.pop("fg", "white")
        defaults = {
            "font": ("Arial", 10, "bold"), 
            "fg": fg_color, 
            "bg": color,
            "activebackground": hover_color or color, 
            "activeforeground": fg_color,
            "bd": 0, 
            "padx": 12, 
            "pady": 6, 
            "cursor": "hand2", 
            "relief": "flat"
        }
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)
        self._bg = color
        self._hover_bg = hover_color or color
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

# ─────────────────────────────────────────────────────────────────────────────
# 8.  Player Action Dialog
# ─────────────────────────────────────────────────────────────────────────────

class PlayerActionDialog(tk.Toplevel):
    """Dialog for recording player actions"""
    def __init__(self, parent, player_num: int, current_pot: float):
        super().__init__(parent)
        self.title(f"Player {player_num} Action")
        self.geometry("400x300")
        self.configure(bg=C_PANEL)
        self.result = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Header
        tk.Label(
            self,
            text=f"What did Player {player_num} do?",
            font=("Arial", 14, "bold"),
            bg=C_PANEL,
            fg=C_TEXT
        ).pack(pady=20)
        
        # Action buttons
        action_frame = tk.Frame(self, bg=C_PANEL)
        action_frame.pack(pady=10)
        
        StyledButton(
            action_frame,
            text="FOLD",
            color=C_BTN_DANGER,
            hover_color=C_BTN_DANGER_HOVER,
            command=lambda: self._set_result(PlayerAction.FOLD, 0)
        ).pack(pady=5, padx=20, fill="x")
        
        StyledButton(
            action_frame,
            text="CALL",
            color=C_BTN_SUCCESS,
            hover_color=C_BTN_SUCCESS_HOVER,
            command=lambda: self._set_result(PlayerAction.CALL, 0)
        ).pack(pady=5, padx=20, fill="x")
        
        StyledButton(
            action_frame,
            text="RAISE",
            color=C_BTN_WARNING,
            hover_color=C_BTN_WARNING_HOVER,
            command=self._show_raise_input
        ).pack(pady=5, padx=20, fill="x")
        
        # Raise amount input (hidden initially)
        self.raise_frame = tk.Frame(self, bg=C_PANEL)
        tk.Label(
            self.raise_frame,
            text="Raise amount:",
            bg=C_PANEL,
            fg=C_TEXT
        ).pack(side="left", padx=5)
        
        self.raise_var = tk.DoubleVar(value=current_pot)
        self.raise_entry = tk.Entry(
            self.raise_frame,
            textvariable=self.raise_var,
            width=10,
            bg=C_BTN_DARK,
            fg="white",
            insertbackground="white"
        )
        self.raise_entry.pack(side="left", padx=5)
        
        StyledButton(
            self.raise_frame,
            text="Confirm",
            color=C_BTN_PRIMARY,
            command=self._confirm_raise
        ).pack(side="left", padx=5)
        
        # Center dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    
    def _set_result(self, action: PlayerAction, amount: float):
        self.result = (action, amount)
        self.destroy()
    
    def _show_raise_input(self):
        self.raise_frame.pack(pady=10)
        self.raise_entry.focus_set()
        self.raise_entry.select_range(0, tk.END)
    
    def _confirm_raise(self):
        try:
            amount = float(self.raise_var.get())
            self._set_result(PlayerAction.RAISE, amount)
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number")

# ─────────────────────────────────────────────────────────────────────────────
# 9.  GUI widgets (IMPROVED)
# ─────────────────────────────────────────────────────────────────────────────

class DraggableCard(tk.Label):
    """Card widget with improved visibility and interactions"""
    def __init__(self, master: tk.Widget, card: Card, app: "PokerAssistant"):
        super().__init__(
            master, 
            text=str(card), 
            font=("Arial", 12, "bold"), 
            fg=card.suit.color,
            bg=C_CARD, 
            width=3, 
            height=2, 
            bd=1, 
            relief="solid",
            highlightthickness=0
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
            target.accept(self)
        else:
            self.place_forget()
            self.pack(side="left", padx=2, pady=2)
            self._app.place_next_free(self.card)

class CardSlot(tk.Frame):
    """Card slot with improved visual feedback"""
    def __init__(self, master: tk.Widget, name: str, app: "PokerAssistant"):
        super().__init__(
            master, 
            width=60, 
            height=80,
            bg="#0d3a26",  # Darker green for empty slots
            bd=2, 
            relief="groove",
            highlightbackground=C_BORDER,
            highlightthickness=1
        )
        self.pack_propagate(False)
        self._label = tk.Label(
            self, 
            text=name, 
            bg="#0d3a26", 
            fg=C_TEXT_DIM,
            font=("Arial", 9)
        )
        self._label.pack(expand=True)
        self.card: Optional[Card] = None
        self._app = weakref.proxy(app)
        
    def accept(self, widget: DraggableCard):
        if self.card:
            widget.place_forget()
            widget.pack(side="left", padx=2, pady=2)
            return
        self.set_card(widget.card)
        widget.place_forget()
        widget._app.grey_out(widget.card)
        self._app.refresh()
        
    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children(): 
            w.destroy()
        inner = tk.Label(
            self, 
            text=str(card), 
            font=("Arial", 16, "bold"),
            fg=card.suit.color, 
            bg=C_CARD, 
            bd=1, 
            relief="solid"
        )
        inner.pack(expand=True, fill="both", padx=2, pady=2)
        inner.bind("<Double-Button-1>", lambda *_: self.clear())
        
    def clear(self):
        if not self.card: 
            return
        self._app.un_grey(self.card)
        self.card = None
        for w in self.winfo_children(): 
            w.destroy()
        self._label = tk.Label(
            self, 
            text="Empty", 
            bg="#0d3a26", 
            fg=C_TEXT_DIM,
            font=("Arial", 9)
        )
        self._label.pack(expand=True)
        self._app.refresh()

# ─────────────────────────────────────────────────────────────────────────────
# 10.  Main Tk window (IMPROVED LAYOUT)
# ─────────────────────────────────────────────────────────────────────────────

class PokerAssistant(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v11 - Professional Edition")
        self.geometry("1400x800")
        self.minsize(1200, 700)
        self.configure(bg=C_BG)
        
        # Configure window style
        self.option_add("*Font", "Arial 10")
        
        # Shared state
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
        self.player_actions: Dict[int, Tuple[PlayerAction, float]] = {}
        self.action_complete = False
        
        self.grid_cards: Dict[str, DraggableCard] = {}
        self.used: set[str] = set()
        self._last_decision_id: Optional[int] = None
        
        self._build_gui()
        
        # Set up auto-refresh
        self._refresh_scheduled = False
        self.bind("<Configure>", lambda e: self._schedule_refresh())
        self.bind("<Button>", lambda e: self._schedule_refresh())
        self.after(100, self.refresh)
        
    def _schedule_refresh(self):
        """Debounced refresh to avoid excessive updates"""
        if not self._refresh_scheduled:
            self._refresh_scheduled = True
            self.after(50, self._do_refresh)
            
    def _do_refresh(self):
        self._refresh_scheduled = False
        self.refresh()

    def _build_gui(self):
        # Main container with padding
        main_container = tk.Frame(self, bg=C_BG)
        main_container.pack(fill="both", expand=True, padx=15, pady=10)
        
        # LEFT PANEL - Card Selection
        left_panel = tk.Frame(main_container, bg=C_PANEL, width=340)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)
        
        # Card selection header
        header_frame = tk.Frame(left_panel, bg=C_PANEL)
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(
            header_frame, 
            text="CARD DECK", 
            font=("Arial", 11, "bold"),
            bg=C_PANEL, 
            fg=C_TEXT
        ).pack(side="left")
        
        # Card grid with better organization
        card_container = tk.Frame(left_panel, bg=C_PANEL)
        card_container.pack(fill="both", expand=True, padx=10)
        
        suits_order = [Suit.SPADE, Suit.HEART, Suit.DIAMOND, Suit.CLUB]
        
        for suit in suits_order:
            suit_frame = tk.LabelFrame(
                card_container, 
                text=f" {suit.value} {suit.name.title()} ",
                fg=suit.color if suit.color == "red" else C_TEXT,
                bg=C_PANEL, 
                font=("Arial", 10, "bold"),
                bd=1,
                relief="groove",
                labelanchor="w",
                padx=5,
                pady=5
            )
            suit_frame.pack(fill="x", pady=3)
            
            # Create two rows for cards
            rows_container = tk.Frame(suit_frame, bg=C_PANEL)
            rows_container.pack(padx=5, pady=5)
            
            card_row1 = tk.Frame(rows_container, bg=C_PANEL)
            card_row1.pack()
            
            card_row2 = tk.Frame(rows_container, bg=C_PANEL)
            card_row2.pack(pady=(3, 0))  # Small gap between rows
            
            # Split ranks between two rows (7 in first row, 6 in second)
            for i, r in enumerate(RANKS):
                card = Card(r, suit)
                w = DraggableCard(card_row1 if i < 7 else card_row2, card, self)
                w.pack(side="left", padx=2)
                self.grid_cards[str(card)] = w
        
        # RIGHT PANEL - Game Area
        right_panel = tk.Frame(main_container, bg=C_BG)
        right_panel.pack(side="left", fill="both", expand=True, padx=(15, 0))
        
        # TABLE AREA
        table_container = tk.Frame(right_panel, bg=C_TABLE, bd=2, relief="ridge")
        table_container.pack(fill="x", pady=(0, 10))
        
        table_inner = tk.Frame(table_container, bg=C_TABLE)
        table_inner.pack(padx=20, pady=15)
        
        # Your hand section
        your_hand_frame = tk.Frame(table_inner, bg=C_TABLE)
        your_hand_frame.pack(side="left", padx=(0, 30))
        
        tk.Label(
            your_hand_frame, 
            text="YOUR HAND", 
            bg=C_TABLE, 
            fg="white",
            font=("Arial", 11, "bold")
        ).pack(pady=(0, 5))
        
        hole_container = tk.Frame(your_hand_frame, bg=C_TABLE)
        hole_container.pack()
        
        self.hole = [CardSlot(hole_container, f"Card {i+1}", self) for i in range(2)]
        for s in self.hole: 
            s.pack(side="left", padx=3)
        
        # Community cards section
        community_frame = tk.Frame(table_inner, bg=C_TABLE)
        community_frame.pack(side="left")
        
        tk.Label(
            community_frame, 
            text="COMMUNITY CARDS", 
            bg=C_TABLE, 
            fg="white",
            font=("Arial", 11, "bold")
        ).pack(pady=(0, 5))
        
        board_container = tk.Frame(community_frame, bg=C_TABLE)
        board_container.pack()
        
        board_labels = ["Flop 1", "Flop 2", "Flop 3", "Turn", "River"]
        self.board = [CardSlot(board_container, label, self) for label in board_labels]
        
        # Add separators
        for i, s in enumerate(self.board):
            s.pack(side="left", padx=3)
            if i == 2:  # After flop
                tk.Frame(board_container, bg="#0a3d29", width=2).pack(side="left", fill="y", padx=5)
            elif i == 3:  # After turn
                tk.Frame(board_container, bg="#0a3d29", width=2).pack(side="left", fill="y", padx=5)
        
        # CONTROL PANEL
        control_panel = tk.LabelFrame(
            right_panel, 
            text=" GAME CONTROLS ",
            bg=C_PANEL,
            fg=C_TEXT,
            font=("Arial", 11, "bold"),
            bd=1,
            relief="groove"
        )
        control_panel.pack(fill="x", pady=(0, 10))
        
        # Settings row
        settings_frame = tk.Frame(control_panel, bg=C_PANEL)
        settings_frame.pack(fill="x", padx=15, pady=10)
        
        # Position selector
        pos_frame = tk.Frame(settings_frame, bg=C_PANEL)
        pos_frame.pack(side="left", padx=(0, 20))
        tk.Label(pos_frame, text="Position", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        
        # Style for combobox
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Custom.TCombobox",
            fieldbackground=C_BTN_DARK,
            background=C_BTN_DARK,
            foreground="white",
            bordercolor=C_BORDER,
            arrowcolor="white",
            borderwidth=1,
            relief="flat",
            insertcolor="white",
            selectbackground=C_BTN_PRIMARY,
            selectforeground="white"
        )
        style.map(
            "Custom.TCombobox",
            fieldbackground=[("readonly", C_BTN_DARK)],
            background=[("active", C_BTN_DARK_HOVER)],
            bordercolor=[("focus", C_BTN_PRIMARY)]
        )
        
        pos_cb = ttk.Combobox(
            pos_frame, 
            textvariable=self.position, 
            values=[p.name for p in Position],
            state="readonly", 
            width=10,
            style="Custom.TCombobox",
            font=("Arial", 10)
        )
        pos_cb.pack()
        pos_cb.bind("<<ComboboxSelected>>", lambda e: self._schedule_refresh())
        
        # Stack selector
        stack_frame = tk.Frame(settings_frame, bg=C_PANEL)
        stack_frame.pack(side="left", padx=(0, 20))
        tk.Label(stack_frame, text="Stack Size", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        
        stack_cb = ttk.Combobox(
            stack_frame, 
            textvariable=self.stack_type, 
            values=[s.value for s in StackType],
            state="readonly", 
            width=10,
            style="Custom.TCombobox",
            font=("Arial", 10)
        )
        stack_cb.pack()
        stack_cb.bind("<<ComboboxSelected>>", lambda e: self._schedule_refresh())
        
        # Players selector
        players_frame = tk.Frame(settings_frame, bg=C_PANEL)
        players_frame.pack(side="left", padx=(0, 20))
        tk.Label(players_frame, text="Players", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        
        spin_container = tk.Frame(players_frame, bg=C_BTN_DARK, bd=1, relief="solid")
        spin_container.pack()
        
        players_spin = tk.Spinbox(
            spin_container,
            from_=2,
            to=9,
            textvariable=self.num_players,
            width=5,
            bg=C_BTN_DARK,
            fg="white",
            bd=0,
            font=("Arial", 10),
            justify="center",
            buttonbackground=C_BTN_DARK,
            insertbackground="white"
        )
        players_spin.pack()
        
        # Betting inputs
        betting_frame = tk.Frame(settings_frame, bg=C_PANEL)
        betting_frame.pack(side="left", padx=(0, 20))
        
        # Entry style
        entry_style = {
            "bg": C_BTN_DARK, 
            "fg": "white", 
            "bd": 1, 
            "relief": "solid",
            "insertbackground": "white", 
            "font": ("Arial", 10),
            "highlightthickness": 1,
            "highlightcolor": C_BTN_PRIMARY,
            "highlightbackground": C_BORDER
        }
        
        # Small blind
        sb_frame = tk.Frame(betting_frame, bg=C_PANEL)
        sb_frame.pack(side="left", padx=(0, 10))
        tk.Label(sb_frame, text="SB", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        sb_entry = tk.Entry(sb_frame, textvariable=self.small_blind, width=8, **entry_style)
        sb_entry.pack()
        
        # Big blind
        bb_frame = tk.Frame(betting_frame, bg=C_PANEL)
        bb_frame.pack(side="left", padx=(0, 10))
        tk.Label(bb_frame, text="BB", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        bb_entry = tk.Entry(bb_frame, textvariable=self.big_blind, width=8, **entry_style)
        bb_entry.pack()
        
        # To call
        call_frame = tk.Frame(betting_frame, bg=C_PANEL)
        call_frame.pack(side="left")
        tk.Label(call_frame, text="To Call", bg=C_PANEL, fg=C_TEXT_DIM, font=("Arial", 9)).pack(anchor="w")
        call_entry = tk.Entry(call_frame, textvariable=self.call_amt, width=10, **entry_style)
        call_entry.pack()
        
        # Action buttons
        btn_frame = tk.Frame(settings_frame, bg=C_PANEL)
        btn_frame.pack(side="right")
        
        self.go_btn = StyledButton(
            btn_frame, 
            text="START GAME", 
            color=C_BTN_SUCCESS,
            hover_color=C_BTN_SUCCESS_HOVER, 
            command=self.start_game,
            padx=20,
            fg="black"
        )
        self.go_btn.pack(side="left", padx=(0, 5))
        
        clear_btn = StyledButton(
            btn_frame, 
            text="CLEAR", 
            color=C_BTN_DARK,
            hover_color=C_BTN_DARK_HOVER, 
            command=self.clear_all,
            fg="black"
        )
        clear_btn.pack(side="left")
        
        # Player actions button
        self.action_btn = StyledButton(
            control_panel, 
            text="RECORD PLAYER ACTIONS", 
            color=C_BTN_PRIMARY,
            hover_color=C_BTN_PRIMARY_HOVER, 
            command=self.record_player_actions,
            state="disabled",
            font=("Arial", 11, "bold"),
            fg="black"
        )
        self.action_btn.pack(pady=(0, 10))
        
        # ANALYSIS AREA
        analysis_container = tk.Frame(right_panel, bg=C_PANEL, bd=1, relief="groove")
        analysis_container.pack(fill="both", expand=True)
        
        # Analysis header
        header_bar = tk.Frame(analysis_container, bg="#0e7490", height=40)
        header_bar.pack(fill="x")
        header_bar.pack_propagate(False)
        
        tk.Label(
            header_bar,
            text="ANALYSIS & RECOMMENDATIONS",
            font=("Arial", 12, "bold"),
            bg="#0e7490",
            fg="white"
        ).pack(expand=True)
        
        # Content area
        content_area = tk.Frame(analysis_container, bg=C_BG)
        content_area.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left: Main analysis
        left_content = tk.Frame(content_area, bg=C_BG)
        left_content.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        # Decision display
        self.decision_frame = tk.Frame(left_content, bg=C_BG, height=80)
        self.decision_frame.pack(fill="x", pady=(0, 10))
        self.decision_frame.pack_propagate(False)
        
        self.decision_label = tk.Label(
            self.decision_frame,
            text="",
            font=("Arial", 24, "bold"),
            bg=C_BG,
            fg=C_BTN_PRIMARY
        )
        self.decision_label.pack(expand=True)
        
        # Main text with scrollbar
        text_frame = tk.Frame(left_content, bg=C_BG)
        text_frame.pack(fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(text_frame, bg=C_PANEL)
        scrollbar.pack(side="right", fill="y")
        
        self.out_body = tk.Text(
            text_frame, 
            font=("Consolas", 10), 
            bg="#1e1e1e",
            fg=C_TEXT,
            wrap="word",
            yscrollcommand=scrollbar.set,
            relief="solid",
            bd=1,
            padx=15,
            pady=10,
            highlightthickness=0
        )
        self.out_body.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.out_body.yview)
        
        # Showdown buttons
        showdown_frame = tk.Frame(left_content, bg=C_BG)
        showdown_frame.pack(fill="x", pady=(10, 0))
        
        won_btn = StyledButton(
            showdown_frame, 
            text="✓ MARK AS WON", 
            color=C_BTN_SUCCESS,
            hover_color=C_BTN_SUCCESS_HOVER,
            command=lambda: self._mark_showdown(1)
        )
        won_btn.pack(side="left", padx=(0, 5))
        
        lost_btn = StyledButton(
            showdown_frame, 
            text="✗ MARK AS LOST", 
            color=C_BTN_DANGER,
            hover_color=C_BTN_DANGER_HOVER,
            command=lambda: self._mark_showdown(0)
        )
        lost_btn.pack(side="left")
        
        # Right: Quick stats
        right_content = tk.Frame(content_area, bg="#2a2a2a", width=280, bd=1, relief="groove")
        right_content.pack(side="right", fill="y")
        right_content.pack_propagate(False)
        
        stats_header = tk.Frame(right_content, bg="#374151", height=40)
        stats_header.pack(fill="x")
        stats_header.pack_propagate(False)
        
        tk.Label(
            stats_header,
            text="SESSION STATISTICS",
            font=("Arial", 10, "bold"),
            bg="#374151",
            fg="white"
        ).pack(expand=True)
        
        self.stats_text = tk.Text(
            right_content, 
            font=("Consolas", 10), 
            bg="#2a2a2a",
            fg=C_TEXT,
            wrap="word",
            relief="flat",
            padx=15,
            pady=10,
            highlightthickness=0
        )
        self.stats_text.pack(fill="both", expand=True)
        
        # Configure text tags
        for tw in (self.out_body, self.stats_text):
            tw.tag_configure("header", font=("Arial", 12, "bold"), foreground=C_BTN_PRIMARY, spacing3=8)
            tw.tag_configure("subheader", font=("Arial", 11, "bold"), foreground=C_TEXT, spacing3=5)
            tw.tag_configure("metric", foreground=C_TEXT)
            tw.tag_configure("positive", foreground="#10b981", font=("Arial", 10, "bold"))
            tw.tag_configure("negative", foreground="#ef4444", font=("Arial", 10, "bold"))
            tw.tag_configure("warning", foreground="#f59e0b")
            tw.tag_configure("dim", foreground=C_TEXT_DIM)
            tw.tag_configure("highlight", background="#2d3748")

    # Update grey_out and un_grey methods
    def grey_out(self, card: Card):
        self.used.add(str(card))
        w = self.grid_cards[str(card)]
        w.configure(
            bg=C_CARD_INACTIVE, 
            relief="flat", 
            fg="#666666"
        )
        
    def un_grey(self, card: Card):
        key = str(card)
        if key in self.used:
            self.used.remove(key)
            w = self.grid_cards[key]
            w.configure(
                bg=C_CARD, 
                relief="solid", 
                fg=card.suit.color
            )

    # Update refresh method for better display
    def refresh(self):
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]
        pos = Position[self.position.get()]
        stack_bb = StackType(self.stack_type.get()).default_bb
        pot = self.current_pot if self.game_started else self.small_blind.get() + self.big_blind.get()
        call = self.call_amt.get()

        # Clear displays
        for w in (self.out_body, self.stats_text):
            w.configure(state="normal")
            w.delete("1.0", "end")
            
        self.decision_label.configure(text="")

        if len(hole) == 2:
            tier = hand_tier(hole)
            board_str = ' '.join(map(str, board))
            analysis = analyse_hand(hole, board, pos, stack_bb, pot, call)
            self._last_decision_id = record_decision(analysis, pos, tier, stack_bb, pot, call, board_str)
            
            # Update decision display
            decision_colors = {
                "RAISE": C_BTN_WARNING,
                "CALL": C_BTN_SUCCESS,
                "FOLD": C_BTN_DANGER,
                "CHECK": C_BTN_INFO
            }
            self.decision_label.configure(
                text=f"→ {analysis.decision}",
                fg=decision_colors.get(analysis.decision, C_TEXT)
            )
            
            # Main analysis
            self.out_body.insert("end", f"Hand: {to_two_card_str(hole)} ({tier.upper()})\n", "header")
            self.out_body.insert("end", f"Board: {board_str or 'Pre-flop'}\n", "metric")
            self.out_body.insert("end", f"Position: {pos.name} | Stack: {stack_bb}BB | Pot: ${pot:.1f}\n\n", "dim")
            
            self.out_body.insert("end", "ANALYSIS\n", "subheader")
            self.out_body.insert("end", f"{analysis.reason}\n\n", "metric")
            
            self.out_body.insert("end", "EQUITY\n", "subheader")
            diff = analysis.equity - analysis.required_eq
            self.out_body.insert("end", f"Your equity:     {analysis.equity:6.1%}\n", "metric")
            self.out_body.insert("end", f"Required equity: {analysis.required_eq:6.1%}\n", "metric")
            self.out_body.insert("end", f"Edge:           {diff:+6.1%}\n", "positive" if diff >= 0 else "negative")
            
            self.out_body.insert("end", f"\nEV Call:  ${analysis.ev_call:+7.2f}\n", "positive" if analysis.ev_call >= 0 else "negative")
            self.out_body.insert("end", f"EV Raise: ${analysis.ev_raise:+7.2f}\n\n", "positive" if analysis.ev_raise >= 0 else "negative")
            
            self.out_body.insert("end", "ADVICE\n", "subheader")
            self.out_body.insert("end", get_position_advice(pos) + "\n\n", "dim")
            self.out_body.insert("end", get_hand_advice(tier, analysis.board_texture, analysis.spr), "dim")
        else:
            self.decision_label.configure(text="Select 2 hole cards", fg=C_TEXT_DIM)
            self.out_body.insert("end", "Welcome to Poker Assistant\n\n", "header")
            self.out_body.insert("end", "1. Drag two cards to 'Your Hand' slots\n", "metric")
            self.out_body.insert("end", "2. Add community cards as revealed\n", "metric")
            self.out_body.insert("end", "3. Press START GAME to begin tracking\n", "metric")
            self.out_body.insert("end", "\nDouble-click any card to remove it\n", "dim")

        # Quick stats
        self.stats_text.insert("end", "WIN RATE\n", "header")
        with open_db() as db:
            wins, total = db.execute(
                "SELECT SUM(showdown_win), COUNT(showdown_win) FROM decisions WHERE showdown_win IS NOT NULL"
            ).fetchone()
        
        if total:
            rate = wins/total
            self.stats_text.insert("end", f"\n{wins}/{total} hands\n", "metric")
            self.stats_text.insert("end", f"{rate:6.1%}\n", "positive" if rate >= 0.5 else "negative")
        else:
            self.stats_text.insert("end", "\nNo showdowns yet\n", "dim")

        self.stats_text.insert("end", "\nRECENT DECISIONS\n", "header")
        with open_db() as db:
            recent = db.execute(
                "SELECT decision, COUNT(*) FROM decisions WHERE id > (SELECT MAX(id) - 20 FROM decisions) GROUP BY decision"
            ).fetchall()
        
        if recent:
            for dec, cnt in recent:
                self.stats_text.insert("end", f"\n{dec:<6}: ", "metric")
                self.stats_text.insert("end", f"{cnt:>2}", "positive" if dec in ("RAISE", "CALL") else "negative")
        else:
            self.stats_text.insert("end", "\nNo decisions yet\n", "dim")

        for w in (self.out_body, self.stats_text):
            w.configure(state="disabled")

    # Keep all other methods the same
    def clear_all(self):
        for s in self.hole + self.board:
            if s.card: 
                s.clear()
        self.game_started = False
        self.go_btn.configure(state="normal", text="START GAME", bg=C_BTN_SUCCESS)
        self.go_btn._bg = C_BTN_SUCCESS
        self.go_btn._hover_bg = C_BTN_SUCCESS_HOVER
        self.action_btn.configure(state="disabled")
        self.current_pot = 0.0
        self.players_in_hand.clear()
        self.player_actions.clear()
        self.action_complete = False
        self.refresh()

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
        if not self.game_started:
            messagebox.showwarning("Not Started", "Please start the game first!")
            return
        your_seat = Position[self.position.get()].value
        actions_recorded = False
        for i in range(1, self.num_players.get() + 1):
            if i == your_seat or i not in self.players_in_hand: 
                continue
            dialog = PlayerActionDialog(self, i, self.current_pot)
            self.wait_window(dialog)
            if dialog.result:
                actions_recorded = True
                action, amount = dialog.result
                self.player_actions[i] = (action, amount)
                if action == PlayerAction.FOLD: 
                    self.players_in_hand.remove(i)
                elif action == PlayerAction.CALL: 
                    self.current_pot += self.call_amt.get()
                elif action == PlayerAction.RAISE:
                    self.current_pot += amount
                    self.call_amt.set(amount - self.call_amt.get())
        if actions_recorded:
            self.action_complete = True
            self.refresh()
            messagebox.showinfo("Actions Recorded", f"Actions recorded. Players remaining: {len(self.players_in_hand)}. Current pot: ${self.current_pot:.1f}")

    def _mark_showdown(self, won: int):
        if self._last_decision_id is None:
            messagebox.showinfo("No Decision", "Please analyze a hand first before marking the result.")
            return
        with open_db() as db:
            db.execute("UPDATE decisions SET showdown_win=? WHERE id=?", (won, self._last_decision_id))
        log.info(f"Marked decision ID {self._last_decision_id} as {'WON' if won else 'LOST'}")
        self.refresh()

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

# ─────────────────────────────────────────────────────────────────────────────
# 11. Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = PokerAssistant()
    app.mainloop()