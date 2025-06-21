"""
All reusable / testable poker logic lives here.
Nothing in this file knows anything about tkinter or the database.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional
import math

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
    TWO   = "2"
    THREE = "3"
    FOUR  = "4"
    FIVE  = "5"
    SIX   = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE  = "9"
    TEN   = "T"
    JACK  = "J"
    QUEEN = "Q"
    KING  = "K"
    ACE   = "A"


RANKS = [r.value for r in Rank]


@dataclass(frozen=True)
class Card:
    rank: str
    suit: Suit

    def __str__(self) -> str:         # “Ah”, “Td” …
        return f"{self.rank}{self.suit.value}"


class Position(Enum):
    BTN   = 9
    SB    = 1
    BB    = 2
    UTG   = 3
    MP1   = 4
    MP2   = 5
    HJ    = 6
    CO    = 7
    UTG1  = 8


class StackType(Enum):
    SHORT      = "Short (10-30BB)"
    MEDIUM     = "Medium (30-60BB)"
    DEEP       = "Deep (60-100BB)"
    VERY_DEEP  = "Very Deep (100+BB)"

    @property
    def default_bb(self) -> int:
        mapping = {
            StackType.SHORT.value: 20,
            StackType.MEDIUM.value: 50,
            StackType.DEEP.value: 80,
            StackType.VERY_DEEP.value: 150
        }
        return mapping.get(self.value, 50)


class PlayerAction(Enum):
    FOLD   = "Fold"
    CALL   = "Call"
    RAISE  = "Raise"
    CHECK  = "Check"
    ALL_IN = "All-in"


@dataclass
class HandAnalysis:
    decision     : str
    reason       : str
    equity       : float
    required_eq  : float
    ev_call      : float
    ev_raise     : float
    board_texture: str = "Unknown"
    spr          : float = 0.0


# ──────────────────────────────────────────────────────
#  Pure functions – easy to unit-test and extend
# ──────────────────────────────────────────────────────
def hand_tier(hole_cards: List[Card]) -> str:
    if len(hole_cards) != 2:
        return "UNKNOWN"

    r1, r2 = hole_cards[0].rank, hole_cards[1].rank
    suited = hole_cards[0].suit == hole_cards[1].suit

    premium = {"A", "K", "Q"}
    if r1 in premium and r2 in premium:
        return "PREMIUM"

    strong = {"A", "K", "Q", "J", "T"}
    if r1 in strong and r2 in strong:
        return "STRONG"

    if r1 == r2:
        if r1 in {"A", "K", "Q", "J"}:
            return "PREMIUM"
        elif r1 in {"T", "9", "8", "7"}:
            return "STRONG"
        else:
            return "MEDIUM"

    if suited and abs(RANKS.index(r1) - RANKS.index(r2)) == 1:
        return "PLAYABLE"

    return "MARGINAL" if suited else "WEAK"


def analyse_hand(hole: List[Card], board: List[Card],
                 position: Position, stack_bb: int,
                 pot: float, to_call: float) -> HandAnalysis:
    tier = hand_tier(hole)
    pot_odds = to_call / (pot + to_call) if pot + to_call else 0

    equity_map = {
        "PREMIUM": 0.75, "STRONG": 0.65, "MEDIUM": 0.55,
        "PLAYABLE": 0.45, "MARGINAL": 0.35, "WEAK": 0.25,
        "UNKNOWN": 0.50
    }
    equity = equity_map.get(tier, 0.5)

    if position in (Position.BTN, Position.CO):
        equity += 0.05
    elif position in (Position.SB, Position.BB):
        equity -= 0.05

    if equity > pot_odds + 0.1:
        decision, reason = "RAISE", f"Strong hand ({tier}) with good equity"
    elif equity > pot_odds:
        decision, reason = "CALL", f"Positive EV with {tier} hand"
    else:
        decision, reason = "FOLD", f"Insufficient equity with {tier} hand"

    ev_call  = equity * (pot + to_call)       - to_call
    ev_raise = equity * (pot + to_call * 2.5) - to_call * 2.5

    return HandAnalysis(decision, reason, equity, pot_odds,
                        ev_call, ev_raise, "Mixed",
                        stack_bb / (pot / 2) if pot else 10)


def to_two_card_str(cards: List[Card]) -> str:
    return f"{cards[0]}{cards[1]}" if len(cards) == 2 else "??"


def get_position_advice(pos: Position) -> str:
    advice = {
        Position.BTN: "You have position advantage. Be aggressive with a wide range.",
        Position.CO : "Good position. Open strong + speculative hands.",
        Position.SB : "Poor position. Play tight, be careful post-flop.",
        Position.BB : "Out of position. Defend selectively.",
        Position.UTG: "Early position. Play only premium hands."
    }
    return advice.get(pos, "Play according to your position.")


def get_hand_advice(tier: str, _board_texture: str, _spr: float) -> str:
    if tier in {"PREMIUM", "STRONG"}:
        return "Strong hand – raise for value, protect on wet boards."
    if tier in {"MEDIUM", "PLAYABLE"}:
        return "Decent hand – pot-control, proceed with caution."
    return "Weak hand – bluff good spots, otherwise fold."