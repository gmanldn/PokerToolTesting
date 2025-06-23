    # poker_unit.py
"""
Exhaustive unit-tests for the Poker-Assistant logic layer (poker_modules.py).
Nothing from tkinter or the database is touched – the tests are completely
pure and deterministic (a fixed RNG seed is used whenever randomness is
involved).

Run with:
    python -m unittest poker_unit.py
"""

from __future__ import annotations
import unittest, random
from typing import List

# ──────────────────────────────────────────────────────
#  Module under test
# ──────────────────────────────────────────────────────
from poker_modules import (
    Suit, Card, HandRank, Position, StackType,
    get_hand_rank, check_straight, get_hand_tier,
    get_board_texture, calculate_equity_monte_carlo,
    analyse_hand, to_two_card_str
)

# ------------------------------------------------------
#  Small helpers
# ------------------------------------------------------
RANK_CHARS = "23456789TJQKA"
SUIT_MAP = {"s": Suit.SPADE, "h": Suit.HEART, "d": Suit.DIAMOND, "c": Suit.CLUB}

def c(code: str) -> Card:
    """
    Utility:  c('As') -> Ace of spades  (rank char + suit letter)
              c('Td') -> Ten of diamonds
    """
    rank_ch, suit_ch = code[0].upper(), code[1].lower()
    if rank_ch not in RANK_CHARS or suit_ch not in SUIT_MAP:
        raise ValueError(f"Bad card code: {code}")
    return Card(rank_ch, SUIT_MAP[suit_ch])

def make_cards(codes: str) -> List[Card]:
    """make_cards('As Kd 7h') -> list[Card]"""
    return [c(tok) for tok in codes.split()]

# A single RNG seed for every simulation based test
random.seed(42)

# ──────────────────────────────────────────────────────
#  Test-Cases
# ──────────────────────────────────────────────────────
class TestHandRanking(unittest.TestCase):
    """
    One reference hand for every class from HIGH_CARD → STRAIGHT_FLUSH.
    A final test verifies that the ordering of the returned tuples follows
    poker rules (strictly ascending in strength).
    """

    def setUp(self):
        # Pre-build the example hands once
        self.examples = {
            HandRank.HIGH_CARD: (
                make_cards("As Kd"),                   # hole
                make_cards("9h 7c 6d 3s 2c")           # board
            ),
            HandRank.PAIR: (
                make_cards("As Ac"),
                make_cards("Kd Qh 7c 6d 3h")
            ),
            HandRank.TWO_PAIR: (
                make_cards("As Kd"),
                make_cards("Ac Kh 7c 6d 3h")
            ),
            HandRank.THREE_OF_A_KIND: (
                make_cards("As Ac"),
                make_cards("Ad Kh 7c 6d 3h")
            ),
            HandRank.STRAIGHT: (
                make_cards("9d 8s"),
                make_cards("Th 7h 6c Qc 2d")           # 6-7-8-9-T straight
            ),
            HandRank.FLUSH: (
                make_cards("As 3s"),
                make_cards("Ks 8s 5s 2d 9h")           # spade flush
            ),
            HandRank.FULL_HOUSE: (
                make_cards("As Ac"),
                make_cards("Ad Kc Kh 7d 3h")           # AAAKK
            ),
            HandRank.FOUR_OF_A_KIND: (
                make_cards("As Ac"),
                make_cards("Ah Ad Kc 7d 3h")           # AAAA
            ),
            HandRank.STRAIGHT_FLUSH: (
                make_cards("8s 9s"),
                make_cards("Ts 7s 6s Qc 2d")           # 6-7-8-9-T straight-flush
            ),
        }

    # One test per hand type – makes debugging easier
    def test_each_individual_rank_is_detected(self):
        for rank, (hole, board) in self.examples.items():
            with self.subTest(rank=rank):
                self.assertEqual(get_hand_rank(hole, board)[0], rank)

    def test_ranking_order(self):
        """
        Ensure that the tuple returned by get_hand_rank obeys the usual
        <, > semantics (python tuple comparison: hand-rank Enum value first,
        then kickers).
        """
        tuples = []
        for rank in HandRank:
            tup = get_hand_rank(*self.examples[rank])
            tuples.append(tup)

        # Ascending in strength
        for weaker, stronger in zip(tuples, tuples[1:]):
            with self.subTest(weaker=weaker, stronger=stronger):
                self.assertLess(weaker, stronger)


class TestStraightDetection(unittest.TestCase):
    def test_wheel_straight_ace_low(self):
        # A-2-3-4-5 straight (wheel)
        ranks = [12, 3, 2, 1, 0]            # A 5 4 3 2 (Ace=12)
        is_straight, high = check_straight(ranks)
        self.assertTrue(is_straight)
        # Highest card for wheel should be 3 (the five)
        self.assertEqual(high, 3)

    def test_no_straight(self):
        ranks = [12, 11, 9, 5, 3]
        self.assertFalse(check_straight(ranks)[0])


class TestHandTierDetection(unittest.TestCase):
    def test_premium(self):
        self.assertEqual(get_hand_tier(make_cards("As Ah")), "PREMIUM")
        self.assertEqual(get_hand_tier(make_cards("As Ks")), "PREMIUM")

    def test_strong(self):
        self.assertEqual(get_hand_tier(make_cards("Ad Qc")), "STRONG")

    def test_playable(self):
        self.assertEqual(get_hand_tier(make_cards("9s 8s")), "PLAYABLE")

    def test_weak(self):
        self.assertEqual(get_hand_tier(make_cards("3c 2d")), "WEAK")

    def test_unknown_if_not_two_cards(self):
        self.assertEqual(get_hand_tier([c("As")]), "UNKNOWN")


class TestBoardTexture(unittest.TestCase):
    def test_trips(self):
        texture = get_board_texture(make_cards("As Ad Ah"))
        self.assertIn("Trips", texture)

    def test_monotone(self):
        texture = get_board_texture(make_cards("2s 7s Ks"))
        self.assertIn("Monotone", texture)

    def test_paired(self):
        self.assertIn("Paired", get_board_texture(make_cards("Ah As 9d")))

    def test_connected(self):
        self.assertIn("Connected", get_board_texture(make_cards("4h 5c 6d")))

    def test_dry_ragged(self):
        self.assertEqual(get_board_texture(make_cards("Ah 7c 2d")), "Dry/Raggedy")

class TestEquityMonteCarlo(unittest.TestCase):
    """
    Uses a reduced simulation count to stay fast while still being meaningful.
    The RNG seed is fixed module-wide to make the tests fully deterministic.
    """

    def test_pocket_aces_favourite(self):
        equity = calculate_equity_monte_carlo(
            hole=make_cards("As Ah"),
            board=[],
            num_opponents=1,
            num_simulations=500
        )
        self.assertGreater(equity, 0.70)

    def test_seven_two_off_is_dog(self):
        equity = calculate_equity_monte_carlo(
            hole=make_cards("7c 2d"),
            board=[],
            num_opponents=1,
            num_simulations=500
        )
        self.assertLess(equity, 0.35)

    def test_equity_bounds(self):
        # Equity must always be between 0 and 1
        equity = calculate_equity_monte_carlo(
            hole=make_cards("Qc Jd"),
            board=make_cards("2h 5c"),
            num_opponents=3,
            num_simulations=300
        )
        self.assertTrue(0.0 <= equity <= 1.0)


class TestAnalysisAndDecision(unittest.TestCase):
    def test_preflop_raise_with_aces_on_button(self):
        analysis = analyse_hand(
            hole=make_cards("As Ah"),
            board=[],
            position=Position.BTN,
            stack_bb=StackType.MEDIUM.default_bb,
            pot=1.5,               # 0.5 + 1 blinds
            to_call=1.0,
            num_players=6
        )
        self.assertEqual(analysis.decision, "RAISE")

    def test_preflop_fold_utg_with_trash(self):
        analysis = analyse_hand(
            hole=make_cards("7d 2c"),
            board=[],
            position=Position.UTG,
            stack_bb=StackType.MEDIUM.default_bb,
            pot=1.5,
            to_call=1.0,
            num_players=6
        )
        self.assertEqual(analysis.decision, "FOLD")

    def test_edge_case_positive_call(self):
        # Slightly +EV call should suggest CALL, not FOLD
        analysis = analyse_hand(
            hole=make_cards("5h 5c"),      # medium pair
            board=make_cards("Qd 9s 2h"),  # dry flop
            position=Position.BB,
            stack_bb=StackType.DEEP.default_bb,
            pot=10.0,
            to_call=2.0,
            num_players=2
        )
        self.assertIn(analysis.decision, ("CALL", "RAISE"))


class TestUtilityHelpers(unittest.TestCase):
    def test_to_two_card_str(self):
        self.assertEqual(
            to_two_card_str(make_cards("As Ah")),
            "A♠A♥"
        )

    def test_card_string_representation(self):
        self.assertEqual(str(c("Kd")), "K♦")


if __name__ == "__main__":
    unittest.main()
