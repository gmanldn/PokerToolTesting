#!/usr/bin/env python3
"""
Graphical user interface and in-game flow for Poker-Assistant.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import weakref
import logging
import math
import re
from typing import List, Dict, Tuple, Optional

# ──────────────────────────────────────────────────────
#  Third-Party / Local modules
# ──────────────────────────────────────────────────────
from poker_modules import (
    Suit, Rank, RANKS_MAP, Card, Position, StackType, PlayerAction, 
    HandAnalysis, GameState, get_hand_tier, analyse_hand, to_two_card_str,
    get_position_advice, get_hand_advice, RANK_ORDER
)
from poker_init import open_db, record_decision

# ──────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# Colors
C_BG, C_PANEL, C_TABLE, C_CARD, C_CARD_INACTIVE, C_TEXT, C_TEXT_DIM, C_BORDER = \
"#1a1a1a", "#242424", "#1a5f3f", "#ffffff", "#3a3a3a", "#e8e8e8", "#888888", "#3a3a3a"
C_BTN_PRIMARY, C_BTN_SUCCESS, C_BTN_DANGER, C_BTN_WARNING, C_BTN_INFO, C_BTN_DARK = \
"#10b981", "#10b981", "#ef4444", "#f59e0b", "#3b82f6", "#374151"
C_BTN_PRIMARY_HOVER, C_BTN_SUCCESS_HOVER, C_BTN_DANGER_HOVER, C_BTN_WARNING_HOVER, C_BTN_INFO_HOVER, C_BTN_DARK_HOVER = \
"#34d399", "#34d399", "#f87171", "#fbbf24", "#60a5fa", "#4b5563"

# ──────────────────────────────────────────────────────
#  GUI widgets
# ──────────────────────────────────────────────────────
class StyledButton(tk.Button):
    def __init__(self, parent, text="", color=C_BTN_PRIMARY, hover_color=None, **kwargs):
        default_fg = "black" if color in (C_BTN_PRIMARY, C_BTN_SUCCESS) else "white"
        fg_color = kwargs.pop("fg", default_fg)
        defaults = {"font": ("Arial", 10, "bold"), "fg": fg_color, "bg": color,
                    "activebackground": hover_color or color, "activeforeground": fg_color,
                    "bd": 0, "padx": 12, "pady": 6, "cursor": "hand2", "relief": "flat"}
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)
        self._bg = color
        self._hover_bg = hover_color
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg or self._bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

class DraggableCard(tk.Label):
    def __init__(self, master: tk.Widget, card: Card, app):
        super().__init__(master, text=str(card), font=("Arial", 12, "bold"),
                         fg=card.suit.color, bg=C_CARD, width=3, height=2,
                         bd=1, relief="solid", highlightthickness=0)
        self.card, self._app = card, weakref.proxy(app)
        self._start, self._dragging = (0, 0), False
        self.bind("<Button-1>", self._click_start)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _click_start(self, ev): self._start, self._dragging = (ev.x, ev.y), False; self.lift()
    def _drag(self, ev):
        if abs(ev.x - self._start[0]) > 3 or abs(ev.y - self._start[1]) > 3: self._dragging = True
        self.place(x=self.winfo_x() + (ev.x - self._start[0]), y=self.winfo_y() + (ev.y - self._start[1]))

    def _release(self, ev):
        target = self.winfo_containing(ev.x_root, ev.y_root)
        if self._dragging and hasattr(target, "accept"): target.accept(self)
        else: self.place_forget(); self.pack(side="left", padx=2, pady=2); self._app.place_next_free(self.card)

class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, app):
        super().__init__(master, width=60, height=80, bg="#0d3a26", bd=2, relief="groove",
                         highlightbackground=C_BORDER, highlightthickness=1)
        self.pack_propagate(False)
        self._label = tk.Label(self, text=name, bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)
        self.card, self._app = None, weakref.proxy(app)

    def accept(self, widget: DraggableCard):
        if self.card: widget.place_forget(); widget.pack(side="left", padx=2, pady=2); return
        self.set_card(widget.card)
        widget.place_forget()
        widget._app.grey_out(widget.card)
        self._app.refresh()

    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children(): w.destroy()
        inner = tk.Label(self, text=str(card), font=("Arial", 16, "bold"),
                         fg=card.suit.color, bg=C_CARD, bd=1, relief="solid")
        inner.pack(expand=True, fill="both", padx=2, pady=2)
        inner.bind("<Double-Button-1>", lambda *_: self.clear())

    def clear(self):
        if not self.card: return
        self._app.un_grey(self.card)
        self.card = None
        for w in self.winfo_children(): w.destroy()
        self._label = tk.Label(self, text="Empty", bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)
        self._app.refresh()
        
class TableVisualization(tk.Canvas):
    def __init__(self, parent, app):
        super().__init__(parent, width=300, height=200, bg=C_PANEL, highlightthickness=0)
        self._app, self.table_rotation = weakref.proxy(app), 0
        self._draw_table()

    def _draw_table(self):
        self.delete("all")
        cx, cy, rx, ry = 150, 100, 110, 70
        self.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill="#0d3a26", outline="#1a5f3f", width=3)
        self.create_oval(cx - rx + 10, cy - ry + 10, cx + rx - 10, cy + ry - 10, fill="", outline="#1a5f3f", width=1)
        
        num_players = self._app.num_players.get()
        your_seat = Position[self._app.position.get()].value

        for i in range(num_players):
            visual_pos = (i - self.table_rotation) % num_players
            angle = (visual_pos * 2 * math.pi / num_players) - (math.pi / 2)
            px, py = cx + int(rx * 1.3 * math.cos(angle)), cy + int(ry * 1.3 * math.sin(angle))

            seat_num = i + 1
            is_you, is_dealer = seat_num == your_seat, seat_num == Position.BTN.value
            radius = 22 if is_you else 18
            
            if is_you:
                color, outline_color, text_color, label, weight = "#fbbf24", "#fbbf24", "black", "YOU", "bold"
            elif is_dealer:
                color, outline_color, text_color, label, weight = C_BTN_INFO, C_BTN_INFO_HOVER, "white", "BTN", "bold"
            else:
                color, outline_color, text_color, label, weight = C_BTN_DARK, C_BORDER, "white", f"P{seat_num}", "normal"
            
            self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=color, outline=outline_color, width=2 if is_you or is_dealer else 1)
            self.create_text(px, py, text=label, font=("Arial", 10, weight), fill=text_color)
            
            if seat_num == Position.SB.value: self.create_text(px, py + radius + 10, text="SB", font=("Arial", 9, "bold"), fill=C_BTN_INFO)
            elif seat_num == Position.BB.value: self.create_text(px, py + radius + 10, text="BB", font=("Arial", 9, "bold"), fill=C_BTN_INFO)

    def rotate_clockwise(self): self.table_rotation = (self.table_rotation - 1) % self._app.num_players.get(); self._draw_table()
    def rotate_counter_clockwise(self): self.table_rotation = (self.table_rotation + 1) % self._app.num_players.get(); self._draw_table()

# ──────────────────────────────────────────────────────
#  Main application window
# ──────────────────────────────────────────────────────
class PokerAssistant(tk.Tk):
    # Centralized styling
    FONT_HEADER = ("Arial", 12, "bold")
    FONT_SUBHEADER = ("Arial", 11, "bold")
    FONT_BODY = ("Consolas", 10)
    FONT_SMALL_LABEL = ("Arial", 9)
    STYLE_ENTRY = {"bg": C_BTN_DARK, "fg": "white", "bd": 1, "relief": "solid", "insertbackground": "white",
                   "font": ("Arial", 10), "highlightthickness": 1, "highlightcolor": C_BTN_PRIMARY, "highlightbackground": C_BORDER}

    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v13 - Pro Edition")
        self.geometry("1400x900")
        self.minsize(1200, 800)
        self.configure(bg=C_BG)

        self.option_add("*Font", "Arial 10")
        
        # State variables
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.small_blind = tk.DoubleVar(value=0.5)
        self.big_blind = tk.DoubleVar(value=1.0)
        self.num_players = tk.IntVar(value=6)
        
        # State object for game flow
        self.game_state = GameState()

        # UI State
        self.grid_cards: Dict[str, DraggableCard] = {}
        self.used_cards: set[str] = set()
        self._last_decision_id: Optional[int] = None
        self._refresh_scheduled = False

        self._build_gui()
        self.after(100, self.refresh)

    def _schedule_refresh(self, _=None):
        if not self._refresh_scheduled:
            self._refresh_scheduled = True
            self.after(50, self._do_refresh)
            
    def _do_refresh(self): self._refresh_scheduled = False; self.refresh()

    def _build_gui(self):
        main = tk.Frame(self, bg=C_BG); main.pack(fill="both", expand=True, padx=15, pady=10)
        # Left Panel (Card Grid + Table View)
        left_panel = tk.Frame(main, bg=C_PANEL, width=340); left_panel.pack(side="left", fill="y"); left_panel.pack_propagate(False)
        self._build_card_grid(left_panel)
        self._build_table_view(left_panel)
        # Right Panel (Main Content)
        right_panel = tk.Frame(main, bg=C_BG); right_panel.pack(side="left", fill="both", expand=True, padx=(15, 0))
        self._build_table_area(right_panel)
        self._build_control_panel(right_panel)
        self._build_action_panel(right_panel)  # New non-modal action panel
        self._build_analysis_area(right_panel)
        
    def _build_card_grid(self, parent):
        tk.Label(parent, text="CARD DECK", font=("Arial", 11, "bold"), bg=C_PANEL, fg=C_TEXT).pack(pady=(10,5))
        card_container = tk.Frame(parent, bg=C_PANEL); card_container.pack(fill="x", expand=False, padx=10)
        for suit in [Suit.SPADE, Suit.HEART, Suit.DIAMOND, Suit.CLUB]:
            sf = tk.LabelFrame(card_container, text=f" {suit.value} ", fg=suit.color if suit.color=="red" else C_TEXT,
                               bg=C_PANEL, font=("Arial", 10, "bold"), bd=1, relief="groove", labelanchor="w", padx=5, pady=5)
            sf.pack(fill="x", pady=3)
            rows = tk.Frame(sf, bg=C_PANEL); rows.pack()
            r1, r2 = tk.Frame(rows, bg=C_PANEL), tk.Frame(rows, bg=C_PANEL); r1.pack(); r2.pack(pady=(3,0))
            for i, r_val in enumerate(RANK_ORDER):
                card = Card(r_val, suit)
                w = DraggableCard(r1 if i < 7 else r2, card, self); w.pack(side="left", padx=2)
                self.grid_cards[str(card)] = w

    def _build_table_view(self, parent):
        tf = tk.LabelFrame(parent, text=" TABLE VIEW ", bg=C_PANEL, fg=C_TEXT, font=("Arial", 10, "bold"), bd=1, relief="groove")
        tf.pack(fill="x", padx=10, pady=10)
        self.table_viz = TableVisualization(tf, self); self.table_viz.pack(pady=5)
        rf = tk.Frame(tf, bg=C_PANEL); rf.pack(pady=(0, 10))
        StyledButton(rf, text="◀", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER, command=self.table_viz.rotate_counter_clockwise, width=3, padx=5, pady=3).pack(side="left", padx=5)
        tk.Label(rf, text="Rotate", bg=C_PANEL, fg=C_TEXT_DIM).pack(side="left", padx=10)
        StyledButton(rf, text="▶", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER, command=self.table_viz.rotate_clockwise, width=3, padx=5, pady=3).pack(side="left", padx=5)

    def _build_table_area(self, parent):
        tc = tk.Frame(parent, bg=C_TABLE, bd=2, relief="ridge"); tc.pack(fill="x", pady=(0, 10))
        ti = tk.Frame(tc, bg=C_TABLE); ti.pack(padx=20, pady=15, fill="x")
        
        # Hole Cards
        yhf = tk.Frame(ti, bg=C_TABLE); yhf.pack(side="left", padx=(0, 30))
        tk.Label(yhf, text="YOUR HAND", bg=C_TABLE, fg="white", font=self.FONT_SUBHEADER).pack(pady=(0, 5))
        hc = tk.Frame(yhf, bg=C_TABLE); hc.pack()
        self.hole = [CardSlot(hc, f"Card {i+1}", self) for i in range(2)]; [s.pack(side="left", padx=3) for s in self.hole]
        
        # Community Cards
        cf = tk.Frame(ti, bg=C_TABLE); cf.pack(side="left")
        tk.Label(cf, text="COMMUNITY CARDS", bg=C_TABLE, fg="white", font=self.FONT_SUBHEADER).pack(pady=(0, 5))
        bc = tk.Frame(cf, bg=C_TABLE); bc.pack()
        self.board = [CardSlot(bc, l, self) for l in ["F1","F2","F3","T","R"]]; [s.pack(side="left", padx=3) for s in self.board]

        # Keyboard Input (New)
        kif = tk.Frame(ti, bg=C_TABLE); kif.pack(side="left", padx=(30, 0), fill="x", expand=True)
        tk.Label(kif, text="FAST INPUT", bg=C_TABLE, fg="white", font=self.FONT_SUBHEADER).pack(pady=(0,5))
        ef = tk.Frame(kif, bg=C_TABLE); ef.pack()
        tk.Label(ef, text="Hand:", bg=C_TABLE, fg=C_TEXT_DIM).pack(side="left")
        self.hole_entry = tk.Entry(ef, **self.STYLE_ENTRY, width=5); self.hole_entry.pack(side="left", padx=5)
        tk.Label(ef, text="Board:", bg=C_TABLE, fg=C_TEXT_DIM).pack(side="left")
        self.board_entry = tk.Entry(ef, **self.STYLE_ENTRY, width=12); self.board_entry.pack(side="left", padx=5)
        StyledButton(ef, text="SET", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER, command=self._set_cards_from_text, padx=15).pack(side="left")

    def _build_control_panel(self, parent):
        cp = tk.LabelFrame(parent, text=" GAME SETUP ", bg=C_PANEL, fg=C_TEXT, font=self.FONT_SUBHEADER, bd=1, relief="groove")
        cp.pack(fill="x", pady=(0, 10))
        sf = tk.Frame(cp, bg=C_PANEL); sf.pack(fill="x", padx=15, pady=10)
        
        # Settings Comboboxes/Spinbox
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Custom.TCombobox", fieldbackground=C_BTN_DARK, background=C_BTN_DARK, foreground="white", bordercolor=C_BORDER, arrowcolor="white", borderwidth=1, relief="flat", padding=4)
        
        items = [("Position", self.position, [p.name for p in Position]), ("Stack", self.stack_type, [s.value for s in StackType]), ("Players", self.num_players, list(range(2, 10)))]
        for label, var, values in items:
            frame = tk.Frame(sf, bg=C_PANEL); frame.pack(side="left", padx=(0, 20))
            tk.Label(frame, text=label, bg=C_PANEL, fg=C_TEXT_DIM, font=self.FONT_SMALL_LABEL).pack(anchor="w")
            if isinstance(var, tk.IntVar):
                tk.Spinbox(frame, from_=2, to=9, textvariable=var, width=5, command=self._on_players_change, **self.STYLE_ENTRY, justify="center", buttonbackground=C_BTN_DARK).pack()
            else:
                cb = ttk.Combobox(frame, textvariable=var, values=values, state="readonly", width=12, style="Custom.TCombobox"); cb.pack()
                cb.bind("<<ComboboxSelected>>", self._on_players_change if label=="Players" else self._schedule_refresh)
        
        # Betting Inputs
        bf = tk.Frame(sf, bg=C_PANEL); bf.pack(side="left", padx=(0, 20))
        for label, var in [("SB", self.small_blind), ("BB", self.big_blind)]:
            frame = tk.Frame(bf, bg=C_PANEL); frame.pack(side="left", padx=(0,10))
            tk.Label(frame, text=label, bg=C_PANEL, fg=C_TEXT_DIM, font=self.FONT_SMALL_LABEL).pack(anchor="w")
            tk.Entry(frame, textvariable=var, width=5, **self.STYLE_ENTRY).pack()

        # Action Buttons
        btn_frame = tk.Frame(sf, bg=C_PANEL); btn_frame.pack(side="right")
        self.go_btn = StyledButton(btn_frame, text="START HAND", color=C_BTN_SUCCESS, hover_color=C_BTN_SUCCESS_HOVER, command=self.start_game, padx=20)
        self.go_btn.pack(side="left", padx=(0, 5))
        StyledButton(btn_frame, text="CLEAR", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER, command=self.clear_all).pack(side="left")

    def _build_action_panel(self, parent):
        self.action_panel = tk.LabelFrame(parent, text=" RECORD OPPONENT ACTIONS ", bg=C_PANEL, fg=C_TEXT, font=self.FONT_SUBHEADER, bd=1, relief="groove")
        # will be packed later
    
    def _build_analysis_area(self, parent):
        ac = tk.Frame(parent, bg=C_PANEL, bd=1, relief="groove"); ac.pack(fill="both", expand=True)
        header = tk.Frame(ac, bg=C_BTN_PRIMARY, height=40); header.pack(fill="x"); header.pack_propagate(False)
        tk.Label(header, text="ANALYSIS & RECOMMENDATIONS", font=self.FONT_HEADER, bg=C_BTN_PRIMARY, fg="black").pack(expand=True)
        content = tk.Frame(ac, bg=C_BG); content.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left side: Decision & Text
        left = tk.Frame(content, bg=C_BG); left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.decision_frame = tk.Frame(left, bg=C_BG, height=80); self.decision_frame.pack(fill="x", pady=(0, 10)); self.decision_frame.pack_propagate(False)
        self.decision_label = tk.Label(self.decision_frame, text="", font=("Arial", 24, "bold"), bg=C_BG); self.decision_label.pack(expand=True)
        
        tf = tk.Frame(left, bg=C_BG); tf.pack(fill="both", expand=True)
        self.out_body = tk.Text(tf, font=self.FONT_BODY, bg="#1e1e1e", fg=C_TEXT, wrap="word", relief="solid", bd=1, padx=15, pady=10, highlightthickness=0); self.out_body.pack(side="left", fill="both", expand=True)
        
        # Right side: Stats
        right = tk.Frame(content, bg="#2a2a2a", width=280, bd=1, relief="groove"); right.pack(side="right", fill="y"); right.pack_propagate(False)
        sh = tk.Frame(right, bg="#374151", height=40); sh.pack(fill="x"); sh.pack_propagate(False)
        tk.Label(sh, text="SESSION STATISTICS", font=("Arial", 10, "bold"), bg="#374151", fg="white").pack(expand=True)
        self.stats_text = tk.Text(right, font=self.FONT_BODY, bg="#2a2a2a", fg=C_TEXT, wrap="word", relief="flat", padx=15, pady=10); self.stats_text.pack(fill="both", expand=True)
        
        for tw in (self.out_body, self.stats_text):
            tw.tag_configure("header", font=self.FONT_HEADER, foreground=C_BTN_PRIMARY, spacing3=8); tw.tag_configure("subheader", font=self.FONT_SUBHEADER, foreground=C_TEXT, spacing3=5)
            tw.tag_configure("positive", foreground=C_BTN_SUCCESS, font=("Arial", 10, "bold")); tw.tag_configure("negative", foreground=C_BTN_DANGER, font=("Arial", 10, "bold"))
            tw.tag_configure("dim", foreground=C_TEXT_DIM)

    # ──────────────────────────────────────────────────────
    #  UI Event Handlers & State Changers
    # ──────────────────────────────────────────────────────
    def _on_players_change(self, _=None): self.table_viz.table_rotation = 0; self.table_viz._draw_table(); self._schedule_refresh()
    def grey_out(self, card: Card): self.used_cards.add(str(card)); self.grid_cards[str(card)].config(bg=C_CARD_INACTIVE, relief="flat", fg="#666")
    def un_grey(self, card: Card):
        key = str(card)
        if key in self.used_cards: self.used_cards.remove(key); self.grid_cards[key].config(bg=C_CARD, relief="solid", fg=card.suit.color)

    def _set_cards_from_text(self):
        try:
            # Clear existing cards first
            for slot in self.hole + self.board: slot.clear()
            
            # Parse and set hole cards
            hole_text = self.hole_entry.get().strip()
            if hole_text:
                hole_cards = self._parse_card_string(hole_text)
                if len(hole_cards) != 2: raise ValueError("Hole cards must be 2 cards.")
                for i, card in enumerate(hole_cards): self.hole[i].set_card(card); self.grey_out(card)
            
            # Parse and set board cards
            board_text = self.board_entry.get().strip()
            if board_text:
                board_cards = self._parse_card_string(board_text)
                for i, card in enumerate(board_cards): 
                    if i < 5: self.board[i].set_card(card); self.grey_out(card)
            
            self.refresh()
        except Exception as e:
            messagebox.showerror("Invalid Card Input", f"Error: {e}\nUse format like 'AsKd' for hole, 'QcTs9h' for board.")
    
    def _parse_card_string(self, text: str) -> List[Card]:
        text = text.replace(" ", "").replace(",", "")
        if len(text) % 2 != 0: raise ValueError("Invalid string length.")
        cards = []
        suit_map = {v.value: k for k, v in Suit.__members__.items()}
        for i in range(0, len(text), 2):
            rank_char, suit_char = text[i].upper(), text[i+1].lower()
            suit_lookup = {'s':'♠', 'h':'♥', 'd':'♦', 'c':'♣'}
            suit_val = suit_lookup.get(suit_char)
            if not suit_val: raise ValueError(f"Invalid suit '{text[i+1]}'")
            if rank_char not in RANKS_MAP: raise ValueError(f"Invalid rank '{text[i]}'")
            cards.append(Card(rank_char, Suit(suit_val)))
        if len(set(cards)) != len(cards): raise ValueError("Duplicate cards detected.")
        return cards

    def clear_all(self):
        for s in self.hole + self.board: s.clear()
        self.game_state = GameState()
        self.go_btn.config(state="normal", text="START HAND", bg=C_BTN_SUCCESS)
        self.go_btn._bg, self.go_btn._hover_bg = C_BTN_SUCCESS, C_BTN_SUCCESS_HOVER
        self.action_panel.pack_forget()
        self.hole_entry.delete(0, tk.END); self.board_entry.delete(0, tk.END)
        self.refresh()

    def start_game(self):
        self.game_state.is_active = True
        self.go_btn.config(text="HAND IN-PROGRESS", state="disabled", bg=C_BTN_DARK)
        self.go_btn._bg = self.go_btn._hover_bg = C_BTN_DARK
        self.game_state.pot = self.small_blind.get() + self.big_blind.get()
        self.game_state.to_call = self.big_blind.get()
        self.game_state.players_in_hand = list(range(1, self.num_players.get() + 1))
        self.record_player_actions()
        self.refresh()
    
    def record_player_actions(self):
        for widget in self.action_panel.winfo_children(): widget.destroy()
        
        # Title and current state
        title = tk.Label(self.action_panel, text=f"Pot: ${self.game_state.pot:.2f} | To Call: ${self.game_state.to_call:.2f}",
                         bg=C_PANEL, fg=C_TEXT, font=("Arial", 10, "bold"))
        title.grid(row=0, column=0, columnspan=5, pady=10)
        
        your_seat = Position[self.position.get()].value
        row = 1
        for p_num in range(1, self.num_players.get() + 1):
            if p_num == your_seat or p_num not in self.game_state.players_in_hand:
                continue
                
            tk.Label(self.action_panel, text=f"Player {p_num}:", bg=C_PANEL, fg=C_TEXT).grid(row=row, column=0, padx=5, pady=5, sticky='e')
            StyledButton(self.action_panel, text="Fold", color=C_BTN_DANGER, hover_color=C_BTN_DANGER_HOVER, padx=8, pady=4, command=lambda p=p_num: self._handle_opponent_action(p, PlayerAction.FOLD)).grid(row=row, column=1, padx=2)
            StyledButton(self.action_panel, text="Call", color=C_BTN_SUCCESS, hover_color=C_BTN_SUCCESS_HOVER, padx=8, pady=4, command=lambda p=p_num: self._handle_opponent_action(p, PlayerAction.CALL)).grid(row=row, column=2, padx=2)
            
            raise_frame = tk.Frame(self.action_panel, bg=C_PANEL)
            raise_frame.grid(row=row, column=3, padx=2)
            raise_entry = tk.Entry(raise_frame, width=6, **self.STYLE_ENTRY)
            raise_entry.pack(side="left")
            StyledButton(raise_frame, text="Raise", color=C_BTN_WARNING, hover_color=C_BTN_WARNING_HOVER, padx=8, pady=4, 
                        command=lambda p=p_num, e=raise_entry: self._handle_opponent_action(p, PlayerAction.RAISE, e.get())).pack(side="left", padx=(3,0))
            row += 1

        self.action_panel.pack(fill="x", pady=(0, 10))

    def _handle_opponent_action(self, player_num, action, amount_str=None):
        if player_num not in self.game_state.players_in_hand: return

        if action == PlayerAction.FOLD:
            self.game_state.players_in_hand.remove(player_num)
        elif action == PlayerAction.CALL:
            self.game_state.pot += self.game_state.to_call
        elif action == PlayerAction.RAISE:
            try:
                amount = float(amount_str)
                if amount <= self.game_state.to_call: 
                    messagebox.showwarning("Invalid Raise", "Raise must be greater than the amount to call.")
                    return
                self.game_state.pot += amount
                self.game_state.to_call = amount  # Set new to_call amount (not the difference)
            except (ValueError, TypeError):
                messagebox.showerror("Invalid Amount", "Please enter a valid number for the raise.")
                return
        
        # Hide the row for the player who acted
        for widget in self.action_panel.winfo_children():
            if isinstance(widget, tk.Label) and widget.cget("text") == f"Player {player_num}:":
                row = widget.grid_info()["row"]
                for w in self.action_panel.grid_slaves(row=row):
                    w.grid_forget()
                break
        
        # Refresh the action panel with updated pot/to_call
        self.record_player_actions()
        
    def _mark_showdown(self, won: int):
        if self._last_decision_id is None: messagebox.showinfo("No Decision", "Analyze a hand first."); return
        with open_db() as db: db.execute("UPDATE decisions SET showdown_win=? WHERE id=?", (won, self._last_decision_id))
        log.info(f"Marked decision ID {self._last_decision_id} as {'WON' if won else 'LOST'}")
        self.refresh()

    def place_next_free(self, card: Card):
        if str(card) in self.used_cards: return
        for slot in self.hole + self.board:
            if slot.card is None: slot.set_card(card); self.grey_out(card); self.refresh(); return
        messagebox.showinfo("No Slot", "All card slots are full.")
        
    # ──────────────────────────────────────────────────────
    #  Main Refresh and UI Update Logic
    # ──────────────────────────────────────────────────────
    def refresh(self):
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]
        
        self._clear_output_panels()
        
        if len(hole) == 2:
            self._update_analysis_panel(hole, board)
        else:
            self._display_welcome_message()
            
        self._update_stats_panel()

    def _clear_output_panels(self):
        for w in (self.out_body, self.stats_text): w.config(state="normal"); w.delete("1.0", "end")
        self.decision_label.config(text="")
        
    def _update_analysis_panel(self, hole, board):
        pos = Position[self.position.get()]
        stack_bb = StackType(self.stack_type.get()).default_bb
        pot = self.game_state.pot if self.game_state.is_active else (self.small_blind.get() + self.big_blind.get())
        to_call = self.game_state.to_call if self.game_state.is_active else self.big_blind.get()
        num_players_in_hand = len(self.game_state.players_in_hand) if self.game_state.is_active else self.num_players.get()

        analysis = analyse_hand(hole, board, pos, stack_bb, pot, to_call, num_players_in_hand)
        tier = get_hand_tier(hole)
        board_str = ' '.join(map(str, board))
        self._last_decision_id = record_decision(analysis, pos, tier, stack_bb, pot, to_call, board_str)

        colors = {"RAISE": C_BTN_WARNING, "CALL": C_BTN_SUCCESS, "FOLD": C_BTN_DANGER, "CHECK": C_BTN_INFO}
        self.decision_label.config(text=f"→ {analysis.decision}", fg=colors.get(analysis.decision, C_TEXT))
        
        self.out_body.insert("end", f"Hand: {to_two_card_str(hole)} ({tier})\n", "header")
        self.out_body.insert("end", f"Board: {board_str or 'Pre-flop'} ({analysis.board_texture})\n", "dim")
        self.out_body.insert("end", f"Position: {pos.name} | Pot: ${pot:.2f} | SPR: {analysis.spr:.1f}\n\n", "dim")
        self.out_body.insert("end", "ADVICE\n", "subheader")
        self.out_body.insert("end", f"{get_position_advice(pos)}\n{get_hand_advice(tier, analysis.board_texture, analysis.spr)}\n\n", "dim")
        self.out_body.insert("end", "ANALYSIS\n", "subheader")
        self.out_body.insert("end", f"{analysis.reason}\n\n")
        self.out_body.insert("end", "EQUITY (Monte Carlo)\n", "subheader")
        edge = analysis.equity - analysis.required_eq
        self.out_body.insert("end", f"Your Equity:     {analysis.equity:6.1%}\n")
        self.out_body.insert("end", f"Required Equity: {analysis.required_eq:6.1%}\n")
        self.out_body.insert("end", f"Edge:           {edge:+6.1%}\n", "positive" if edge >= 0 else "negative")

    def _display_welcome_message(self):
        self.decision_label.config(text="Enter Cards to Begin", fg=C_TEXT_DIM)
        self.out_body.insert("end", "Welcome to Poker Assistant\n\n", "header")
        self.out_body.insert("end", "1. Type cards into the 'Fast Input' boxes (e.g., AhKc)\n", "dim")
        self.out_body.insert("end", "2. Or drag-and-drop cards from the deck\n", "dim")
        self.out_body.insert("end", "3. Set up game conditions and press START HAND\n", "dim")

    def _update_stats_panel(self):
        self.stats_text.insert("end", "WIN RATE (Showdown)\n", "header")
        with open_db() as db:
            wins, total = db.execute("SELECT SUM(showdown_win), COUNT(showdown_win) FROM decisions WHERE showdown_win IS NOT NULL").fetchone()
        if total: self.stats_text.insert("end", f"\n{wins}/{total} hands ({wins/total:.1%})\n", "positive" if wins/total >= 0.5 else "negative")
        else: self.stats_text.insert("end", "\nNo showdowns recorded\n", "dim")
        
        self.stats_text.insert("end", "\nRECENT DECISIONS\n", "header")
        # In a separate `with` block to ensure connection is closed.
        with open_db() as db:
            recent = db.execute("SELECT decision, COUNT(*) FROM decisions WHERE id > (SELECT MAX(id) - 20 FROM decisions) GROUP BY decision").fetchall()
        if recent:
            for dec, cnt in sorted(recent): self.stats_text.insert("end", f"\n{dec:<6}: {cnt:>2}", "positive" if dec in ("RAISE", "CALL") else "negative")
        else: self.stats_text.insert("end", "\nNo decisions recorded\n", "dim")

        for w in (self.out_body, self.stats_text): w.config(state="disabled")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        app = PokerAssistant()
        app.mainloop()
    except Exception as e:
        log.error("An unhandled exception occurred", exc_info=True)
        messagebox.showerror("Fatal Error", f"A critical error occurred: {e}")
