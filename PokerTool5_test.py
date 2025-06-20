from __future__ import annotations
"""PokerTool5 – Enhanced with table visualization and advanced metrics
--------------------------------------------------------------------------------------
Features:
- Graphical table representation
- Advanced metrics (pot odds, SPR, equity calculations)
- Improved strategy recommendations
- Opponent profiling
"""

import logging
import random
import math
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Dict, Callable, Any
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

# Stack size categories
STACK_CATEGORIES = {
    'short': (0, 20),      # 0-20 BB
    'medium': (20, 80),    # 20-80 BB
    'deep': (80, 150),     # 80-150 BB
    'very_deep': (150, 999) # 150+ BB
}

# Bullying effectiveness based on stack dynamics
STACK_BULLY_MATRIX = {
    ('very_deep', 'short'): 0.6,
    ('very_deep', 'medium'): 1.0,
    ('very_deep', 'deep'): 0.7,
    ('very_deep', 'very_deep'): 0.5,
    ('deep', 'short'): 0.6,
    ('deep', 'medium'): 0.9,
    ('deep', 'deep'): 0.6,
    ('medium', 'short'): 0.5,
    ('medium', 'medium'): 0.4,
    ('short', 'short'): 0.2,
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

class OpponentProfile:
    """Track opponent tendencies and statistics"""
    
    def __init__(self, name: str):
        self.name = name
        self.hands_played = 0
        self.vpip = 0.0  # Voluntarily Put In Pot
        self.pfr = 0.0   # Pre-Flop Raise
        self.aggression_factor = 0.0
        self.fold_to_cbet = 0.0
        self.opponent_type = OpponentType.UNKNOWN
        
    def update_stats(self, action: str, position: int):
        """Update opponent statistics based on observed action"""
        self.hands_played += 1
        # Simplified stat tracking
        if action in ['call', 'raise', 'bet']:
            self.vpip = min(100.0, self.vpip + 1.0)
        
        if action in ['raise', 'bet']:
            self.pfr = min(100.0, self.pfr + 0.5)
            self.aggression_factor = min(5.0, self.aggression_factor + 0.1)
    
    def classify_opponent(self) -> OpponentType:
        """Classify opponent based on tracked statistics"""
        if self.hands_played < 10:
            return OpponentType.UNKNOWN
        
        if self.vpip < 20 and self.pfr < 15:
            return OpponentType.TIGHT_PASSIVE
        elif self.vpip < 25 and self.pfr > 15:
            return OpponentType.TIGHT_AGGRESSIVE
        elif self.vpip > 35 and self.pfr < 15:
            return OpponentType.LOOSE_PASSIVE
        elif self.vpip > 30 and self.pfr > 20:
            return OpponentType.LOOSE_AGGRESSIVE
        else:
            return OpponentType.UNKNOWN

class TableVisualization(tk.Frame):
    """GUI component for table visualization"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, width=400, height=300, bg='darkgreen')
        self.canvas.pack(padx=10, pady=10)
        self.draw_table()
        
    def draw_table(self):
        """Draw the poker table"""
        # Clear canvas
        self.canvas.delete("all")
        
        # Draw table
        self.canvas.create_oval(50, 50, 350, 250, fill='darkgreen', outline='brown', width=5)
        
        # Draw positions
        positions = [
            (200, 60, "BTN"),   # Button
            (120, 80, "SB"),    # Small Blind
            (80, 150, "BB"),    # Big Blind
            (120, 220, "UTG"),  # Under the Gun
            (200, 240, "MP"),   # Middle Position
            (280, 220, "CO"),   # Cut Off
        ]
        
        for x, y, pos in positions:
            self.canvas.create_oval(x-20, y-20, x+20, y+20, fill='lightblue', outline='black')
            self.canvas.create_text(x, y-30, text=pos, font=('Arial', 8, 'bold'))

class PokerAssistant:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("PokerTool5 - Advanced Poker Assistant")
        self.root.geometry("800x600")
        
        # Initialize database
        self.db = PokerDatabase()
        
        # Current game state
        self.hole_cards = []
        self.community_cards = []
        self.position = 1
        self.pot_size = 0.0
        self.call_amount = 0.0
        self.stack_size = 100.0
        self.big_blind = 1.0
        
        # Opponent tracking
        self.opponents = {}
        
        self.setup_gui()
        
    def setup_gui(self):
        """Setup the main GUI"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Main game tab
        main_frame = ttk.Frame(notebook)
        notebook.add(main_frame, text="Game Analysis")
        
        # Table visualization
        table_frame = ttk.LabelFrame(main_frame, text="Table View")
        table_frame.pack(fill='x', padx=5, pady=5)
        
        self.table_viz = TableVisualization(table_frame)
        self.table_viz.pack()
        
        # Hand input
        hand_frame = ttk.LabelFrame(main_frame, text="Current Hand")
        hand_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(hand_frame, text="Hole Cards:").grid(row=0, column=0, padx=5, pady=5)
        self.hole_cards_var = tk.StringVar(value="AhKs")
        ttk.Entry(hand_frame, textvariable=self.hole_cards_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(hand_frame, text="Community Cards:").grid(row=0, column=2, padx=5, pady=5)
        self.community_cards_var = tk.StringVar()
        ttk.Entry(hand_frame, textvariable=self.community_cards_var, width=15).grid(row=0, column=3, padx=5, pady=5)
        
        # Position and betting
        betting_frame = ttk.LabelFrame(main_frame, text="Betting Information")
        betting_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(betting_frame, text="Position:").grid(row=0, column=0, padx=5, pady=5)
        self.position_var = tk.IntVar(value=1)
        position_combo = ttk.Combobox(betting_frame, textvariable=self.position_var, width=10)
        position_combo['values'] = [f"{i} ({POSITION_NAMES[i]})" for i in range(1, 7)]
        position_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(betting_frame, text="Pot Size:").grid(row=0, column=2, padx=5, pady=5)
        self.pot_size_var = tk.DoubleVar(value=10.0)
        ttk.Entry(betting_frame, textvariable=self.pot_size_var, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(betting_frame, text="Call Amount:").grid(row=1, column=0, padx=5, pady=5)
        self.call_amount_var = tk.DoubleVar(value=2.0)
        ttk.Entry(betting_frame, textvariable=self.call_amount_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(betting_frame, text="Stack Size:").grid(row=1, column=2, padx=5, pady=5)
        self.stack_size_var = tk.DoubleVar(value=100.0)
        ttk.Entry(betting_frame, textvariable=self.stack_size_var, width=10).grid(row=1, column=3, padx=5, pady=5)
        
        # Analysis button
        ttk.Button(betting_frame, text="Analyze Hand", command=self.analyze_hand).grid(row=2, column=0, columnspan=4, pady=10)
        
        # Results display
        results_frame = ttk.LabelFrame(main_frame, text="Analysis Results")
        results_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.results_text = tk.Text(results_frame, height=15, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        self.results_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Statistics tab
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Statistics")
        
        ttk.Label(stats_frame, text="Game Statistics", font=('Arial', 16, 'bold')).pack(pady=10)
        ttk.Label(stats_frame, text="Feature coming soon...").pack()
    
    def parse_cards(self, card_string: str) -> List[Card]:
        """Parse card string into Card objects"""
        cards = []
        card_string = card_string.replace(" ", "").replace(",", "")
        
        i = 0
        while i < len(card_string) - 1:
            rank = card_string[i]
            suit_char = card_string[i + 1]
            
            # Convert suit character to symbol
            suit_map = {'h': '♥', 'd': '♦', 'c': '♣', 's': '♠'}
            suit = suit_map.get(suit_char.lower(), suit_char)
            
            if rank in RANKS and suit in SUITS:
                cards.append(Card(rank, suit))
            
            i += 2
        
        return cards
    
    def analyze_hand(self):
        """Perform comprehensive hand analysis"""
        try:
            # Parse input
            hole_cards = self.parse_cards(self.hole_cards_var.get())
            community_cards = self.parse_cards(self.community_cards_var.get())
            
            if len(hole_cards) != 2:
                messagebox.showerror("Error", "Please enter exactly 2 hole cards")
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
                'notes': 'Auto-analysis'
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
        log.info("Enhanced Poker Assistant with Table Visualization started successfully")
        root.mainloop()
    except Exception as e:
        log.error(f"Failed to start application: {e}")
        messagebox.showerror("Startup Error", f"Failed to start Enhanced Poker Assistant: {e}")

if __name__ == "__main__":
    main()