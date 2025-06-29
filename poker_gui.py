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


class PokerAssistant:
    """Main GUI application for the Poker Assistant."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎯 Poker Assistant - Professional Texas Hold'em Analyzer")
        self.root.geometry("1200x800")
        
        # Initialize database
        self.init_database()
        
        # State variables - Don't initialize GameState yet
        self.game_state = None  # Will be created when needed
        self.hole_cards = []
        self.board_cards = []
        self.analysis_history = []
        
        # Style configuration
        self.setup_styles()
        
        # Build GUI
        self.build_gui()
        
        # Bind events
        self.bind_events()
        
        # Load saved session if exists
        self.load_session()
    
    def init_database(self):
        """Initialize the database connection."""
        try:
            # open_db() returns just a connection, not a tuple
            self.conn = open_db()
            self.cursor = self.conn.cursor()
            initialise_db_if_needed(self.cursor)
            self.conn.commit()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to initialize database: {e}")
            self.conn = None
            self.cursor = None
    
    def setup_styles(self):
        """Configure ttk styles for modern appearance."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        self.colors = {
            'bg': '#1e1e1e',
            'fg': '#ffffff',
            'button': '#2d2d2d',
            'button_hover': '#3d3d3d',
            'accent': '#007acc',
            'success': '#4caf50',
            'warning': '#ff9800',
            'danger': '#f44336',
            'card_red': '#ff4444',
            'card_black': '#000000'
        }
        
        # Configure root window
        self.root.configure(bg=self.colors['bg'])
        
        # Configure styles
        style.configure('Title.TLabel', font=('Arial', 24, 'bold'))
        style.configure('Heading.TLabel', font=('Arial', 14, 'bold'))
        style.configure('Card.TButton', font=('Arial', 16, 'bold'), width=4)
        style.configure('Action.TButton', font=('Arial', 12), padding=10)
    
    def build_gui(self):
        """Build the main GUI layout."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=2)
        
        # Left panel - Input controls
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
                               style='Title.TLabel')
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # Position selection
        ttk.Label(input_frame, text="Position:", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.position_var = tk.StringVar(value="BTN")
        position_frame = ttk.Frame(input_frame)
        position_frame.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        positions = [
            ("BTN", "BTN"), ("SB", "SB"), ("BB", "BB"),
            ("UTG", "UTG"), ("MP", "MP1"), ("CO", "CO")
        ]
        
        for i, (text, value) in enumerate(positions):
            ttk.Radiobutton(position_frame, text=text, variable=self.position_var,
                          value=value).grid(row=0, column=i, padx=5)
        row += 1
        
        # Stack size
        ttk.Label(input_frame, text="Stack (BB):", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.stack_var = tk.StringVar(value="50")
        stack_spinbox = ttk.Spinbox(input_frame, from_=1, to=1000, 
                                   textvariable=self.stack_var, width=10)
        stack_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Pot size
        ttk.Label(input_frame, text="Pot Size (BB):", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.pot_var = tk.StringVar(value="10")
        pot_spinbox = ttk.Spinbox(input_frame, from_=0, to=1000, 
                                 textvariable=self.pot_var, width=10)
        pot_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # To call
        ttk.Label(input_frame, text="To Call (BB):", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.to_call_var = tk.StringVar(value="2")
        call_spinbox = ttk.Spinbox(input_frame, from_=0, to=1000, 
                                  textvariable=self.to_call_var, width=10)
        call_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Number of players
        ttk.Label(input_frame, text="Players:", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.players_var = tk.StringVar(value="6")
        players_spinbox = ttk.Spinbox(input_frame, from_=2, to=9, 
                                     textvariable=self.players_var, width=10)
        players_spinbox.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Separator
        ttk.Separator(input_frame, orient='horizontal').grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Card selection
        self.build_card_selection(input_frame, row)
    
    def build_card_selection(self, parent, start_row):
        """Build the card selection interface."""
        row = start_row
        
        # Hole cards
        ttk.Label(parent, text="Hole Cards:", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.hole_frame = ttk.Frame(parent)
        self.hole_frame.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        self.hole_labels = []
        for i in range(2):
            label = ttk.Label(self.hole_frame, text="--", font=('Arial', 20), 
                            relief=tk.RIDGE, width=4)
            label.grid(row=0, column=i, padx=5)
            self.hole_labels.append(label)
        
        ttk.Button(self.hole_frame, text="Clear", 
                  command=self.clear_hole_cards).grid(row=0, column=2, padx=10)
        row += 1
        
        # Board cards
        ttk.Label(parent, text="Board:", style='Heading.TLabel').grid(
            row=row, column=0, sticky=tk.W, pady=5)
        
        self.board_frame = ttk.Frame(parent)
        self.board_frame.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        self.board_labels = []
        for i in range(5):
            label = ttk.Label(self.board_frame, text="--", font=('Arial', 20), 
                            relief=tk.RIDGE, width=4)
            label.grid(row=0, column=i, padx=5)
            self.board_labels.append(label)
        
        ttk.Button(self.board_frame, text="Clear", 
                  command=self.clear_board_cards).grid(row=0, column=5, padx=10)
        row += 1
        
        # Card picker
        ttk.Label(parent, text="Select Cards:", style='Heading.TLabel').grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        row += 1
        
        self.build_card_picker(parent, row)
    
    def build_card_picker(self, parent, start_row):
        """Build the card picker grid."""
        picker_frame = ttk.Frame(parent)
        picker_frame.grid(row=start_row, column=0, columnspan=3, pady=10)
        
        # Create card buttons
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        suits = [Suit.SPADE, Suit.HEART, Suit.DIAMOND, Suit.CLUB]
        
        for r, rank in enumerate(ranks):
            for s, suit in enumerate(suits):
                btn = tk.Button(picker_frame, text=f"{rank}{suit.value}",
                              font=('Arial', 14, 'bold'),
                              width=4, height=2,
                              fg=self.colors['card_red'] if suit.color == 'red' else self.colors['card_black'],
                              command=lambda r=rank, s=suit: self.select_card(r, s))
                btn.grid(row=r, column=s, padx=2, pady=2)
    
    def build_output_panel(self, parent):
        """Build the analysis output panel."""
        output_frame = ttk.LabelFrame(parent, text="Analysis Results", padding="15")
        output_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Results text area
        self.results_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD,
                                                     width=60, height=30,
                                                     font=('Consolas', 11))
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure tags for colored text
        self.results_text.tag_configure("title", font=('Arial', 16, 'bold'))
        self.results_text.tag_configure("heading", font=('Arial', 12, 'bold'))
        self.results_text.tag_configure("success", foreground=self.colors['success'])
        self.results_text.tag_configure("warning", foreground=self.colors['warning'])
        self.results_text.tag_configure("danger", foreground=self.colors['danger'])
        self.results_text.tag_configure("info", foreground=self.colors['accent'])
        
        # Configure grid weights
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
    
    def build_action_panel(self, parent):
        """Build the action buttons panel."""
        action_frame = ttk.Frame(parent)
        action_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        # Analysis button
        self.analyze_btn = ttk.Button(action_frame, text="🎯 Analyze Hand",
                                     command=self.analyze_hand,
                                     style='Action.TButton')
        self.analyze_btn.grid(row=0, column=0, padx=5)
        
        # Save session button
        ttk.Button(action_frame, text="💾 Save Session",
                  command=self.save_session,
                  style='Action.TButton').grid(row=0, column=1, padx=5)
        
        # Load session button
        ttk.Button(action_frame, text="📂 Load Session",
                  command=self.load_session,
                  style='Action.TButton').grid(row=0, column=2, padx=5)
        
        # Help button
        ttk.Button(action_frame, text="❓ Help",
                  command=self.show_help,
                  style='Action.TButton').grid(row=0, column=3, padx=5)
        
        # Exit button
        ttk.Button(action_frame, text="❌ Exit",
                  command=self.exit_app,
                  style='Action.TButton').grid(row=0, column=4, padx=5)
    
    def bind_events(self):
        """Bind keyboard shortcuts and events."""
        self.root.bind('<Control-a>', lambda e: self.analyze_hand())
        self.root.bind('<Control-s>', lambda e: self.save_session())
        self.root.bind('<Control-l>', lambda e: self.load_session())
        self.root.bind('<Control-h>', lambda e: self.show_help())
        self.root.bind('<Control-q>', lambda e: self.exit_app())
        self.root.bind('<Escape>', lambda e: self.clear_all_cards())
    
    def select_card(self, rank: str, suit: Suit):
        """Handle card selection."""
        card = Card(rank, suit)
        
        # Check if card already selected
        if card in self.hole_cards or card in self.board_cards:
            messagebox.showwarning("Duplicate Card", 
                                 f"{card} is already selected!")
            return
        
        # Add to hole cards or board
        if len(self.hole_cards) < 2:
            self.hole_cards.append(card)
            self.update_card_display()
        elif len(self.board_cards) < 5:
            self.board_cards.append(card)
            self.update_card_display()
        else:
            messagebox.showinfo("Cards Full", 
                              "All card slots are filled. Clear some cards first.")
    
    def update_card_display(self):
        """Update the card display labels."""
        # Update hole cards
        for i, label in enumerate(self.hole_labels):
            if i < len(self.hole_cards):
                card = self.hole_cards[i]
                label.config(text=str(card),
                           foreground=self.colors['card_red'] if card.suit.color == 'red' 
                           else self.colors['card_black'])
            else:
                label.config(text="--", foreground='black')
        
        # Update board cards
        for i, label in enumerate(self.board_labels):
            if i < len(self.board_cards):
                card = self.board_cards[i]
                label.config(text=str(card),
                           foreground=self.colors['card_red'] if card.suit.color == 'red' 
                           else self.colors['card_black'])
            else:
                label.config(text="--", foreground='black')
    
    def clear_hole_cards(self):
        """Clear hole cards."""
        self.hole_cards = []
        self.update_card_display()
    
    def clear_board_cards(self):
        """Clear board cards."""
        self.board_cards = []
        self.update_card_display()
    
    def clear_all_cards(self):
        """Clear all cards."""
        self.clear_hole_cards()
        self.clear_board_cards()
    
    def analyze_hand(self):
        """Perform hand analysis."""
        # Validate inputs
        if len(self.hole_cards) != 2:
            messagebox.showwarning("Invalid Input", 
                                 "Please select exactly 2 hole cards.")
            return
        
        try:
            # Get input values
            position = Position[self.position_var.get()]
            stack_bb = float(self.stack_var.get())
            pot = float(self.pot_var.get())
            to_call = float(self.to_call_var.get())
            num_players = int(self.players_var.get())
            
            # Create GameState
            self.game_state = GameState(
                position=position,
                stack_bb=stack_bb,
                pot=pot,
                to_call=to_call,
                num_players=num_players,
                hole_cards=self.hole_cards,
                board=self.board_cards
            )
            
            # Perform analysis
            analysis = analyse_hand(
                hole=self.hole_cards,
                board=self.board_cards,
                position=position,
                stack_bb=stack_bb,
                pot=pot,
                to_call=to_call,
                num_players=num_players
            )
            
            # Display results
            self.display_analysis(analysis)
            
            # Save to history
            self.save_to_history(analysis)
            
            # Log to database
            self.log_hand_to_db(analysis)
            
        except Exception as e:
            messagebox.showerror("Analysis Error", 
                               f"Error analyzing hand: {str(e)}")
    
    def display_analysis(self, analysis):
        """Display analysis results in the output panel."""
        self.results_text.delete(1.0, tk.END)
        
        # Title
        self.results_text.insert(tk.END, "🎯 HAND ANALYSIS RESULTS\n", "title")
        self.results_text.insert(tk.END, "=" * 50 + "\n\n")
        
        # Decision
        decision_color = {
            "FOLD": "danger",
            "CALL": "warning",
            "RAISE": "success",
            "ALL_IN": "success"
        }.get(analysis.decision, "info")
        
        self.results_text.insert(tk.END, "DECISION: ", "heading")
        self.results_text.insert(tk.END, f"{analysis.decision}\n", decision_color)
        self.results_text.insert(tk.END, f"Reason: {analysis.reason}\n\n")
        
        # Hand information
        self.results_text.insert(tk.END, "HAND INFORMATION\n", "heading")
        self.results_text.insert(tk.END, "-" * 30 + "\n")
        self.results_text.insert(tk.END, f"Hole Cards: {to_two_card_str(self.hole_cards)}\n")
        self.results_text.insert(tk.END, f"Hand Tier: {analysis.hand_tier}\n")
        self.results_text.insert(tk.END, f"Position: {self.position_var.get()}\n")
        self.results_text.insert(tk.END, f"Board Texture: {analysis.board_texture}\n\n")
        
        # Equity and odds
        self.results_text.insert(tk.END, "EQUITY & ODDS\n", "heading")
        self.results_text.insert(tk.END, "-" * 30 + "\n")
        self.results_text.insert(tk.END, f"Your Equity: {analysis.equity:.1%}\n")
        self.results_text.insert(tk.END, f"Pot Odds: {analysis.pot_odds:.1%}\n")
        self.results_text.insert(tk.END, f"Required Equity: {analysis.required_eq:.1%}\n\n")
        
        # Expected value
        self.results_text.insert(tk.END, "EXPECTED VALUE\n", "heading")
        self.results_text.insert(tk.END, "-" * 30 + "\n")
        self.results_text.insert(tk.END, f"EV Call: {analysis.ev_call:+.2f} BB\n")
        self.results_text.insert(tk.END, f"EV Fold: {analysis.ev_fold:+.2f} BB\n\n")
        
        # Additional notes
        self.results_text.insert(tk.END, "NOTES\n", "heading")
        self.results_text.insert(tk.END, "-" * 30 + "\n")
        self.results_text.insert(tk.END, f"{analysis.position_notes}\n")
        
        if analysis.pot_committed:
            self.results_text.insert(tk.END, "\n⚠️ POT COMMITTED\n", "warning")
    
    def save_to_history(self, analysis):
        """Save analysis to history."""
        self.analysis_history.append({
            'timestamp': datetime.now().isoformat(),
            'hole_cards': [str(c) for c in self.hole_cards],
            'board': [str(c) for c in self.board_cards],
            'position': self.position_var.get(),
            'stack': self.stack_var.get(),
            'pot': self.pot_var.get(),
            'to_call': self.to_call_var.get(),
            'players': self.players_var.get(),
            'decision': analysis.decision,
            'equity': analysis.equity,
            'ev_call': analysis.ev_call
        })
    
    def log_hand_to_db(self, analysis):
        """Log hand to database."""
        if not self.cursor:
            return
        
        try:
            self.cursor.execute('''
                INSERT INTO hands (timestamp, hole_cards, board, position, 
                                 stack_bb, pot, to_call, num_players, 
                                 decision, equity, ev)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                to_two_card_str(self.hole_cards),
                ' '.join(str(c) for c in self.board_cards),
                self.position_var.get(),
                float(self.stack_var.get()),
                float(self.pot_var.get()),
                float(self.to_call_var.get()),
                int(self.players_var.get()),
                analysis.decision,
                analysis.equity,
                analysis.ev_call
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Database error: {e}")
    
    def save_session(self):
        """Save current session to file."""
        session_data = {
            'timestamp': datetime.now().isoformat(),
            'current_state': {
                'hole_cards': [str(c) for c in self.hole_cards],
                'board': [str(c) for c in self.board_cards],
                'position': self.position_var.get(),
                'stack': self.stack_var.get(),
                'pot': self.pot_var.get(),
                'to_call': self.to_call_var.get(),
                'players': self.players_var.get()
            },
            'history': self.analysis_history
        }
        
        filename = f"poker_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(session_data, f, indent=2)
            messagebox.showinfo("Session Saved", 
                              f"Session saved to {filename}")
        except Exception as e:
            messagebox.showerror("Save Error", 
                               f"Failed to save session: {e}")
    
    def load_session(self):
        """Load session from file."""
        from tkinter import filedialog
        
        filename = filedialog.askopenfilename(
            title="Select session file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                session_data = json.load(f)
            
            # Restore current state
            state = session_data.get('current_state', {})
            
            # Clear cards
            self.clear_all_cards()
            
            # Restore hole cards
            for card_str in state.get('hole_cards', []):
                if len(card_str) >= 2:
                    rank = card_str[0]
                    suit_char = card_str[1]
                    suit = next((s for s in Suit if s.value == suit_char), None)
                    if suit:
                        self.hole_cards.append(Card(rank, suit))
            
            # Restore board
            for card_str in state.get('board', []):
                if len(card_str) >= 2:
                    rank = card_str[0]
                    suit_char = card_str[1]
                    suit = next((s for s in Suit if s.value == suit_char), None)
                    if suit:
                        self.board_cards.append(Card(rank, suit))
            
            # Update displays
            self.update_card_display()
            
            # Restore other values
            self.position_var.set(state.get('position', 'BTN'))
            self.stack_var.set(state.get('stack', '50'))
            self.pot_var.set(state.get('pot', '10'))
            self.to_call_var.set(state.get('to_call', '2'))
            self.players_var.set(state.get('players', '6'))
            
            # Restore history
            self.analysis_history = session_data.get('history', [])
            
            messagebox.showinfo("Session Loaded", 
                              "Session loaded successfully!")
            
        except Exception as e:
            messagebox.showerror("Load Error", 
                               f"Failed to load session: {e}")
    
    def show_help(self):
        """Show help dialog."""
        help_text = """
🎯 POKER ASSISTANT HELP
========================

SHORTCUTS:
• Ctrl+A: Analyze hand
• Ctrl+S: Save session
• Ctrl+L: Load session
• Ctrl+H: Show help
• Ctrl+Q: Exit
• Escape: Clear all cards

HOW TO USE:
1. Select your position at the table
2. Enter stack size, pot size, and amount to call
3. Click cards to select your hole cards (2 cards)
4. Optionally select board cards (up to 5)
5. Click "Analyze Hand" for recommendations

HAND TIERS:
• PREMIUM: AA, KK, QQ, JJ, AKs
• STRONG: TT, 99, 88, AQ, AJs, KQs
• MEDIUM: 77-55, AT, KQ, QJ, JT suited
• PLAYABLE: Small pairs, suited connectors
• MARGINAL: Weak suited cards, A-rag
• WEAK: Everything else

DECISION GUIDE:
• RAISE: Strong hand, positive EV
• CALL: Marginally profitable
• FOLD: Negative EV
• Position matters - play tighter early!
        """
        
        help_window = tk.Toplevel(self.root)
        help_window.title("Help")
        help_window.geometry("600x700")
        
        text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, 
                                        width=70, height=35,
                                        font=('Consolas', 10))
        text.pack(padx=10, pady=10)
        text.insert(tk.END, help_text)
        text.config(state=tk.DISABLED)
        
        ttk.Button(help_window, text="Close", 
                  command=help_window.destroy).pack(pady=10)
    
    def exit_app(self):
        """Exit the application."""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            if self.conn:
                self.conn.close()
            self.root.quit()
    
    def run(self):
        """Start the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point."""
    app = PokerAssistant()
    app.run()


if __name__ == "__main__":
    main()
