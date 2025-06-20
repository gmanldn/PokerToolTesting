from __future__ import annotations
"""PokerTool5 – Enhanced with visual card selection and drag-drop interface
--------------------------------------------------------------------------------------
Features:
- Visual card grid for selection
- Drag and drop card placement
- Large, scalable card icons
- Visual slots for hole cards and community cards
- Graphical table representation
- Advanced metrics and strategy recommendations
"""

import logging
import random
import math
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Dict, Callable, Any, Set
from itertools import combinations
from dataclasses import dataclass
from enum import Enum

import tkinter as tk
from tkinter import ttk, messagebox, font

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
# Database Setup
# ---------------------------------------------------------------------------
Base = declarative_base()

class GameSession(Base):
    __tablename__ = 'game_sessions'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    position = Column(Integer)
    hand_cards = Column(String(10))
    community_cards = Column(String(20))
    action_taken = Column(String(50))
    pot_size = Column(Float)
    stack_size = Column(Float)
    result = Column(String(20))
    notes = Column(Text)

class PokerDatabase:
    def __init__(self, db_path: str = "poker_sessions.db"):
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def save_session(self, session_data: dict):
        with self.get_session() as session:
            game_session = GameSession(**session_data)
            session.add(game_session)

# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------
SUITS = ["♠", "♥", "♦", "♣"]
SUIT_COLORS = {"♠": "black", "♣": "black", "♥": "red", "♦": "red"}
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
    1: 0.85,
    2: 0.90,
    3: 0.95,
    4: 1.10,
    5: 0.95,
    6: 1.00
}

# Enhanced position factors for various strategies
POSITION_BULLY_FACTORS = {
    1: 0.4,   # UTG - Very limited bullying potential
    2: 0.6,   # MP - Some bullying potential
    3: 0.85,  # CO - Strong bullying position
    4: 1.0,   # BTN - Best bullying position
    5: 0.7,   # SB - Moderate (out of position post-flop)
    6: 0.5    # BB - Limited (worst position post-flop)
}

HAND_TIERS = {
    'premium': ['AA', 'KK', 'QQ', 'JJ', 'AKs', 'AK'],
    'strong': ['TT', '99', 'AQs', 'AQ', 'AJs', 'KQs', 'ATs'],
    'decent': ['88', '77', 'AJ', 'KQ', 'QJs', 'JTs', 'A9s', 'KJs'],
    'marginal': ['66', '55', 'AT', 'KJ', 'QT', 'JT', 'A8s', 'K9s', 'Q9s'],
    'weak': ['44', '33', '22', 'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s'],
    'speculative': ['T9s', '98s', '87s', '76s', '65s', '54s', 'K8s', 'Q8s', 'J9s']
}

# Hand strength factors
HAND_BULLY_FACTORS = {
    'premium': 1.0,
    'strong': 0.85,
    'decent': 0.7,
    'marginal': 0.55,
    'weak': 0.45,
    'speculative': 0.6,
    'trash': 0.3
}

# Opponent types
class OpponentType(Enum):
    TIGHT_PASSIVE = "Tight-Passive (Rock)"
    TIGHT_AGGRESSIVE = "Tight-Aggressive (TAG)"
    LOOSE_PASSIVE = "Loose-Passive (Calling Station)"
    LOOSE_AGGRESSIVE = "Loose-Aggressive (LAG)"
    UNKNOWN = "Unknown"

@dataclass
class TableMetrics:
    """Advanced table metrics for decision making"""
    pot_size: float = 0.0
    pot_odds: float = 0.0
    implied_odds: float = 0.0
    spr: float = 0.0  # Stack-to-pot ratio
    m_ratio: float = 0.0  # Tournament metric
    fold_equity: float = 0.0
    ev: float = 0.0  # Expected value
    hand_equity: float = 0.0
    bluff_to_value_ratio: float = 0.0

class Card:
    def __init__(self, rank: str, suit: str) -> None:
        self.rank = rank
        self.suit = suit
        self.value = RANK_VALUES[rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return f"Card({self.rank}, {self.suit})"

    def __eq__(self, other) -> bool:
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))

def create_deck() -> List[Card]:
    return [Card(r, s) for s in SUITS for r in RANKS]

def cards_to_string(cards: List[Card]) -> str:
    """Convert list of cards to string representation"""
    if not cards:
        return ""
    
    # Handle pairs and suited/offsuit hands
    if len(cards) == 2:
        c1, c2 = cards
        if c1.rank == c2.rank:
            return f"{c1.rank}{c2.rank}"
        elif c1.suit == c2.suit:
            return f"{max(c1.rank, c2.rank, key=lambda x: RANK_VALUES[x])}{min(c1.rank, c2.rank, key=lambda x: RANK_VALUES[x])}s"
        else:
            return f"{max(c1.rank, c2.rank, key=lambda x: RANK_VALUES[x])}{min(c1.rank, c2.rank, key=lambda x: RANK_VALUES[x])}"
    
    return "".join(str(c) for c in cards)

def get_hand_tier(cards: List[Card]) -> str:
    """Determine the tier of a poker hand"""
    if len(cards) != 2:
        return 'trash'
    
    hand_string = cards_to_string(cards)
    
    for tier, hands in HAND_TIERS.items():
        if hand_string in hands:
            return tier
    
    return 'trash'

def evaluate_hand_strength(hole_cards: List[Card], community_cards: List[Card] = None) -> float:
    """Evaluate the strength of a poker hand (0.0 to 1.0)"""
    if community_cards is None:
        community_cards = []
    
    # Pre-flop evaluation
    if not community_cards:
        tier = get_hand_tier(hole_cards)
        tier_strengths = {
            'premium': 0.95,
            'strong': 0.80,
            'decent': 0.65,
            'marginal': 0.45,
            'weak': 0.30,
            'speculative': 0.35,
            'trash': 0.15
        }
        return tier_strengths.get(tier, 0.15)
    
    # Post-flop evaluation (simplified)
    all_cards = hole_cards + community_cards
    if len(all_cards) < 5:
        return 0.5  # Placeholder for incomplete hands
    
    # Simple hand ranking evaluation
    return evaluate_five_card_hand(all_cards)

def evaluate_five_card_hand(cards: List[Card]) -> float:
    """Simplified 5-card hand evaluation"""
    if len(cards) < 5:
        return 0.5
    
    # Take the best 5 cards from available cards
    best_cards = sorted(cards, key=lambda c: c.value, reverse=True)[:5]
    
    # Check for pairs, straights, flushes (simplified)
    ranks = [c.rank for c in best_cards]
    suits = [c.suit for c in best_cards]
    
    # Count rank frequencies
    rank_counts = {}
    for rank in ranks:
        rank_counts[rank] = rank_counts.get(rank, 0) + 1
    
    counts = sorted(rank_counts.values(), reverse=True)
    
    # Check for flush
    is_flush = len(set(suits)) == 1
    
    # Check for straight
    values = sorted([RANK_VALUES[r] for r in ranks])
    is_straight = all(values[i] == values[i-1] + 1 for i in range(1, len(values)))
    
    # Hand rankings (simplified)
    if is_straight and is_flush:
        return 0.99  # Straight flush
    elif counts[0] == 4:
        return 0.95  # Four of a kind
    elif counts[0] == 3 and counts[1] == 2:
        return 0.90  # Full house
    elif is_flush:
        return 0.85  # Flush
    elif is_straight:
        return 0.80  # Straight
    elif counts[0] == 3:
        return 0.70  # Three of a kind
    elif counts[0] == 2 and counts[1] == 2:
        return 0.60  # Two pair
    elif counts[0] == 2:
        return 0.45  # One pair
    else:
        return 0.30  # High card

def calculate_pot_odds(pot_size: float, call_amount: float) -> float:
    """Calculate pot odds"""
    if call_amount <= 0:
        return float('inf')
    return pot_size / call_amount

def calculate_spr(stack_size: float, pot_size: float) -> float:
    """Calculate Stack-to-Pot Ratio"""
    if pot_size <= 0:
        return float('inf')
    return stack_size / pot_size

def calculate_advanced_metrics(
    hole_cards: List[Card],
    community_cards: List[Card],
    pot_size: float,
    call_amount: float,
    stack_size: float,
    position: int,
    num_opponents: int = 1
) -> TableMetrics:
    """Calculate comprehensive table metrics"""
    
    metrics = TableMetrics()
    metrics.pot_size = pot_size
    
    # Basic calculations
    if call_amount > 0:
        metrics.pot_odds = calculate_pot_odds(pot_size, call_amount)
    
    metrics.spr = calculate_spr(stack_size, pot_size)
    
    # Hand equity (simplified)
    metrics.hand_equity = evaluate_hand_strength(hole_cards, community_cards)
    
    # Fold equity estimation (based on position and aggression)
    position_factor = POSITION_BULLY_FACTORS.get(position, 0.5)
    metrics.fold_equity = min(0.8, position_factor * 0.6 + (1.0 / max(1, num_opponents)) * 0.4)
    
    # Expected value calculation (simplified)
    win_prob = metrics.hand_equity
    fold_prob = metrics.fold_equity
    
    if call_amount > 0:
        metrics.ev = (win_prob * pot_size) - ((1 - win_prob) * call_amount)
    
    # Implied odds (simplified estimation)
    if metrics.hand_equity > 0.3:  # Drawing hands
        metrics.implied_odds = metrics.pot_odds * (1 + min(2.0, metrics.spr * 0.1))
    else:
        metrics.implied_odds = metrics.pot_odds
    
    return metrics

class DraggableCard(tk.Label):
    """A card widget that can be dragged"""
    
    def __init__(self, parent, card: Card, card_size: int = 60):
        super().__init__(parent)
        self.card = card
        self.card_size = card_size
        self.original_parent = parent
        self.is_selected = False
        
        # Configure the card appearance
        self.configure(
            text=f"{card.rank}\n{card.suit}",
            font=('Arial', card_size // 3, 'bold'),
            fg=SUIT_COLORS[card.suit],
            bg='white',
            relief='raised',
            bd=2,
            width=card_size // 10,
            height=card_size // 20,
            cursor='hand2'
        )
        
        # Bind drag events
        self.bind('<Button-1>', self.on_click)
        self.bind('<B1-Motion>', self.on_drag)
        self.bind('<ButtonRelease-1>', self.on_release)
        
        self.start_x = 0
        self.start_y = 0
        
    def on_click(self, event):
        """Handle click event"""
        self.start_x = event.x
        self.start_y = event.y
        self.lift()  # Bring to front
        
    def on_drag(self, event):
        """Handle drag event"""
        x = self.winfo_x() + event.x - self.start_x
        y = self.winfo_y() + event.y - self.start_y
        self.place(x=x, y=y)
        
    def on_release(self, event):
        """Handle release event"""
        # Find which drop zone we're over
        x = self.winfo_rootx()
        y = self.winfo_rooty()
        
        # Get the widget under the cursor
        target = self.winfo_containing(x, y)
        
        # Check if it's a valid drop zone
        if hasattr(target, 'accept_drop'):
            target.accept_drop(self)
        else:
            # Return to original position if not dropped on valid zone
            self.reset_position()
    
    def reset_position(self):
        """Reset card to original position"""
        self.place_forget()
        self.pack(side='left', padx=2, pady=2)

class CardSlot(tk.Frame):
    """A slot that can accept dropped cards"""
    
    def __init__(self, parent, slot_name: str, card_size: int = 60, on_update=None):
        super().__init__(parent, bg='darkgreen', relief='sunken', bd=3)
        self.slot_name = slot_name
        self.card_size = card_size
        self.on_update = on_update
        self.current_card = None
        
        # Size configuration
        self.configure(width=card_size + 10, height=int(card_size * 1.4) + 10)
        self.pack_propagate(False)
        
        # Empty slot label
        self.empty_label = tk.Label(
            self,
            text=slot_name,
            bg='darkgreen',
            fg='white',
            font=('Arial', 10)
        )
        self.empty_label.pack(expand=True)
        
    def accept_drop(self, card_widget: DraggableCard):
        """Accept a dropped card"""
        # Remove any existing card
        if self.current_card:
            self.current_card.reset_position()
        
        # Clear the empty label
        self.empty_label.pack_forget()
        
        # Place the new card
        card_widget.place_forget()
        card_widget.original_parent = self
        self.current_card = card_widget
        
        # Create a display copy in the slot
        display_card = tk.Label(
            self,
            text=f"{card_widget.card.rank}\n{card_widget.card.suit}",
            font=('Arial', self.card_size // 3, 'bold'),
            fg=SUIT_COLORS[card_widget.card.suit],
            bg='white',
            relief='raised',
            bd=2
        )
        display_card.pack(expand=True, fill='both', padx=5, pady=5)
        
        # Store reference to display
        self.display_widget = display_card
        
        # Trigger update callback
        if self.on_update:
            self.on_update()
    
    def clear(self):
        """Clear the slot"""
        if hasattr(self, 'display_widget'):
            self.display_widget.destroy()
        self.current_card = None
        self.empty_label.pack(expand=True)
    
    def get_card(self) -> Optional[Card]:
        """Get the card in this slot"""
        return self.current_card.card if self.current_card else None

class TableVisualization(tk.Frame):
    """GUI component for table visualization with card slots"""
    
    def __init__(self, parent, on_update=None):
        super().__init__(parent)
        self.on_update = on_update
        self.card_size = 60
        
        # Main canvas for table
        self.canvas = tk.Canvas(self, width=600, height=400, bg='darkgreen')
        self.canvas.pack(padx=10, pady=10)
        
        # Card slots
        self.hole_card_slots = []
        self.community_card_slots = []
        
        self.setup_table()
        
    def setup_table(self):
        """Setup the poker table with card slots"""
        # Draw table
        self.canvas.create_oval(100, 100, 500, 300, fill='darkgreen', outline='brown', width=5)
        
        # Draw positions
        positions = [
            (300, 110, "BTN"),   # Button
            (220, 130, "SB"),    # Small Blind
            (180, 200, "BB"),    # Big Blind
            (220, 270, "UTG"),   # Under the Gun
            (300, 290, "MP"),    # Middle Position
            (380, 270, "CO"),    # Cut Off
        ]
        
        for x, y, pos in positions:
            self.canvas.create_oval(x-20, y-20, x+20, y+20, fill='lightblue', outline='black')
            self.canvas.create_text(x, y-30, text=pos, font=('Arial', 8, 'bold'))
        
        # Create hole card slots
        hole_frame = tk.Frame(self.canvas, bg='darkgreen')
        self.canvas.create_window(300, 350, window=hole_frame)
        
        self.canvas.create_text(300, 320, text="Your Hole Cards", fill='white', font=('Arial', 12, 'bold'))
        
        for i in range(2):
            slot = CardSlot(hole_frame, f"Hole {i+1}", self.card_size, self.on_update)
            slot.pack(side='left', padx=5)
            self.hole_card_slots.append(slot)
        
        # Create community card slots
        community_frame = tk.Frame(self.canvas, bg='darkgreen')
        self.canvas.create_window(300, 200, window=community_frame)
        
        self.canvas.create_text(300, 160, text="Community Cards", fill='white', font=('Arial', 12, 'bold'))
        
        for i in range(5):
            slot = CardSlot(community_frame, ["Flop 1", "Flop 2", "Flop 3", "Turn", "River"][i], 
                          self.card_size, self.on_update)
            slot.pack(side='left', padx=3)
            self.community_card_slots.append(slot)
    
    def get_hole_cards(self) -> List[Card]:
        """Get current hole cards"""
        cards = []
        for slot in self.hole_card_slots:
            card = slot.get_card()
            if card:
                cards.append(card)
        return cards
    
    def get_community_cards(self) -> List[Card]:
        """Get current community cards"""
        cards = []
        for slot in self.community_card_slots:
            card = slot.get_card()
            if card:
                cards.append(card)
        return cards
    
    def clear_all(self):
        """Clear all card slots"""
        for slot in self.hole_card_slots + self.community_card_slots:
            slot.clear()

class CardSelectionGrid(tk.Frame):
    """Grid showing all 52 cards for selection"""
    
    def __init__(self, parent, card_size: int = 60):
        super().__init__(parent)
        self.card_size = card_size
        self.card_widgets = {}
        self.used_cards = set()
        
        self.setup_grid()
        
    def setup_grid(self):
        """Create the card selection grid"""
        # Create a frame for each suit
        for suit_idx, suit in enumerate(SUITS):
            suit_frame = tk.LabelFrame(
                self,
                text=f"{suit} {['Spades', 'Hearts', 'Diamonds', 'Clubs'][suit_idx]}",
                font=('Arial', 12, 'bold'),
                fg=SUIT_COLORS[suit]
            )
            suit_frame.grid(row=suit_idx, column=0, sticky='ew', padx=5, pady=5)
            
            # Create cards for this suit
            for rank_idx, rank in enumerate(RANKS):
                card = Card(rank, suit)
                card_widget = DraggableCard(suit_frame, card, self.card_size)
                card_widget.pack(side='left', padx=2, pady=2)
                
                # Store reference
                self.card_widgets[str(card)] = card_widget
    
    def mark_used(self, card: Card):
        """Mark a card as used"""
        self.used_cards.add(str(card))
        if str(card) in self.card_widgets:
            self.card_widgets[str(card)].configure(bg='lightgray')
    
    def mark_unused(self, card: Card):
        """Mark a card as unused"""
        self.used_cards.discard(str(card))
        if str(card) in self.card_widgets:
            self.card_widgets[str(card)].configure(bg='white')

class PokerAssistant:
    """Main application class with visual card interface"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("PokerTool5 - Visual Poker Assistant")
        self.root.geometry("1200x800")
        
        # Initialize database
        self.db = PokerDatabase()
        
        # Current game state
        self.position = 1
        self.pot_size = 0.0
        self.call_amount = 0.0
        self.stack_size = 100.0
        self.big_blind = 1.0
        
        # Opponent tracking
        self.opponents = {}
        
        self.setup_gui()
        
    def setup_gui(self):
        """Setup the main GUI with visual elements"""
        # Create main container
        main_container = tk.Frame(self.root)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left side - Card selection
        left_frame = tk.Frame(main_container)
        left_frame.pack(side='left', fill='both', expand=True)
        
        # Card selection label
        tk.Label(left_frame, text="Card Selection", font=('Arial', 16, 'bold')).pack(pady=5)
        
        # Card grid
        self.card_grid = CardSelectionGrid(left_frame, card_size=50)
        self.card_grid.pack(padx=10, pady=10)
        
        # Right side - Table and analysis
        right_frame = tk.Frame(main_container)
        right_frame.pack(side='right', fill='both', expand=True)
        
        # Table visualization
        table_frame = ttk.LabelFrame(right_frame, text="Poker Table")
        table_frame.pack(fill='x', padx=5, pady=5)
        
        self.table_viz = TableVisualization(table_frame, on_update=self.on_cards_update)
        self.table_viz.pack()
        
        # Controls frame
        controls_frame = ttk.LabelFrame(right_frame, text="Game Controls")
        controls_frame.pack(fill='x', padx=5, pady=5)
        
        # Position and betting
        row1_frame = tk.Frame(controls_frame)
        row1_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(row1_frame, text="Position:").pack(side='left', padx=5)
        self.position_var = tk.IntVar(value=1)
        position_combo = ttk.Combobox(row1_frame, textvariable=self.position_var, width=15)
        position_combo['values'] = [f"{i} ({POSITION_NAMES[i]})" for i in range(1, 7)]
        position_combo.pack(side='left', padx=5)
        
        ttk.Label(row1_frame, text="Pot Size:").pack(side='left', padx=5)
        self.pot_size_var = tk.DoubleVar(value=10.0)
        ttk.Entry(row1_frame, textvariable=self.pot_size_var, width=10).pack(side='left', padx=5)
        
        row2_frame = tk.Frame(controls_frame)
        row2_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(row2_frame, text="Call Amount:").pack(side='left', padx=5)
        self.call_amount_var = tk.DoubleVar(value=2.0)
        ttk.Entry(row2_frame, textvariable=self.call_amount_var, width=10).pack(side='left', padx=5)
        
        ttk.Label(row2_frame, text="Stack Size:").pack(side='left', padx=5)
        self.stack_size_var = tk.DoubleVar(value=100.0)
        ttk.Entry(row2_frame, textvariable=self.stack_size_var, width=10).pack(side='left', padx=5)
        
        # Action buttons
        button_frame = tk.Frame(controls_frame)
        button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(button_frame, text="Analyze Hand", command=self.analyze_hand).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear Table", command=self.clear_table).pack(side='left', padx=5)
        
        # Results display
        results_frame = ttk.LabelFrame(right_frame, text="Analysis Results")
        results_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.results_text = tk.Text(results_frame, height=10, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        self.results_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def on_cards_update(self):
        """Called when cards are dropped on the table"""
        # Update card usage in the selection grid
        all_cards = self.table_viz.get_hole_cards() + self.table_viz.get_community_cards()
        
        # Mark all cards as unused first
        for card_str in self.card_grid.card_widgets:
            card_widget = self.card_grid.card_widgets[card_str]
            card_widget.configure(bg='white')
        
        # Mark used cards
        for card in all_cards:
            self.card_grid.mark_used(card)
    
    def clear_table(self):
        """Clear all cards from the table"""
        self.table_viz.clear_all()
        self.results_text.delete(1.0, tk.END)
        self.on_cards_update()
    
    def analyze_hand(self):
        """Perform comprehensive hand analysis"""
        try:
            # Get cards from visual interface
            hole_cards = self.table_viz.get_hole_cards()
            community_cards = self.table_viz.get_community_cards()
            
            if len(hole_cards) != 2:
                messagebox.showerror("Error", "Please place exactly 2 hole cards")
                return
            
            # Get betting information
            position = self.position_var.get()
            pot_size = self.pot_size_var.get()
            call_amount = self.call_amount_var.get()
            stack_size = self.stack_size_var.get()
            
            # Calculate metrics
            metrics = calculate_advanced_metrics(
                hole_cards, community_cards, pot_size, call_amount, stack_size, position
            )
            
            # Generate analysis
            analysis = self.generate_analysis(hole_cards, community_cards, metrics, position)
            
            # Display results
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(1.0, analysis)
            
            # Save to database
            session_data = {
                'position': position,
                'hand_cards': "".join(str(c) for c in hole_cards),
                'community_cards': "".join(str(c) for c in community_cards),
                'pot_size': pot_size,
                'stack_size': stack_size,
                'notes': 'Visual analysis'
            }
            self.db.save_session(session_data)
            
        except Exception as e:
            messagebox.showerror("Error", f"Analysis failed: {str(e)}")
            log.error(f"Analysis error: {e}")
    
    def generate_analysis(self, hole_cards: List[Card], community_cards: List[Card], 
                         metrics: TableMetrics, position: int) -> str:
        """Generate comprehensive hand analysis"""
        
        analysis_lines = []
        analysis_lines.append("=== POKER HAND ANALYSIS ===\n")
        
        # Hand information
        hand_str = "".join(str(c) for c in hole_cards)
        tier = get_hand_tier(hole_cards)
        analysis_lines.append(f"Hand: {hand_str}")
        analysis_lines.append(f"Hand Tier: {tier.title()}")
        analysis_lines.append(f"Position: {POSITION_NAMES.get(position, 'Unknown')} ({position})")
        
        if community_cards:
            community_str = "".join(str(c) for c in community_cards)
            analysis_lines.append(f"Community Cards: {community_str}")
        
        analysis_lines.append("")
        
        # Metrics
        analysis_lines.append("=== METRICS ===")
        analysis_lines.append(f"Hand Equity: {metrics.hand_equity:.1%}")
        analysis_lines.append(f"Pot Odds: {metrics.pot_odds:.2f}:1")
        analysis_lines.append(f"Stack-to-Pot Ratio: {metrics.spr:.1f}")
        analysis_lines.append(f"Fold Equity: {metrics.fold_equity:.1%}")
        analysis_lines.append(f"Expected Value: ${metrics.ev:.2f}")
        analysis_lines.append("")
        
        # Strategy recommendations
        analysis_lines.append("=== STRATEGY RECOMMENDATION ===")
        
        recommendation = self.get_strategy_recommendation(hole_cards, metrics, position, tier)
        analysis_lines.append(recommendation)
        
        analysis_lines.append("")
        
        # Position analysis
        analysis_lines.append("=== POSITIONAL ANALYSIS ===")
        pos_analysis = self.get_positional_analysis(position, tier)
        analysis_lines.append(pos_analysis)
        
        return "\n".join(analysis_lines)
    
    def get_strategy_recommendation(self, hole_cards: List[Card], metrics: TableMetrics, 
                                  position: int, tier: str) -> str:
        """Generate strategy recommendation"""
        
        recommendations = []
        
        # Pre-flop recommendations
        if metrics.hand_equity > 0.8:
            recommendations.append("STRONG HAND: Consider raising/re-raising for value")
        elif metrics.hand_equity > 0.6:
            recommendations.append("GOOD HAND: Bet/call for value, consider position")
        elif metrics.hand_equity > 0.4:
            recommendations.append("MARGINAL HAND: Play cautiously, consider folding if facing aggression")
        else:
            recommendations.append("WEAK HAND: Consider folding unless in favorable position")
        
        # Pot odds analysis
        if metrics.pot_odds > 0 and metrics.hand_equity > 0:
            required_equity = 1 / (metrics.pot_odds + 1)
            if metrics.hand_equity > required_equity:
                recommendations.append(f"CALL: Hand equity ({metrics.hand_equity:.1%}) exceeds required equity ({required_equity:.1%})")
            else:
                recommendations.append(f"FOLD: Hand equity ({metrics.hand_equity:.1%}) below required equity ({required_equity:.1%})")
        
        # Position-based adjustments
        if position in [4, 5]:  # Button, Small Blind
            recommendations.append("POSITION ADVANTAGE: Consider more aggressive play")
        elif position in [1, 2]:  # UTG, MP
            recommendations.append("EARLY POSITION: Play tighter range")
        
        return " | ".join(recommendations)
    
    def get_positional_analysis(self, position: int, tier: str) -> str:
        """Analyze position-specific considerations"""
        
        pos_name = POSITION_NAMES.get(position, "Unknown")
        
        if position == 4:  # Button
            return f"{pos_name}: Best position - can play wider range, steal blinds, control pot size"
        elif position == 3:  # Cut Off
            return f"{pos_name}: Strong position - good stealing opportunity if button folds"
        elif position in [5, 6]:  # Blinds
            return f"{pos_name}: Forced bet - play tight unless getting good odds"
        else:  # Early positions
            return f"{pos_name}: Early position - play premium hands, avoid marginal situations"

# Main execution
def main():
    try:
        root = tk.Tk()
        app = PokerAssistant(root)
        log.info("Visual Poker Assistant started successfully")
        root.mainloop()
    except Exception as e:
        log.error(f"Failed to start application: {e}")
        messagebox.showerror("Startup Error", f"Failed to start Visual Poker Assistant: {e}")

if __name__ == "__main__":
    main()