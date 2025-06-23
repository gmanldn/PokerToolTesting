#!/usr/bin/env python3
"""
Graphical user interface and in-game flow for Poker-Assistant.
Enhanced version with automatic analysis updates on card placement.

* 2024 Upgrade:
    - Large suit icons in card grid
    - Pane refreshing fix after card add/remove
    - "Clear All Cards" button
    - Keyboard shortcuts for instant card selection
    - Highlight next slot for card entry
    - Separate table diagram window
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import weakref, logging, math, re
from typing import List, Dict, Tuple, Optional, Set

# ──────────────────────────────────────────────────────
#  Third-Party / Local modules
# ──────────────────────────────────────────────────────────────────────────────
from poker_modules import (
    Suit, Rank, RANKS_MAP, Card, Position, StackType, PlayerAction,
    HandAnalysis, GameState, get_hand_tier, analyse_hand, to_two_card_str,
    get_position_advice, get_hand_advice, RANK_ORDER
)
from poker_init import open_db, record_decision
from poker_tablediagram import TableDiagramWindow

# ──────────────────────────────────────────────────────
#  Constants & Colours - Enhanced
# ──────────────────────────────────────────────────────
log = logging.getLogger(__name__)

C_BG, C_PANEL, C_TABLE, C_CARD, C_CARD_INACTIVE, C_TEXT, C_TEXT_DIM, C_BORDER = \
"#1a1a1a", "#242424", "#1a5f3f", "#ffffff", "#3a3a3a", "#e8e8e8", "#888888", "#3a3a3a"
C_BTN_PRIMARY, C_BTN_SUCCESS, C_BTN_DANGER, C_BTN_WARNING, C_BTN_INFO, C_BTN_DARK = \
"#10b981", "#10b981", "#ef4444", "#f59e0b", "#3b82f6", "#374151"
C_BTN_PRIMARY_HOVER, C_BTN_SUCCESS_HOVER, C_BTN_DANGER_HOVER, C_BTN_WARNING_HOVER, C_BTN_INFO_HOVER, C_BTN_DARK_HOVER = \
"#34d399", "#34d399", "#f87171", "#fbbf24", "#60a5fa", "#4b5563"

# Enhanced colors
C_HERO = "#3b82f6"  # Bright blue for the player
C_HERO_HOVER = "#60a5fa"  # Lighter blue for hover
C_DEALER_PRIMARY = "#FFD700"  # Gold
C_DEALER_SECONDARY = "#FFA500"  # Orange
C_DEALER_BORDER = "#B8860B"  # Dark golden rod
C_CARD_SELECTED = "#fbbf24"  # Yellow for selected card
C_PLAYER_ACTIVE = "#10b981"  # Green for active player
C_PLAYER_INACTIVE = "#6b7280"  # Gray for folded player

SUIT_COLORS = {
    "red": "#f43f5e",
    "black": "#38bdf8"
}

# ──────────────────────────────────────────────────────
#  GUI Widgets
# ──────────────────────────────────────────────────────
class StyledButton(tk.Button):
    def __init__(self, parent, text="", color=C_BTN_PRIMARY, hover_color=None, **kwargs):
        default_fg = "black"  # Always use black text for all buttons
        fg_color = kwargs.pop("fg", default_fg)
        defaults = {"font": ("Arial", 10, "bold"), "fg": fg_color, "bg": color,
                    "activebackground": hover_color or color, "activeforeground": fg_color,
                    "bd": 0, "padx": 12, "pady": 6, "cursor": "hand2", "relief": "flat"}
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)
        self._bg, self._hover_bg = color, hover_color
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg or self._bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

class SelectableCard(tk.Label):
    """Card that can be clicked to select into next available slot."""
    def __init__(self, master: tk.Widget, card: Card, app):
        super().__init__(master, text=str(card), font=("Arial", 12, "bold"),
                         fg=card.suit.color, bg=C_CARD, width=3, height=2,
                         bd=2, relief="solid", highlightthickness=0, cursor="hand2")
        self.card, self._app = card, weakref.proxy(app)
        self._is_used = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_click(self, event):
        if self._is_used:
            return
        self._app.place_card_in_next_slot(self.card)

    def _on_enter(self, event):
        if not self._is_used:
            self.config(bg=C_CARD_SELECTED, relief="raised")

    def _on_leave(self, event):
        if not self._is_used:
            self.config(bg=C_CARD, relief="solid")

    def set_used(self, used: bool):
        self._is_used = used
        if used:
            self.config(bg=C_CARD_INACTIVE, fg=C_TEXT_DIM, cursor="arrow")
        else:
            self.config(bg=C_CARD, fg=self.card.suit.color, cursor="hand2")

class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, app, slot_type: str = "board"):
        super().__init__(master, width=60, height=80, bg="#0d3a26", bd=2, relief="groove",
                         highlightbackground=C_BORDER, highlightthickness=1)
        self.pack_propagate(False)
        self._label = tk.Label(self, text=name, bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)
        self.card, self._app = None, weakref.proxy(app)
        self.slot_type = slot_type  # "hole" or "board"

    def set_card(self, card: Card):
        if self.card:
            return False  # Slot already occupied
        
        self.card = card
        for w in self.winfo_children():
            w.destroy()
        
        inner = tk.Label(self, text=str(card), font=("Arial", 16, "bold"),
                         fg=card.suit.color, bg=C_CARD, bd=1, relief="solid", cursor="hand2")
        inner.pack(expand=True, fill="both", padx=2, pady=2)
        inner.bind("<Button-1>", lambda *_: self.clear())

        self._app.grey_out(card)

        # Immediate refresh
        self._app.force_refresh()
        return True

    def clear(self):
        if not self.card:
            return
        
        self._app.un_grey(self.card)
        old_card = self.card
        self.card = None
        
        for w in self.winfo_children():
            w.destroy()
        
        self._label = tk.Label(self, text="Empty", bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)

        # Immediate refresh
        self._app.force_refresh()

    def highlight(self, on: bool):
        if on:
            self.config(highlightbackground="#fbbf24", highlightthickness=3)
        else:
            self.config(highlightbackground=C_BORDER, highlightthickness=1)

class PlayerToggle(tk.Frame):
    """Clickable player icon that can be toggled on/off."""
    def __init__(self, master, player_num: int, app, **kwargs):
        super().__init__(master, **kwargs)
        self.player_num = player_num
        self._app = weakref.proxy(app)
        self._is_active = True
        
        # Create the visual representation
        self._create_widget()
        
    def _create_widget(self):
        # Player frame with border
        self.config(bg=C_PANEL, width=60, height=60, bd=2, relief="solid",
                   highlightbackground=C_PLAYER_ACTIVE, highlightthickness=2)
        
        # Player icon (simple circle with number)
        self.canvas = tk.Canvas(self, width=40, height=40, bg=C_PANEL, highlightthickness=0)
        self.canvas.pack(expand=True, pady=2)
        
        # Draw player circle
        self._draw_player()
        
        # Label
        self.label = tk.Label(self, text=f"P{self.player_num}", bg=C_PANEL, fg=C_TEXT,
                             font=("Arial", 9, "bold"))
        self.label.pack()
        
        # Bind click events
        self.bind("<Button-1>", self._toggle)
        self.canvas.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        
        # Hover effects
        for widget in [self, self.canvas, self.label]:
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        
    def _draw_player(self):
        self.canvas.delete("all")
        color = C_PLAYER_ACTIVE if self._is_active else C_PLAYER_INACTIVE
        # Draw circle
        self.canvas.create_oval(5, 5, 35, 35, fill=color, outline="", width=0)
        # Draw player number
        text_color = "white" if self._is_active else C_TEXT_DIM
        self.canvas.create_text(20, 20, text=str(self.player_num), 
                               font=("Arial", 14, "bold"), fill=text_color)
        
    def _toggle(self, event=None):
        self._is_active = not self._is_active
        self._draw_player()
        
        # Update border color
        border_color = C_PLAYER_ACTIVE if self._is_active else C_PLAYER_INACTIVE
        self.config(highlightbackground=border_color)
        
        # Update label color
        self.label.config(fg=C_TEXT if self._is_active else C_TEXT_DIM)
        
        # Update game state
        self._app.update_active_players()
        # Immediate refresh to show toggles/analysis updating instantly
        self._app.force_refresh()
        
    def _on_enter(self, event):
        self.config(cursor="hand2")
        if self._is_active:
            self.config(highlightbackground=C_BTN_PRIMARY_HOVER)
        else:
            self.config(highlightbackground=C_TEXT_DIM)
            
    def _on_leave(self, event):
        border_color = C_PLAYER_ACTIVE if self._is_active else C_PLAYER_INACTIVE
        self.config(highlightbackground=border_color)
        
    def is_active(self) -> bool:
        return self._is_active

    def set_active(self, active: bool):
        if self._is_active != active:
            self._toggle()

class PokerAssistant(tk.Tk):
    FONT_HEADER = ("Arial", 13, "bold")
    FONT_SUBHEADER = ("Arial", 11, "bold")
    FONT_BODY = ("Consolas", 10)
    FONT_SMALL_LABEL = ("Arial", 9)
    STYLE_ENTRY = {"bg": C_BTN_DARK, "fg": "white", "bd": 1, "relief": "solid",
                   "insertbackground": "white",
                   "font": ("Arial", 10),
                   "highlightthickness": 2,
                   "highlightcolor": C_BTN_PRIMARY,
                   "highlightbackground": C_BORDER}

    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v16 - Pro Edition")
        self.geometry("1100x920")
        self.minsize(1000, 800)
        self.configure(bg=C_BG)
        self.option_add("*Font", "Arial 10")

        # State vars
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.small_blind = tk.DoubleVar(value=0.5)
        self.big_blind = tk.DoubleVar(value=1.0)
        self.num_players = tk.IntVar(value=6)
        
        # Seat positions
        self.hero_seat = tk.IntVar(value=1)
        self.dealer_seat = tk.IntVar(value=3)

        # Game state
        self.game_state = GameState()

        # UI state
        self.grid_cards: Dict[str, SelectableCard] = {}
        self.used_cards: set[str] = set()
        self.player_toggles: Dict[int, PlayerToggle] = {}
        self._last_decision_id: Optional[int] = None

        # Create table diagram window
        self.table_window = TableDiagramWindow(self)
        
        self._build_gui()
        self.update_active_players()

        # Keyboard shortcuts for quick card input
        self._key_entry_buffer = ""
        self.bind_all("<Key>", self._handle_keypress)
        
        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Handle main window close."""
        if hasattr(self, 'table_window'):
            self.table_window.destroy()
        self.destroy()

    def force_refresh(self):
        """Force an immediate refresh of the entire UI."""
        self.refresh()

    def _build_gui(self):
        main = tk.Frame(self, bg=C_BG)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # Left panel
        left_panel = tk.Frame(main, bg=C_PANEL, width=440)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)
        self._build_card_grid(left_panel)

        # Right panel
        right_panel = tk.Frame(main, bg=C_BG)
        right_panel.pack(side="left", fill="both", expand=True, padx=(15, 0))
        self._build_table_area(right_panel)
        self._build_control_panel(right_panel)
        self._build_action_panel(right_panel)
        self._build_analysis_area(right_panel)

    def _build_card_grid(self, parent):
        header = tk.Frame(parent, bg=C_PANEL)
        header.pack(fill="x", pady=(10, 5), padx=10)
        tk.Label(header, text="🃏 CARD DECK", font=("Arial", 12, "bold"),
                 bg=C_PANEL, fg=C_TEXT).pack(side="left")
        tk.Label(header, text="Click cards or use A-S for 2♠ etc", font=("Arial", 9),
                 bg=C_PANEL, fg=C_TEXT_DIM).pack(side="right")

        card_container = tk.Frame(parent, bg=C_PANEL)
        card_container.pack(fill="x", expand=False, padx=10)

        # --- Improved: Large suit highlighting ---
        for suit in [Suit.SPADE, Suit.HEART, Suit.DIAMOND, Suit.CLUB]:
            suit_frame = tk.Frame(card_container, bg=C_PANEL)
            suit_frame.pack(fill="x", pady=3)
            # Large icon
            suit_color = SUIT_COLORS[suit.color]
            symbol = suit.value
            icon_lbl = tk.Label(suit_frame, text=symbol, font=("Arial", 32, "bold"),
                                fg=suit_color, bg=C_PANEL)
            icon_lbl.pack(side="left", padx=(0, 10))

            # Suit label (text)
            suit_lbl = tk.Label(suit_frame, text=suit.name.capitalize(),
                                font=("Arial", 12, "bold"),
                                fg=suit_color, bg=C_PANEL)
            suit_lbl.pack(side="left")

            # Card row in a subframe with colored border
            border_color = suit_color
            card_border = tk.Frame(suit_frame, bg=border_color, bd=2)
            card_border.pack(side="left", padx=(15, 0), fill="x")
            card_inner = tk.Frame(card_border, bg=C_PANEL)
            card_inner.pack()

            r1 = tk.Frame(card_inner, bg=C_PANEL)
            r2 = tk.Frame(card_inner, bg=C_PANEL)
            r1.pack()
            r2.pack(pady=(3, 0))
            for i, r_val in enumerate(RANK_ORDER):
                card = Card(r_val, suit)
                w = SelectableCard(r1 if i < 7 else r2, card, self)
                w.pack(side="left", padx=2)
                self.grid_cards[str(card)] = w

    def _build_table_area(self, parent):
        """Build the table configuration area."""
        tf = tk.LabelFrame(parent, text=" 🪑 TABLE SETUP ", bg=C_BG, fg=C_TEXT,
                          font=self.FONT_HEADER, bd=2, relief="groove")
        tf.pack(fill="x", pady=(0, 15))

        # First row: Position and Stack
        row1 = tk.Frame(tf, bg=C_BG)
        row1.pack(fill="x", padx=15, pady=(10, 5))

        # Position selection
        pos_frame = tk.Frame(row1, bg=C_BG)
        pos_frame.pack(side="left", padx=(0, 30))
        tk.Label(pos_frame, text="Position:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack(side="left", padx=(0, 5))
        
        # Fixed: Use MP1 instead of MP
        positions = [("UTG", Position.UTG.name), ("MP1", Position.MP1.name),
                    ("CO", Position.CO.name), ("BTN", Position.BTN.name),
                    ("SB", Position.SB.name), ("BB", Position.BB.name)]
        for text, val in positions:
            rb = tk.Radiobutton(pos_frame, text=text, variable=self.position, value=val,
                               bg=C_BG, fg=C_TEXT, selectcolor=C_BTN_DARK,
                               activebackground=C_BG, activeforeground=C_TEXT,
                               command=self.refresh)
            rb.pack(side="left", padx=2)

        # Stack size
        stack_frame = tk.Frame(row1, bg=C_BG)
        stack_frame.pack(side="left")
        tk.Label(stack_frame, text="Stack:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack(side="left", padx=(0, 5))
        
        stacks = [("Short", StackType.SHORT.value), ("Medium", StackType.MEDIUM.value),
                 ("Deep", StackType.DEEP.value)]
        for text, val in stacks:
            rb = tk.Radiobutton(stack_frame, text=text, variable=self.stack_type, value=val,
                               bg=C_BG, fg=C_TEXT, selectcolor=C_BTN_DARK,
                               activebackground=C_BG, activeforeground=C_TEXT,
                               command=self.refresh)
            rb.pack(side="left", padx=2)

        # Second row: Players
        row2 = tk.Frame(tf, bg=C_BG)
        row2.pack(fill="x", padx=15, pady=(5, 10))

        tk.Label(row2, text="Active Players:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack(side="left", padx=(0, 10))

        # Player toggles
        for i in range(1, 10):
            toggle = PlayerToggle(row2, i, self, bg=C_BG)
            toggle.pack(side="left", padx=3)
            self.player_toggles[i] = toggle

        # Third row: Hero and Dealer seats
        row3 = tk.Frame(tf, bg=C_BG)
        row3.pack(fill="x", padx=15, pady=(5, 10))

        # Hero seat
        hero_frame = tk.Frame(row3, bg=C_BG)
        hero_frame.pack(side="left", padx=(0, 30))
        tk.Label(hero_frame, text="Hero Seat:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack(side="left", padx=(0, 5))
        hero_spin = tk.Spinbox(hero_frame, from_=1, to=9, textvariable=self.hero_seat,
                              width=5, command=self.refresh, **self.STYLE_ENTRY)
        hero_spin.pack(side="left")

        # Dealer seat
        dealer_frame = tk.Frame(row3, bg=C_BG)
        dealer_frame.pack(side="left")
        tk.Label(dealer_frame, text="Dealer Seat:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack(side="left", padx=(0, 5))
        dealer_spin = tk.Spinbox(dealer_frame, from_=1, to=9, textvariable=self.dealer_seat,
                                width=5, command=self.refresh, **self.STYLE_ENTRY)
        dealer_spin.pack(side="left")

    def _build_control_panel(self, parent):
        """Build the game control panel."""
        cf = tk.LabelFrame(parent, text=" 🎮 GAME CONTROLS ", bg=C_BG, fg=C_TEXT,
                          font=self.FONT_HEADER, bd=2, relief="groove")
        cf.pack(fill="x", pady=(0, 15))

        # --- New: Clear all cards button
        clear_btn = StyledButton(
            cf, text="🧹 Clear All Cards", color=C_BTN_INFO, hover_color=C_BTN_INFO_HOVER,
            command=self._reset_cards_only, font=("Arial", 10, "bold")
        )
        clear_btn.pack(pady=5, anchor="w", padx=15)

        # Card slots
        slots = tk.Frame(cf, bg=C_BG)
        slots.pack(fill="x", padx=15, pady=15)
        
        # Hole cards
        hole_frame = tk.Frame(slots, bg=C_BG)
        hole_frame.pack(side="left", padx=(0, 30))
        tk.Label(hole_frame, text="🂠 YOUR HAND", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SUBHEADER).pack(anchor="w")
        hole_slots = tk.Frame(hole_frame, bg=C_BG)
        hole_slots.pack(pady=8)
        self.hole = [CardSlot(hole_slots, "Card 1", self, "hole"), 
                     CardSlot(hole_slots, "Card 2", self, "hole")]
        for slot in self.hole:
            slot.pack(side="left", padx=5)
        
        # Board cards
        board_frame = tk.Frame(slots, bg=C_BG)
        board_frame.pack(side="left")
        tk.Label(board_frame, text="🃏 COMMUNITY BOARD", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SUBHEADER).pack(anchor="w")
        board_slots = tk.Frame(board_frame, bg=C_BG)
        board_slots.pack(pady=8)
        self.board = [CardSlot(board_slots, f"Card {i+1}", self, "board") for i in range(5)]
        for slot in self.board:
            slot.pack(side="left", padx=3)

        # Betting controls
        bet_frame = tk.Frame(cf, bg=C_BG)
        bet_frame.pack(fill="x", padx=15, pady=(0, 15))

        # Blinds
        blinds_frame = tk.Frame(bet_frame, bg=C_BG)
        blinds_frame.pack(side="left", padx=(0, 30))
        
        sb_frame = tk.Frame(blinds_frame, bg=C_BG)
        sb_frame.pack(side="left", padx=(0, 15))
        tk.Label(sb_frame, text="Small Blind:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack()
        sb_entry = tk.Entry(sb_frame, textvariable=self.small_blind, width=8, **self.STYLE_ENTRY)
        sb_entry.pack()

        bb_frame = tk.Frame(blinds_frame, bg=C_BG)
        bb_frame.pack(side="left")
        tk.Label(bb_frame, text="Big Blind:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack()
        bb_entry = tk.Entry(bb_frame, textvariable=self.big_blind, width=8, **self.STYLE_ENTRY)
        bb_entry.pack()

        # Pot and To Call
        pot_frame = tk.Frame(bet_frame, bg=C_BG)
        pot_frame.pack(side="left")
        
        pot_inner = tk.Frame(pot_frame, bg=C_BG)
        pot_inner.pack(side="left", padx=(0, 15))
        tk.Label(pot_inner, text="Current Pot:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack()
        self.pot_entry = tk.Entry(pot_inner, width=10, **self.STYLE_ENTRY)
        self.pot_entry.pack()

        call_inner = tk.Frame(pot_frame, bg=C_BG)
        call_inner.pack(side="left")
        tk.Label(call_inner, text="To Call:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SMALL_LABEL).pack()
        self.call_entry = tk.Entry(call_inner, width=10, **self.STYLE_ENTRY)
        self.call_entry.pack()

    def _build_action_panel(self, parent):
        """Build the action panel with decision tracking."""
        af = tk.LabelFrame(parent, text=" 🎯 ACTIONS ", bg=C_BG, fg=C_TEXT,
                          font=self.FONT_HEADER, bd=2, relief="groove")
        af.pack(fill="x", pady=(0, 15))

        # Decision display
        dec_frame = tk.Frame(af, bg=C_BG)
        dec_frame.pack(fill="x", padx=15, pady=(10, 5))
        tk.Label(dec_frame, text="Recommended Action:", bg=C_BG, fg=C_TEXT,
                font=self.FONT_SUBHEADER).pack(side="left")
        self.decision_label = tk.Label(dec_frame, text="→ Add 2 hole cards to begin...",
                                      bg=C_BG, fg=C_TEXT_DIM,
                                      font=("Arial", 12, "bold"))
        self.decision_label.pack(side="left", padx=(10, 0))

        # Action buttons
        btn_frame = tk.Frame(af, bg=C_BG)
        btn_frame.pack(fill="x", padx=15, pady=(5, 15))

        actions = [
            ("💰 RAISE", C_BTN_WARNING, C_BTN_WARNING_HOVER, PlayerAction.RAISE),
            ("📞 CALL", C_BTN_SUCCESS, C_BTN_SUCCESS_HOVER, PlayerAction.CALL),
            ("❌ FOLD", C_BTN_DANGER, C_BTN_DANGER_HOVER, PlayerAction.FOLD),
            ("✔️ CHECK", C_BTN_INFO, C_BTN_INFO_HOVER, PlayerAction.CHECK)
        ]

        for text, color, hover, action in actions:
            btn = StyledButton(btn_frame, text=text, color=color, hover_color=hover,
                             command=lambda a=action: self._record_action(a))
            btn.pack(side="left", padx=5)

        # Start new hand button
        new_hand_btn = StyledButton(btn_frame, text="🔄 New Hand", 
                                   color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER,
                                   command=self._reset_hand)
        new_hand_btn.pack(side="right", padx=(20, 0))

    def _build_analysis_area(self, parent):
        """Build the analysis display area."""
        self.analysis_frame = tk.LabelFrame(parent, text=" 📊 HAND ANALYSIS ", 
                                           bg=C_BG, fg=C_TEXT,
                                           font=self.FONT_HEADER, bd=2, relief="groove")
        self.analysis_frame.pack(fill="both", expand=True)

        # Create text widget for analysis
        self.analysis_text = tk.Text(self.analysis_frame, bg=C_PANEL, fg=C_TEXT,
                                    font=self.FONT_BODY, wrap="word", height=10,
                                    bd=0, padx=15, pady=15)
        self.analysis_text.pack(fill="both", expand=True, padx=2, pady=2)

        # Stats panel
        self.stats_frame = tk.LabelFrame(parent, text=" 📈 SESSION STATS ", 
                                        bg=C_BG, fg=C_TEXT,
                                        font=self.FONT_HEADER, bd=2, relief="groove")
        self.stats_frame.pack(fill="x", pady=(15, 0))

        self.stats_text = tk.Text(self.stats_frame, bg=C_PANEL, fg=C_TEXT,
                                 font=self.FONT_BODY, wrap="word", height=3,
                                 bd=0, padx=15, pady=10)
        self.stats_text.pack(fill="x", padx=2, pady=2)

    def _reset_cards_only(self):
        """Only clear all cards, don't touch pot/players."""
        for slot in self.hole + self.board:
            slot.clear()
        self.force_refresh()

    def place_card_in_next_slot(self, card: Card):
        """Place a card in the next available slot."""
        # Try hole cards first
        for slot in self.hole:
            if slot.set_card(card):
                self._highlight_next_slot()
                return
        
        # Then try board cards
        for slot in self.board:
            if slot.set_card(card):
                self._highlight_next_slot()
                return
        
        messagebox.showinfo("No Free Slots", "All card slots are full. Remove a card first.")

    def _highlight_next_slot(self):
        """Highlight the next available slot for card entry."""
        candidates = self.hole + self.board
        found = False
        for slot in candidates:
            if not slot.card and not found:
                slot.highlight(True)
                found = True
            else:
                slot.highlight(False)
        if not found:
            for slot in candidates:
                slot.highlight(False)

    def _handle_keypress(self, event):
        """Handle keyboard shortcuts for rapid card entry."""
        key = event.char.upper()
        # Acceptable rank input
        valid_ranks = {
            'A': 'A', 'K': 'K', 'Q': 'Q', 'J': 'J', 'T': 'T',
            '2': '2', '3': '3', '4': '4', '5': '5', '6': '6',
            '7': '7', '8': '8', '9': '9'
        }
        valid_suits = {'S': Suit.SPADE, 'H': Suit.HEART, 'D': Suit.DIAMOND, 'C': Suit.CLUB}

        if key in valid_ranks:
            self._key_entry_buffer = key
        elif key in valid_suits and self._key_entry_buffer:
            card = Card(self._key_entry_buffer, valid_suits[key])
            cardstr = str(card)
            if cardstr in self.grid_cards and not self.grid_cards[cardstr]._is_used:
                self.place_card_in_next_slot(card)
            self._key_entry_buffer = ""
        else:
            self._key_entry_buffer = ""

    def grey_out(self, card: Card):
        """Mark a card as used in the grid."""
        card_str = str(card)
        if card_str in self.grid_cards:
            self.grid_cards[card_str].set_used(True)
            self.used_cards.add(card_str)

    def un_grey(self, card: Card):
        """Mark a card as available in the grid."""
        card_str = str(card)
        if card_str in self.grid_cards:
            self.grid_cards[card_str].set_used(False)
            self.used_cards.discard(card_str)

    def update_active_players(self):
        """Update the number of active players based on toggles."""
        active_count = sum(1 for toggle in self.player_toggles.values() if toggle.is_active())
        self.num_players.set(max(2, active_count))  # Minimum 2 players
        
    def _update_game_state(self):
        """Update game state from UI inputs."""
        try:
            pot_text = self.pot_entry.get().strip()
            call_text = self.call_entry.get().strip()
            
            if pot_text and call_text:
                self.game_state.is_active = True
                self.game_state.pot = float(pot_text)
                self.game_state.to_call = float(call_text)
            else:
                self.game_state.is_active = False
                self.game_state.pot = self.small_blind.get() + self.big_blind.get()
                self.game_state.to_call = self.big_blind.get()
        except ValueError:
            self.game_state.is_active = False

    def _record_action(self, action: PlayerAction):
        """Record a player action."""
        if self._last_decision_id is None:
            messagebox.showwarning("No Analysis", 
                                 "Add 2 hole cards first to get hand analysis before recording actions.")
            return
        
        try:
            record_decision(self._last_decision_id, action.value)
            messagebox.showinfo("Action Recorded", 
                              f"Your {action.value} action has been recorded.")
        except Exception as e:
            log.error(f"Failed to record action: {e}")
            messagebox.showerror("Error", f"Failed to record action: {e}")

    def _reset_hand(self):
        """Reset for a new hand."""
        for slot in self.hole + self.board:
            slot.clear()
        self.pot_entry.delete(0, tk.END)
        self.call_entry.delete(0, tk.END)
        self.game_state = GameState()
        self._last_decision_id = None
        self.refresh()

    def refresh(self):
        """Main refresh method that updates everything."""
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]

        self._clear_output_panels()
        self._update_game_state()

        # Highlight next slot
        self._highlight_next_slot()

        # Determine stage
        stage_lookup = {0: "Pre-flop", 3: "Flop", 4: "Turn", 5: "River"}
        stage = stage_lookup.get(len(board), "Post-flop")

        analysis: Optional[HandAnalysis] = None
        
        # Show analysis if we have 2 hole cards
        if len(hole) == 2:
            analysis = self._update_analysis_panel(hole, board)
            
            # Update decision label with current recommendation
            colors = {"RAISE": C_BTN_WARNING, "CALL": C_BTN_SUCCESS, 
                     "FOLD": C_BTN_DANGER, "CHECK": C_BTN_INFO}
            self.decision_label.config(
                text=f"→ {analysis.decision}",
                fg=colors.get(analysis.decision, C_TEXT)
            )
        else:
            self._display_welcome_message()
            self.decision_label.config(text="→ Add 2 hole cards to begin...", fg=C_TEXT_DIM)
            self._last_decision_id = None

        self._update_stats_panel()

        # Update table diagram
        active_players = {i for i, toggle in self.player_toggles.items() if toggle.is_active()}
        pot = self.game_state.pot if self.game_state.is_active else (self.small_blind.get() + self.big_blind.get())
        to_call = self.game_state.to_call if self.game_state.is_active else self.big_blind.get()
        equity = analysis.equity if analysis else None
        
        self.table_window.update_state(
            active_players=active_players,
            hero_seat=self.hero_seat.get(),
            dealer_seat=self.dealer_seat.get(),
            pot=pot,
            to_call=to_call,
            stage=stage,
            equity=equity
        )

    def _clear_output_panels(self):
        """Clear all output text widgets."""
        self.analysis_text.delete("1.0", tk.END)
        self.stats_text.delete("1.0", tk.END)

    def _display_welcome_message(self):
        """Display welcome message when no cards are selected."""
        self.analysis_text.insert("1.0", 
            "Welcome to Poker Assistant v16!\n\n"
            "• Click cards or use keyboard shortcuts (e.g., AS for A♠)\n"
            "• Add 2 hole cards to see hand analysis\n"
            "• Toggle players on/off to adjust table dynamics\n"
            "• Add community cards to see updated recommendations\n\n"
            "Ready to improve your game!")

    def _update_analysis_panel(self, hole: List[Card], board: List[Card]) -> HandAnalysis:
        """Update the analysis panel with hand information."""
        try:
            analysis = analyse_hand(
                hole=hole,
                board=board,
                position=Position[self.position.get()],
                stack_type=StackType(self.stack_type.get()),
                num_players=self.num_players.get(),
                to_call=self.game_state.to_call,
                pot=self.game_state.pot,
                big_blind=self.big_blind.get()
            )

            # Store for action recording
            hand_str = to_two_card_str(hole[0], hole[1])
            decision_id = open_db().execute(
                "INSERT INTO decisions (hand, position, decision, timestamp) VALUES (?, ?, ?, datetime('now'))",
                (hand_str, self.position.get(), analysis.decision)
            ).lastrowid
            open_db().commit()
            self._last_decision_id = decision_id

            # Format analysis display
            self._format_analysis_display(analysis, hole, board)
            
            return analysis
            
        except Exception as e:
            log.error(f"Analysis failed: {e}")
            self.analysis_text.insert("1.0", f"Analysis Error: {e}")
            return HandAnalysis()

    def _format_analysis_display(self, analysis: HandAnalysis, hole: List[Card], board: List[Card]):
        """Format and display the analysis results."""
        text = self.analysis_text
        
        # Hand info
        hand_str = f"{hole[0]} {hole[1]}"
        text.insert(tk.END, f"Your Hand: {hand_str}\n")
        
        if board:
            board_str = " ".join(str(c) for c in board)
            text.insert(tk.END, f"Board: {board_str}\n")
        
        text.insert(tk.END, f"Position: {self.position.get()}\n")
        text.insert(tk.END, f"Players: {self.num_players.get()}\n\n")
        
        # Analysis results
        text.insert(tk.END, f"Hand Tier: {analysis.tier}\n")
        text.insert(tk.END, f"Playability: {analysis.playability}/10\n")
        
        if analysis.equity:
            text.insert(tk.END, f"Equity: {analysis.equity:.1f}%\n")
        
        if analysis.pot_odds:
            text.insert(tk.END, f"Pot Odds: {analysis.pot_odds:.1f}%\n")
        
        text.insert(tk.END, f"\nRecommendation: {analysis.decision}\n\n")
        
        # Reasoning
        if analysis.reasoning:
            text.insert(tk.END, "Analysis:\n")
            for reason in analysis.reasoning:
                text.insert(tk.END, f"• {reason}\n")

    def _update_stats_panel(self):
        """Update session statistics."""
        try:
            db = open_db()
            cursor = db.execute(
                "SELECT decision, COUNT(*) FROM decisions WHERE date(timestamp) = date('now') GROUP BY decision"
            )
            stats = dict(cursor.fetchall())
            
            total = sum(stats.values())
            if total > 0:
                self.stats_text.insert("1.0", f"Today's Decisions ({total} hands):\n")
                for action in ["FOLD", "CALL", "RAISE", "CHECK"]:
                    count = stats.get(action, 0)
                    pct = (count / total * 100) if total > 0 else 0
                    self.stats_text.insert(tk.END, f"{action}: {count} ({pct:.1f}%)  ")
            else:
                self.stats_text.insert("1.0", "No decisions recorded today yet.")
                
        except Exception as e:
            log.error(f"Stats update failed: {e}")
            self.stats_text.insert("1.0", "Stats unavailable")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        app = PokerAssistant()
        app.mainloop()
    except Exception as e:
        log.error("Unhandled exception", exc_info=True)
        messagebox.showerror("Fatal Error", f"A critical error occurred: {e}")
