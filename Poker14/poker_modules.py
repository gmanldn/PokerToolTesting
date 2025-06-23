"""
All reusable / testable poker logic lives here.
Nothing in this file knows anything about tkinter or the database.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set, Dict
from collections import Counter
import random

# ──────────────────────────────────────────────────────
#  Core domain objects
# ──────────────────────────────────────────────────────
class Suit(Enum):
    SPADE   = "♠"
    HEART   = "♥"
    DIAMOND = "♦"
    CLUB    = "♣"

    @property
    def color(self) -> str:
        return "red" if self in (Suit.HEART, Suit.DIAMOND) else "black"

class Rank(Enum):
    TWO, THREE, FOUR, FIVE, SIX, SEVEN, EIGHT, NINE, TEN, JACK, QUEEN, KING, ACE = range(13)

    @property
    def val(self) -> str:
        return "23456789TJQKA"[self.value]

# Define constants that depend on Rank first.
RANKS_MAP = {r.val: r for r in Rank}
RANK_ORDER = [r.val for r in Rank]

# Now define Card, which depends on Suit, Rank, and RANK_ORDER.
@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: Suit

    @property
    def rank_val(self) -> int:
        return RANK_ORDER.index(self.rank)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit.value}"

# Finally, define FULL_DECK which depends on the Card class.
FULL_DECK = [Card(r.val, s) for s in Suit for r in Rank]

class Position(Enum):
    SB    = 1
    BB    = 2
    UTG   = 3
    UTG1  = 4
    MP1   = 5
    MP2   = 6
    HJ    = 7
    CO    = 8
    BTN   = 9

class StackType(Enum):
    SHORT      = "Short (10-30BB)"
    MEDIUM     = "Medium (30-60BB)"
    DEEP       = "Deep (60-100BB)"
    VERY_DEEP  = "Very Deep (100+BB)"

    @property
    def default_bb(self) -> int:
        return {
            StackType.SHORT: 20, StackType.MEDIUM: 50,
            StackType.DEEP: 80, StackType.VERY_DEEP: 150
        }[self]

class PlayerAction(Enum):
    FOLD, CALL, RAISE, CHECK, ALL_IN = range(5)

@dataclass
class GameState:
    is_active: bool = False
    pot: float = 0.0
    to_call: float = 0.0
    players_in_hand: List[int] = field(default_factory=list)
    player_actions: Dict[int, Tuple[PlayerAction, float]] = field(default_factory=dict)
    
@dataclass
class HandAnalysis:
    decision: str
    reason: str
    equity: float
    required_eq: float
    ev_call: float
    ev_raise: float
    board_texture: str
    spr: float

# ──────────────────────────────────────────────────────
#  Hand Evaluation Logic
# ──────────────────────────────────────────────────────
class HandRank(Enum):
    HIGH_CARD, PAIR, TWO_PAIR, THREE_OF_A_KIND, STRAIGHT, FLUSH, FULL_HOUSE, FOUR_OF_A_KIND, STRAIGHT_FLUSH = range(9)

def get_hand_rank(hole: List[Card], board: List[Card]) -> Tuple[HandRank, List[int]]:
    """Evaluates 7 cards and returns the best 5-card hand rank and kickers."""
    cards = sorted(hole + board, key=lambda c: c.rank_val, reverse=True)
    
    ranks = [c.rank_val for c in cards]
    suits = [c.suit for c in cards]
    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    # Check for Flush and Straight Flush
    is_flush = False
    flush_suit = None
    for s, count in suit_counts.items():
        if count >= 5:
            is_flush = True
            flush_suit = s
            break
    
    if is_flush:
        flush_cards = sorted([c for c in cards if c.suit == flush_suit], key=lambda c: c.rank_val, reverse=True)
        flush_ranks = [c.rank_val for c in flush_cards]
        is_straight, straight_high = check_straight(flush_ranks)
        if is_straight:
            return (HandRank.STRAIGHT_FLUSH, [straight_high])
    
    # Check for 4-of-a-kind, Full House, 3-of-a-kind
    pairs = []
    threes = []
    fours = []
    for rank, count in rank_counts.items():
        if count == 4: fours.append(rank)
        elif count == 3: threes.append(rank)
        elif count == 2: pairs.append(rank)
    
    fours.sort(reverse=True)
    threes.sort(reverse=True)
    pairs.sort(reverse=True)

    if fours:
        kicker = max([r for r in ranks if r != fours[0]]) if len([r for r in ranks if r != fours[0]]) > 0 else 0
        return (HandRank.FOUR_OF_A_KIND, [fours[0], kicker])
    
    if threes and pairs:
        return (HandRank.FULL_HOUSE, [threes[0], pairs[0]])

    if threes and len(threes) > 1: # Two sets mean one makes a full house
        return (HandRank.FULL_HOUSE, [threes[0], threes[1]])

    if is_flush:
        return (HandRank.FLUSH, flush_ranks[:5])

    # Check for Straight
    is_straight, straight_high = check_straight(ranks)
    if is_straight:
        return (HandRank.STRAIGHT, [straight_high])

    # Check for Trips, Two Pair, Pair
    if threes:
        kickers = [r for r in ranks if r != threes[0]][:2]
        return (HandRank.THREE_OF_A_KIND, [threes[0]] + kickers)

    if len(pairs) >= 2:
        kickers = [r for r in ranks if r not in pairs[:2]][:1]
        return (HandRank.TWO_PAIR, pairs[:2] + kickers)

    if pairs:
        kickers = [r for r in ranks if r != pairs[0]][:3]
        return (HandRank.PAIR, [pairs[0]] + kickers)

    return (HandRank.HIGH_CARD, ranks[:5])

def check_straight(ranks: List[int]) -> Tuple[bool, int]:
    """Helper to check for a straight in a list of ranks."""
    unique_ranks = sorted(list(set(ranks)), reverse=True)
    if 12 in unique_ranks: # Add low ace for A-5 straight (ACE has value 12)
        unique_ranks.append(-1)
        
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] == unique_ranks[i+4] + 4:
            return (True, unique_ranks[i])
    return (False, -1)

# ──────────────────────────────────────────────────────
#  Equity and Analysis Logic
# ──────────────────────────────────────────────────────
HAND_TIERS = {
    "PREMIUM": {"AA", "KK", "QQ", "JJ", "AKs"},
    "STRONG": {"TT", "99", "88", "AQs", "AJs", "ATs", "KQs", "AKo", "AQo"},
    "MEDIUM": {"77", "66", "55", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "A9s", "AJo", "KQo"},
    "PLAYABLE": {"A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s", "K9s", "Q9s", "J9s", "98s", "87s", "76s", "65s", "ATo", "KJo", "QJo"},
    "MARGINAL": {"44", "33", "22", "K8s", "K7s", "Q8s", "T8s", "97s", "86s", "75s", "54s"},
    "WEAK": {} # Everything else
}

def get_hand_tier(hole_cards: List[Card]) -> str:
    if len(hole_cards) != 2: return "UNKNOWN"
    c1, c2 = sorted(hole_cards, key=lambda c: c.rank_val, reverse=True)
    suited = "s" if c1.suit == c2.suit else "o"
    if c1.rank == c2.rank: suited = ""
    hand_str_generic = f"{c1.rank}{c2.rank}{suited}"
    hand_str_offsuit = f"{c2.rank}{c1.rank}o"
    
    for tier, hands in HAND_TIERS.items():
        if hand_str_generic in hands or (suited == "o" and hand_str_offsuit in hands):
            return tier
    return "WEAK"

def get_opponent_range(tier: str) -> Set[str]:
    if tier == "TIGHT":
        return HAND_TIERS["PREMIUM"] | HAND_TIERS["STRONG"]
    if tier == "MEDIUM":
        return HAND_TIERS["PREMIUM"] | HAND_TIERS["STRONG"] | HAND_TIERS["MEDIUM"]
    # "LOOSE" includes almost everything
    return set().union(*HAND_TIERS.values())

def calculate_equity_monte_carlo(
    hole: List[Card], 
    board: List[Card], 
    num_opponents: int,
    opponent_range_tier: str = "MEDIUM",
    num_simulations: int = 2000
) -> float:
    
    known_cards = set(hole + board)
    deck = [c for c in FULL_DECK if c not in known_cards]
    
    if len(deck) < 2 * num_opponents + (5 - len(board)):
        return 0.5  # Not enough cards
    
    opponent_range_cards = []
    opp_range_str = get_opponent_range(opponent_range_tier)
    
    for hand_str in opp_range_str:
        r1_val, r2_val = hand_str[0], hand_str[1]
        
        # Check if the cards for this hand combo are even in the deck
        possible_in_deck = sum(1 for c in deck if c.rank == r1_val) >= (2 if r1_val == r2_val else 1) and \
                           sum(1 for c in deck if c.rank == r2_val) >= 1
        if not possible_in_deck:
            continue

        if len(hand_str) == 3 and hand_str[2] == 's': # Suited
            for s in Suit:
                c1, c2 = Card(r1_val, s), Card(r2_val, s)
                if c1 in deck and c2 in deck:
                    opponent_range_cards.append([c1, c2])
        else: # Pair or off-suit
            all_r1s = [c for c in deck if c.rank == r1_val]
            all_r2s = [c for c in deck if c.rank == r2_val]
            if r1_val == r2_val: # Pair
                for i in range(len(all_r1s)):
                    for j in range(i + 1, len(all_r1s)):
                        opponent_range_cards.append([all_r1s[i], all_r1s[j]])
            else: # Offsuit
                for c1 in all_r1s:
                    for c2 in all_r2s:
                        if c1.suit != c2.suit:
                           opponent_range_cards.append([c1,c2])


    if not opponent_range_cards: return 0.5 # fallback

    wins = 0
    ties = 0
    valid_sims = 0

    for _ in range(num_simulations):
        random.shuffle(deck)
        sim_deck = list(deck)
        
        # Deal hands to opponents
        opp_hands = []
        possible_opp_hands = [h for h in opponent_range_cards if h[0] in sim_deck and h[1] in sim_deck]
        random.shuffle(possible_opp_hands)
        
        dealt_cards = set()
        skip_sim = False
        for _ in range(num_opponents):
            hand_found = False
            # Try to find a hand from the range that doesn't conflict with cards already dealt to other opponents
            for hand_candidate in possible_opp_hands:
                if hand_candidate[0] not in dealt_cards and hand_candidate[1] not in dealt_cards:
                    opp_hands.append(hand_candidate)
                    dealt_cards.update(hand_candidate)
                    # Remove cards from sim_deck
                    sim_deck.remove(hand_candidate[0])
                    sim_deck.remove(hand_candidate[1])
                    hand_found = True
                    break
            if not hand_found: # Could not find a hand from the range
                if len(sim_deck) >= 2:
                    hand = [sim_deck.pop(), sim_deck.pop()]
                    opp_hands.append(hand)
                else:
                    skip_sim = True
                    break
        
        if skip_sim:
            continue

        # Draw board
        needed = 5 - len(board)
        if len(sim_deck) < needed:
            continue
        sim_board = board + sim_deck[:needed]

        my_rank = get_hand_rank(hole, sim_board)
        best_opp_rank = (HandRank.HIGH_CARD, [-1])

        for opp_hand in opp_hands:
            opp_rank = get_hand_rank(opp_hand, sim_board)
            if opp_rank > best_opp_rank:
                best_opp_rank = opp_rank
        
        if my_rank > best_opp_rank:
            wins += 1
        elif my_rank == best_opp_rank:
            ties += 1
        
        valid_sims += 1

    if valid_sims == 0: return 0.0
    return (wins + ties / 2) / valid_sims

def get_board_texture(board: List[Card]) -> str:
    if not board: return "Pre-flop"
    ranks = [c.rank_val for c in board]
    suits = [c.suit for c in board]
    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    textures = []
    if max(rank_counts.values()) == 3: textures.append("Trips")
    elif max(rank_counts.values()) == 2: textures.append("Paired")
    
    if max(suit_counts.values()) >= 3: textures.append("Monotone" if len(board) == 3 and max(suit_counts.values()) == 3 else "Flush-draw")
    
    unique_ranks = sorted(list(set(ranks)))
    is_connected = False
    if len(unique_ranks) >= 3:
      for i in range(len(unique_ranks) - 2):
          if unique_ranks[i+2] - unique_ranks[i] <= 4:
              is_connected = True
              break
    if is_connected: textures.append("Connected")
        
    if not textures: return "Dry/Raggedy"
    return ", ".join(textures)


def analyse_hand(hole: List[Card], board: List[Card], position: Position, 
                 stack_bb: int, pot: float, to_call: float, num_players: int) -> HandAnalysis:
    
    tier = get_hand_tier(hole)
    pot_odds = to_call / (pot + to_call) if pot + to_call > 0 else 0
    # Effective stack is what's in your stack minus what you'd need to call
    effective_stack = stack_bb * (pot / 100.0) if pot > 0 else stack_bb  # Approximate BB value
    spr = effective_stack / pot if pot > 0 else 100

    equity = calculate_equity_monte_carlo(hole, board, max(0, num_players - 1))
    board_texture = get_board_texture(board)

    # Adjust decision making based on equity edge and SPR
    equity_edge = equity - pot_odds

    if equity_edge > 0.10 or (equity_edge > 0.05 and spr < 4):
        decision, reason = "RAISE", f"Strong equity edge ({equity_edge:+.1%}) and favorable SPR ({spr:.1f})."
    elif equity_edge >= 0:
        decision, reason = "CALL", f"Positive EV call based on pot odds vs equity ({equity:.1%})."
    else:
        decision, reason = "FOLD", f"Insufficient equity ({equity:.1%}) to meet pot odds ({pot_odds:.1%})."
    
    # Pre-flop adjustments based on position
    if not board:
        if position in (Position.UTG, Position.UTG1) and tier not in ("PREMIUM", "STRONG"):
            decision, reason = "FOLD", "Too weak to open from early position."
        if position in (Position.BTN, Position.CO) and decision == "CALL":
            decision = "RAISE" # Be more aggressive in position
            reason = "Good position to take control of the pot with a playable hand."

    ev_call = (equity * (pot + to_call)) - to_call
    ev_raise = (equity * (pot + to_call * 2.5)) - (to_call * 2.5) if to_call > 0 else (equity * (pot + 3)) - 3

    return HandAnalysis(decision, reason, equity, pot_odds, ev_call, ev_raise, board_texture, spr)

def to_two_card_str(cards: List[Card]) -> str:
    return f"{cards[0].rank}{cards[0].suit.value}{cards[1].rank}{cards[1].suit.value}" if len(cards) == 2 else "??"


def get_position_advice(pos: Position) -> str:
    advice = {
        Position.BTN: "You have position advantage. Be aggressive with a wide range.",
        Position.CO : "Good position. Open strong + speculative hands.",
        Position.SB : "Poor position. Play tight, be careful post-flop.",
        Position.BB : "Out of position. Defend selectively.",
        Position.UTG: "Early position. Play only premium hands."
    }
    return advice.get(pos, "Play according to your position.")

def get_hand_advice(tier: str, board_texture: str, spr: float) -> str:
    base_advice = {
        "PREMIUM": "Value bet strongly. Be cautious on very scary boards.",
        "STRONG": "Raise for value. Pot control if heavy resistance on wet boards.",
        "MEDIUM": "Decent hand. Pot-control, proceed with caution on wet boards.",
        "PLAYABLE": "Good for semi-bluffs or calling on the flop if you hit a draw.",
    }.get(tier, "Weak hand. Look for good bluffing spots or fold to aggression.")

    if spr < 4:
        base_advice += " With a low SPR, you should be willing to get all-in."
    elif "Flush-draw" in board_texture or "Connected" in board_texture:
        base_advice += " This is a wet board; be wary of multi-way pots."
    
    return base_advice