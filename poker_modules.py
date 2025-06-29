#!/usr/bin/env python3
"""
Fixed Poker Modules - Core functionality for poker hand analysis
Addresses HandRank comparison issues by using IntEnum
"""

from enum import IntEnum, Enum
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Set
import random
from collections import Counter
import itertools

# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENUMS AND CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

class Suit(Enum):
    """Card suits with symbols."""
    SPADE = "♠"
    HEART = "♥"
    DIAMOND = "♦"
    CLUB = "♣"
    
    @property
    def color(self):
        """Return the color of the suit."""
        return "red" if self in (Suit.HEART, Suit.DIAMOND) else "black"


class Rank(Enum):
    """Card ranks with their display values."""
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
    
    @property
    def val(self):
        """Return the string value of the rank."""
        return self.value


# Rank mappings and ordering
RANKS_MAP = {rank.value: rank for rank in Rank}
RANK_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']


class HandRank(IntEnum):
    """
    Poker hand rankings from lowest to highest.
    Using IntEnum for built-in comparison support.
    """
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


class Position(Enum):
    """Table positions in poker."""
    BTN = "Button"
    SB = "Small Blind"
    BB = "Big Blind"
    UTG = "Under the Gun"
    MP1 = "Middle Position 1"
    MP2 = "Middle Position 2"
    HJ = "Hijack"
    CO = "Cutoff"


class StackType(Enum):
    """Stack size categories."""
    SHORT = "short"      # < 30BB
    MEDIUM = "medium"    # 30-100BB
    DEEP = "deep"        # > 100BB


class PlayerAction(Enum):
    """Possible player actions."""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"


# ═══════════════════════════════════════════════════════════════════════════════
# CARD CLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Card:
    """Represents a playing card."""
    rank: str
    suit: Suit
    
    def __post_init__(self):
        """Validate card rank."""
        if self.rank not in RANK_ORDER:
            raise ValueError(f"Invalid rank: {self.rank}")
    
    def __str__(self):
        """String representation of card."""
        return f"{self.rank}{self.suit.value}"
    
    def __repr__(self):
        """Detailed representation."""
        return f"Card('{self.rank}', {self.suit})"
    
    @property
    def rank_val(self) -> int:
        """Numeric value of rank for comparisons."""
        return RANK_ORDER.index(self.rank)
    
    def __eq__(self, other):
        """Equality comparison."""
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit
    
    def __hash__(self):
        """Make Card hashable for use in sets."""
        return hash((self.rank, self.suit))


# Generate full deck
FULL_DECK = [Card(rank.val, suit) for suit in Suit for rank in Rank]


# ═══════════════════════════════════════════════════════════════════════════════
# HAND TIERS AND RANGES
# ═══════════════════════════════════════════════════════════════════════════════

HAND_TIERS = {
    "PREMIUM": [
        "AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"
    ],
    "STRONG": [
        "TT", "99", "88", "AQo", "AJs", "AJo", "ATs", "KQs"
    ],
    "MEDIUM": [
        "77", "66", "55", "ATo", "A9s", "A8s", "KQo", "KJs", "KTs", "QJs", "QTs", "JTs"
    ],
    "PLAYABLE": [
        "44", "33", "22", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s", "KJo", "KTo",
        "QJo", "QTo", "JTo", "T9s", "98s", "87s", "76s", "65s", "54s"
    ],
    "MARGINAL": [
        "A9o", "A8o", "A7o", "A6o", "A5o", "K9s", "K8s", "K7s", "Q9s", "Q8s",
        "J9s", "J8s", "T8s", "T7s", "97s", "96s", "86s", "85s", "75s", "74s",
        "64s", "63s", "53s", "52s", "43s", "42s", "32s"
    ],
    "WEAK": []  # Everything else
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HandAnalysis:
    """Complete analysis of a poker hand."""
    decision: str
    equity: float
    pot_odds: float
    required_eq: float
    ev_call: float
    ev_fold: float
    reason: str
    hand_tier: str
    position_notes: str
    board_texture: str
    pot_committed: bool


@dataclass
class GameState:
    """Current state of the poker game."""
    position: Position
    stack_bb: float
    pot: float
    to_call: float
    num_players: int
    hole_cards: List[Card]
    board: List[Card]
    
    @property
    def pot_invested(self) -> float:
        """Calculate how much we've already invested."""
        # Simplified - would need betting history for accuracy
        return 0.0
    
    @property
    def effective_stack(self) -> float:
        """Stack size after current call."""
        return self.stack_bb - self.to_call


# ═══════════════════════════════════════════════════════════════════════════════
# HAND EVALUATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def check_straight(ranks: List[int]) -> Optional[int]:
    """
    Check if ranks form a straight, return high card if true.
    Handles ace-low straights (A-2-3-4-5).
    """
    if not ranks:
        return None
    
    unique_ranks = sorted(set(ranks), reverse=True)
    
    # Check for regular straights
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] - unique_ranks[i+4] == 4:
            return unique_ranks[i]
    
    # Check for ace-low straight (wheel)
    if set(unique_ranks) >= {12, 0, 1, 2, 3}:  # A, 2, 3, 4, 5
        return 3  # 5-high straight
    
    return None


def get_hand_rank(hole: List[Card], board: List[Card]) -> Tuple[HandRank, List[int]]:
    """
    Determine the best 5-card poker hand rank from hole cards and board.
    Returns (HandRank, kickers) where kickers help break ties.
    """
    all_cards = hole + board
    
    if len(all_cards) < 5:
        # Not enough cards for a valid hand
        return HandRank.HIGH_CARD, [card.rank_val for card in sorted(hole, key=lambda c: c.rank_val, reverse=True)]
    
    # Find best 5-card combination
    best_rank = HandRank.HIGH_CARD
    best_kickers = []
    
    for combo in itertools.combinations(all_cards, 5):
        combo_list = list(combo)
        
        # Count ranks and suits
        rank_counts = Counter(card.rank_val for card in combo_list)
        suit_counts = Counter(card.suit for card in combo_list)
        
        # Get sorted unique ranks
        sorted_ranks = sorted(rank_counts.keys(), reverse=True)
        
        # Check for flush
        is_flush = max(suit_counts.values()) >= 5
        
        # Check for straight
        straight_high = check_straight([card.rank_val for card in combo_list])
        is_straight = straight_high is not None
        
        # Determine hand rank
        current_rank = HandRank.HIGH_CARD
        kickers = []
        
        if is_straight and is_flush:
            current_rank = HandRank.STRAIGHT_FLUSH
            kickers = [straight_high]
        elif 4 in rank_counts.values():
            current_rank = HandRank.FOUR_OF_A_KIND
            quad_rank = [r for r, c in rank_counts.items() if c == 4][0]
            kicker_rank = [r for r, c in rank_counts.items() if c == 1][0]
            kickers = [quad_rank, kicker_rank]
        elif 3 in rank_counts.values() and 2 in rank_counts.values():
            current_rank = HandRank.FULL_HOUSE
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            kickers = [trip_rank, pair_rank]
        elif is_flush:
            current_rank = HandRank.FLUSH
            flush_suit = [s for s, c in suit_counts.items() if c >= 5][0]
            flush_cards = sorted([c.rank_val for c in combo_list if c.suit == flush_suit], reverse=True)
            kickers = flush_cards[:5]
        elif is_straight:
            current_rank = HandRank.STRAIGHT
            kickers = [straight_high]
        elif 3 in rank_counts.values():
            current_rank = HandRank.THREE_OF_A_KIND
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            kicker_ranks = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
            kickers = [trip_rank] + kicker_ranks[:2]
        elif list(rank_counts.values()).count(2) >= 2:
            current_rank = HandRank.TWO_PAIR
            pair_ranks = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
            kicker_rank = [r for r, c in rank_counts.items() if c == 1][0] if 1 in rank_counts.values() else 0
            kickers = pair_ranks[:2] + [kicker_rank]
        elif 2 in rank_counts.values():
            current_rank = HandRank.PAIR
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            kicker_ranks = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
            kickers = [pair_rank] + kicker_ranks[:3]
        else:
            current_rank = HandRank.HIGH_CARD
            kickers = sorted_ranks[:5]
        
        # Update best hand if this combination is better
        if current_rank > best_rank or (current_rank == best_rank and kickers > best_kickers):
            best_rank = current_rank
            best_kickers = kickers
    
    return best_rank, best_kickers


# ═══════════════════════════════════════════════════════════════════════════════
# HAND ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def to_two_card_str(cards: List[Card]) -> str:
    """Convert two cards to standard notation."""
    if len(cards) != 2:
        return ""
    
    c1, c2 = cards
    if c1.rank_val < c2.rank_val:
        c1, c2 = c2, c1
    
    suited = "s" if c1.suit == c2.suit else "o"
    if c1.rank == c2.rank:
        return f"{c1.rank}{c2.rank}"
    
    return f"{c1.rank}{c2.rank}{suited}"


def get_hand_tier(hole_cards: List[Card]) -> str:
    """Classify hole cards into tiers."""
    hand_str = to_two_card_str(hole_cards)
    
    # Handle specific notations
    if len(hand_str) >= 2:
        # For pairs, check without suit designation
        if hand_str[0] == hand_str[1]:
            pair_str = hand_str[:2]
            for tier, hands in HAND_TIERS.items():
                if pair_str in hands:
                    return tier
        else:
            # Check both suited and offsuit versions
            for tier, hands in HAND_TIERS.items():
                if hand_str in hands:
                    return tier
    
    return "WEAK"


def get_opponent_range(player_type: str) -> List[str]:
    """Get typical hand range for opponent type."""
    if player_type == "TIGHT":
        return HAND_TIERS["PREMIUM"] + HAND_TIERS["STRONG"][:4]
    elif player_type == "MEDIUM":
        return HAND_TIERS["PREMIUM"] + HAND_TIERS["STRONG"] + HAND_TIERS["MEDIUM"]
    else:  # LOOSE
        return (HAND_TIERS["PREMIUM"] + HAND_TIERS["STRONG"] + 
                HAND_TIERS["MEDIUM"] + HAND_TIERS["PLAYABLE"])


def calculate_equity_monte_carlo(hole: List[Card], board: List[Card], 
                               num_opponents: int, opp_range_type: str,
                               num_simulations: int = 1000) -> float:
    """
    Calculate equity using Monte Carlo simulation.
    """
    if num_simulations <= 0:
        return 0.5
    
    wins = 0
    ties = 0
    
    # Get opponent range
    opp_range = get_opponent_range(opp_range_type)
    
    # Create deck excluding known cards
    known_cards = set(hole + board)
    remaining_deck = [card for card in FULL_DECK if card not in known_cards]
    
    for _ in range(num_simulations):
        # Shuffle remaining deck
        sim_deck = remaining_deck.copy()
        random.shuffle(sim_deck)
        
        # Complete the board
        board_cards_needed = 5 - len(board)
        sim_board = board + sim_deck[:board_cards_needed]
        sim_deck = sim_deck[board_cards_needed:]
        
        # Get our hand rank
        our_rank, our_kickers = get_hand_rank(hole, sim_board)
        
        # Simulate opponent hands
        best_opp_rank = HandRank.HIGH_CARD
        best_opp_kickers = []
        
        for opp_idx in range(num_opponents):
            # Deal opponent cards from range
            if len(sim_deck) >= 2:
                opp_cards = sim_deck[:2]
                sim_deck = sim_deck[2:]
                
                opp_rank, opp_kickers = get_hand_rank(opp_cards, sim_board)
                
                if (opp_rank > best_opp_rank or 
                    (opp_rank == best_opp_rank and opp_kickers > best_opp_kickers)):
                    best_opp_rank = opp_rank
                    best_opp_kickers = opp_kickers
        
        # Compare hands
        if our_rank > best_opp_rank:
            wins += 1
        elif our_rank == best_opp_rank:
            if our_kickers > best_opp_kickers:
                wins += 1
            elif our_kickers == best_opp_kickers:
                ties += 1
    
    return (wins + ties * 0.5) / num_simulations


def get_board_texture(board: List[Card]) -> str:
    """Analyze board texture for strategic considerations."""
    if not board:
        return "Pre-flop"
    
    textures = []
    
    # Check for pairs on board
    rank_counts = Counter(card.rank for card in board)
    if any(count >= 2 for count in rank_counts.values()):
        textures.append("Paired")
    
    # Check for flush possibilities
    suit_counts = Counter(card.suit for card in board)
    max_suit = max(suit_counts.values())
    if max_suit >= 3:
        textures.append("Monotone" if max_suit == len(board) else "Flush possible")
    
    # Check for straight possibilities
    ranks = sorted(set(card.rank_val for card in board))
    for i in range(len(ranks) - 2):
        if ranks[i+2] - ranks[i] <= 4:
            textures.append("Straight possible")
            break
    
    # Overall classification
    if not textures:
        if len(set(card.rank_val for card in board)) == len(board):
            textures.append("Rainbow")
        else:
            textures.append("Dry")
    
    return ", ".join(textures)


def get_position_advice(position: Position) -> str:
    """Get position-specific advice."""
    if position in [Position.BTN, Position.CO]:
        return "Late position - play more hands aggressively"
    elif position in [Position.UTG, Position.MP1]:
        return "Early position - play tight, strong hands only"
    else:
        return "Middle position - moderate range"


def get_hand_advice(tier: str) -> str:
    """Get advice based on hand tier."""
    advice_map = {
        "PREMIUM": "Premium hand - raise or re-raise aggressively",
        "STRONG": "Strong hand - raise in most positions",
        "MEDIUM": "Medium strength - play cautiously in early position",
        "PLAYABLE": "Playable hand - consider position and action",
        "MARGINAL": "Marginal hand - fold in early position",
        "WEAK": "Weak hand - fold unless in blinds"
    }
    return advice_map.get(tier, "Evaluate based on position and action")


def analyse_hand(hole: List[Card], board: List[Card], position: Position,
                stack_bb: float, pot: float, to_call: float, num_players: int) -> HandAnalysis:
    """
    Comprehensive hand analysis with decision recommendation.
    """
    # Get hand tier
    hand_tier = get_hand_tier(hole)
    
    # Calculate pot odds
    pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 0
    
    # Estimate equity
    opponent_type = "MEDIUM"  # Default assumption
    equity = calculate_equity_monte_carlo(hole, board, num_players - 1, opponent_type, 1000)
    
    # Calculate EVs
    ev_call = equity * (pot + to_call) - to_call
    ev_fold = 0
    
    # Determine if pot committed
    pot_committed = (stack_bb > 0 and to_call / stack_bb > 0.3 and pot / stack_bb > 1.0)
    
    # Make decision
    if pot_committed:
        decision = "CALL"
        reason = "Pot committed"
    elif equity > pot_odds * 1.2:  # Want some edge
        decision = "RAISE" if equity > 0.7 else "CALL"
        reason = f"Positive EV: {ev_call:.2f}BB"
    elif equity > pot_odds:
        decision = "CALL"
        reason = "Marginal call"
    else:
        decision = "FOLD"
        reason = f"Negative EV: {ev_call:.2f}BB"
    
    # Get contextual advice
    position_notes = get_position_advice(position)
    board_texture = get_board_texture(board)
    
    return HandAnalysis(
        decision=decision,
        equity=equity,
        pot_odds=pot_odds,
        required_eq=pot_odds,
        ev_call=ev_call,
        ev_fold=ev_fold,
        reason=reason,
        hand_tier=hand_tier,
        position_notes=position_notes,
        board_texture=board_texture,
        pot_committed=pot_committed
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING AND VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Quick validation tests
    print("🎯 Poker Modules - Quick Validation")
    print("=" * 50)
    
    # Test 1: HandRank comparison
    print("\n1. Testing HandRank comparisons:")
    print(f"   PAIR > HIGH_CARD: {HandRank.PAIR > HandRank.HIGH_CARD}")
    print(f"   FLUSH > STRAIGHT: {HandRank.FLUSH > HandRank.STRAIGHT}")
    print(f"   STRAIGHT_FLUSH > FOUR_OF_A_KIND: {HandRank.STRAIGHT_FLUSH > HandRank.FOUR_OF_A_KIND}")
    
    # Test 2: Card creation
    print("\n2. Testing Card creation:")
    ace_spades = Card('A', Suit.SPADE)
    king_hearts = Card('K', Suit.HEART)
    print(f"   Ace of Spades: {ace_spades}")
    print(f"   King of Hearts: {king_hearts}")
    
    # Test 3: Hand evaluation
    print("\n3. Testing hand evaluation:")
    hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
    board = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('K', Suit.SPADE)]
    rank, kickers = get_hand_rank(hole, board)
    print(f"   Hole: {hole}")
    print(f"   Board: {board}")
    print(f"   Best hand: {rank.name} with kickers {kickers}")
    
    # Test 4: Equity calculation
    print("\n4. Testing equity calculation:")
    hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
    board = []
    equity = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 500)
    print(f"   AK vs 1 opponent: {equity:.2%} equity")
    
    print("\n✅ All basic tests passed!")
