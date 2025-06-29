#!/usr/bin/env python3
"""
Fixed Poker GUI - Graphical interface for the Poker Assistant
Fixes GameState initialization and database connection issues
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from poker_modules import (
    Card, Suit, Position, analyse_hand, get_hand_tier,
    to_two_card_str, RANK_ORDER, GameState
)
from poker_init import open_db, initialise_db_if_needed

# ──────────────────────────────────────────────────────
#  GUI Application
# ──────────────────────────────────────────────────────
class PokerAssistantGUI(tk.Tk):
    """Main application window."""
    def __init__(self):
        super().__init__()

        # Basic window setup
        self.title("Poker Assistant")
        self.geometry("1100x720")
        self.minsize(980, 640)

        # Internal state
        self.cards: List[Card] = []
        self.board_cards: List[Card] = []
        self.game_state = GameState()
        self.conn = None
        self.cursor = None

        # DB
        self.init_database()

        # Build GUI
        self.build_gui()

        # Bind events
        self.bind_events()

        # Load saved session if exists
        self.load_session()

    # ──────────────── DB ────────────────
    def init_database(self):
        """Initialize the database connection."""
        try:
            # Ensure the database file and schema exist before opening a connection
            initialise_db_if_needed()
            self.conn = open_db()
            self.cursor = self.conn.cursor()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to initialize database: {e}")
            self.conn = None
            self.cursor = None

    # ──────────────── Styles ────────────────
    def setup_styles(self):
        """Configure ttk styles for modern appearance."""
        style = ttk.Style()
        style.theme_use('clam')

        # Configure colors
        self.colors = {
            'bg': '#1e1e1e',
            'fg': '#e0e0e0',
            'accent': '#2196f3',
            'highlight': '#2e2e2e'
        }

        self.configure(bg=self.colors['bg'])

        style.configure('TLabel',
                        background=self.colors['bg'],
                        foreground=self.colors['fg'])
        style.configure('TButton',
                        background=self.colors['accent'],
                        foreground='#ffffff')
        style.configure('TEntry',
                        fieldbackground=self.colors['highlight'],
                        foreground=self.colors['fg'])

    # ──────────────── GUI Build helpers ────────────────
    def build_gui(self):
        """Create and lay out widgets."""
        self.setup_styles()

        main_frame = ttk.Frame(self, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Left panel - Card inputs & game state
        self.build_input_panel(main_frame)

        # Right panel - Analysis output
        self.build_output_panel(main_frame)

        # Bottom panel - Action buttons
        self.build_action_panel(main_frame)

    def build_input_panel(self, parent):
        """Build the input controls panel."""
        input_frame = ttk.LabelFrame(parent, text="Game Input", padding="15")
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))

        row = 0

        # Title
        title_label = ttk.Label(input_frame, text="♠️ Poker Assistant ♥️", 
                                font=("Arial", 18, "bold"))
        title_label.grid(row=row, column=0, columnspan=4, pady=(0, 10))
        row += 1

        # Hand Cards section
        hand_label = ttk.Label(input_frame, text="Your Hand (2 cards):")
        hand_label.grid(row=row, column=0, sticky=tk.W)
        row += 1

        self.hand_entries: List[tk.Entry] = []
        for c in range(2):
            entry = ttk.Entry(input_frame, width=5, justify='center')
            entry.grid(row=row, column=c, padx=2)
            self.hand_entries.append(entry)

        row += 1

        # Board Cards section
        board_label = ttk.Label(input_frame, text="Board (0-5 cards):")
        board_label.grid(row=row, column=0, sticky=tk.W)
        row += 1

        self.board_entries: List[tk.Entry] = []
        for c in range(5):
            entry = ttk.Entry(input_frame, width=5, justify='center')
            entry.grid(row=row, column=c, padx=2, pady=(0, 5))
            self.board_entries.append(entry)

        row += 1

        # Position selector
        ttk.Label(input_frame, text="Position:").grid(row=row, column=0, sticky=tk.W)
        self.position_var = tk.StringVar(value=Position.UTG.name)
        pos_combo = ttk.Combobox(
            input_frame,
            textvariable=self.position_var,
            values=[p.name for p in Position],
            state="readonly",
            width=8
        )
        pos_combo.grid(row=row, column=1, sticky=tk.W)
        row += 1

        # Stack size in BB
        ttk.Label(input_frame, text="Stack (BB):").grid(row=row, column=0, sticky=tk.W)
        self.stack_var = tk.StringVar()
        stack_entry = ttk.Entry(input_frame, textvariable=self.stack_var, width=8)
        stack_entry.grid(row=row, column=1, sticky=tk.W)
        row += 1

        # Pot size
        ttk.Label(input_frame, text="Pot Size:").grid(row=row, column=0, sticky=tk.W)
        self.pot_var = tk.StringVar()
        pot_entry = ttk.Entry(input_frame, textvariable=self.pot_var, width=8)
        pot_entry.grid(row=row, column=1, sticky=tk.W)
        row += 1

        # Amount to call
        ttk.Label(input_frame, text="To Call:").grid(row=row, column=0, sticky=tk.W)
        self.call_var = tk.StringVar()
        call_entry = ttk.Entry(input_frame, textvariable=self.call_var, width=8)
        call_entry.grid(row=row, column=1, sticky=tk.W)
        row += 1

        # Analyse button
        analyse_btn = ttk.Button(input_frame, text="Analyse Hand", command=self.on_analyse)
        analyse_btn.grid(row=row, column=0, columnspan=2, pady=(10, 0), sticky=tk.EW)
        row += 1

        # Game-state serialization buttons
        save_btn = ttk.Button(input_frame, text="Save Session", command=self.save_session)
        load_btn = ttk.Button(input_frame, text="Load Session", command=self.load_session)
        save_btn.grid(row=row, column=0, pady=(10, 0), sticky=tk.EW)
        load_btn.grid(row=row, column=1, pady=(10, 0), sticky=tk.EW)

    def build_output_panel(self, parent):
        """Result/analysis text panel."""
        output_frame = ttk.LabelFrame(parent, text="Analysis Output", padding="15")
        output_frame.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)

        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            height=35,
            width=60,
            bg='#121212',
            fg='#f2f2f2',
            insertbackground='#f2f2f2'
        )
        self.output_text.grid(row=0, column=0, sticky=tk.NSEW)

    def build_action_panel(self, parent):
        """Buttons along the bottom."""
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky=tk.EW)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        clear_btn = ttk.Button(action_frame, text="Clear", command=self.clear_all)
        quit_btn = ttk.Button(action_frame, text="Quit", command=self.quit)

        clear_btn.grid(row=0, column=0, sticky=tk.EW)
        quit_btn.grid(row=0, column=1, sticky=tk.EW)

    # ──────────────── Events / Commands ────────────────
    def bind_events(self):
        self.bind("<Return>", lambda *_: self.on_analyse())

    def clear_all(self):
        """Reset every input + output field."""
        for e in self.hand_entries + self.board_entries:
            e.delete(0, tk.END)

        self.position_var.set(Position.UTG.name)
        self.stack_var.set("")
        self.pot_var.set("")
        self.call_var.set("")

        self.output_text.delete("1.0", tk.END)

    def on_analyse(self):
        """Run analysis then display + log result."""
        try:
            # Parse cards
            self.cards = self._parse_card_entries(self.hand_entries, expected=2)
            self.board_cards = self._parse_card_entries(self.board_entries, max_cards=5)

            # Update game state
            self.game_state.position = Position[self.position_var.get()]
            self.game_state.stack_bb = int(self.stack_var.get() or 0)
            self.game_state.pot = float(self.pot_var.get() or 0)
            self.game_state.to_call = float(self.call_var.get() or 0)
            self.game_state.board = self.board_cards

            # Analyse
            analysis = analyse_hand(self.cards, self.board_cards, self.game_state)
            tier = get_hand_tier(self.cards)

            # Display
            self._display_analysis(analysis, tier)

            # Persist
            self._save_to_db(analysis, tier)

        except ValueError as ve:
            messagebox.showerror("Input Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Unhandled error: {e}")

    # ──────────────── Parsing helpers ────────────────
    def _parse_card_entries(self, entries: List[tk.Entry], expected: int = None,
                            max_cards: int = None) -> List[Card]:
        """Parse card notation from entry widgets."""
        cards: List[Card] = []
        for entry in entries:
            text = entry.get().strip().upper()
            if not text:
                continue
            if not self._is_valid_card(text):
                raise ValueError(f"Invalid card: '{text}'")
            rank, suit = text[0], text[1]
            cards.append(Card(rank, Suit[suit]))
        if expected is not None and len(cards) != expected:
            raise ValueError(f"Expected {expected} cards but got {len(cards)}")
        if max_cards is not None and len(cards) > max_cards:
            raise ValueError(f"Maximum {max_cards} board cards allowed")
        return cards

    @staticmethod
    def _is_valid_card(card_str: str) -> bool:
        """Check syntax like 'AS', 'TD', '9H'."""
        return (
            len(card_str) == 2
            and card_str[0] in RANK_ORDER
            and card_str[1] in Suit.__members__
        )

    # ──────────────── Display helpers ────────────────
    def _display_analysis(self, analysis, tier: str):
        """Pretty-print analysis to the output pane."""
        self.output_text.delete("1.0", tk.END)
        out = self.output_text

        out.insert(tk.END, f"=== Hand Analysis ({datetime.now():%Y-%m-%d %H:%M:%S}) ===\n\n")
        out.insert(tk.END, f"Your Hand: {to_two_card_str(self.cards)} (Tier {tier})\n")
        if self.board_cards:
            out.insert(tk.END, f"Board: {', '.join(str(c) for c in self.board_cards)}\n")
        out.insert(tk.END, f"Position: {self.game_state.position.name}\n")
        out.insert(tk.END, f"Stack: {self.game_state.stack_bb} BB\n")
        out.insert(tk.END, f"Pot: {self.game_state.pot}\n")
        out.insert(tk.END, f"To Call: {self.game_state.to_call}\n\n")

        out.insert(tk.END, f"Decision: {analysis.decision}\n")
        out.insert(tk.END, f"SPR: {analysis.spr:.2f}\n")
        out.insert(tk.END, f"Board texture: {analysis.board_texture}\n")

    # ──────────────── Database helpers ────────────────
    def _save_to_db(self, analysis, tier: str):
        """Insert the decision into SQLite DB."""
        if not self.cursor:
            return
        try:
            self.cursor.execute(
                """
                INSERT INTO decisions
                    (position, hand_tier, stack_bb, pot, to_call, board,
                     decision, spr, board_texture)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.game_state.position.name,
                    tier,
                    self.game_state.stack_bb,
                    self.game_state.pot,
                    self.game_state.to_call,
                    ','.join(str(c) for c in self.board_cards),
                    analysis.decision,
                    analysis.spr,
                    analysis.board_texture,
                ),
            )
            self.conn.commit()
        except Exception as e:
            messagebox.showwarning("DB Warning", f"Could not save hand: {e}")

    # ──────────────── Session persistence ────────────────
    def save_session(self):
        """Dump current GUI state into a .json file."""
        data = {
            'hand': [e.get() for e in self.hand_entries],
            'board': [e.get() for e in self.board_entries],
            'position': self.position_var.get(),
            'stack': self.stack_var.get(),
            'pot': self.pot_var.get(),
            'to_call': self.call_var.get(),
        }
        try:
            with open("session.json", "w") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Session Saved", "Session saved to session.json")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save session: {e}")

    def load_session(self):
        """Restore GUI state from previously saved .json file."""
        if not os.path.exists("session.json"):
            return
        try:
            with open("session.json", "r") as f:
                data = json.load(f)
            for entry, val in zip(self.hand_entries, data.get('hand', [])):
                entry.delete(0, tk.END)
                entry.insert(0, val)
            for entry, val in zip(self.board_entries, data.get('board', [])):
                entry.delete(0, tk.END)
                entry.insert(0, val)
            self.position_var.set(data.get('position', Position.UTG.name))
            self.stack_var.set(data.get('stack', ''))
            self.pot_var.set(data.get('pot', ''))
            self.call_var.set(data.get('to_call', ''))
            messagebox.showinfo("Session Loaded", "Session loaded from session.json")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load session: {e}")

# ──────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────
if __name__ == "__main__":
    app = PokerAssistantGUI()
    app.mainloop()