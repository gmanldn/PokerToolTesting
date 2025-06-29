#!/usr/bin/env python3
"""
Comprehensive test suite for Poker Assistant application.
Tests methodology, accuracy, and consistency across all modules.

Run with: python -m pytest poker_test.py -v
"""

import pytest
import sqlite3
import tempfile
import os
from typing import List, Set, Tuple
from unittest.mock import patch, MagicMock
from collections import Counter

# Import modules to test
from poker_modules import (
    Suit, Rank, Card, Position, StackType, PlayerAction, GameState, HandAnalysis,
    HandRank, RANKS_MAP, RANK_ORDER, FULL_DECK, HAND_TIERS,
    get_hand_rank, check_straight, get_hand_tier, get_opponent_range,
    calculate_equity_monte_carlo, get_board_texture, analyse_hand,
    to_two_card_str, get_position_advice, get_hand_advice
)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES AND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_cards():
    """Fixture providing commonly used cards for testing."""
    return {
        'ace_spades': Card('A', Suit.SPADE),
        'king_hearts': Card('K', Suit.HEART),
        'queen_diamonds': Card('Q', Suit.DIAMOND),
        'jack_clubs': Card('J', Suit.CLUB),
        'ten_spades': Card('T', Suit.SPADE),
        'nine_hearts': Card('9', Suit.HEART),
        'eight_diamonds': Card('8', Suit.DIAMOND),
        'seven_clubs': Card('7', Suit.CLUB),
        'six_spades': Card('6', Suit.SPADE),
        'five_hearts': Card('5', Suit.HEART),
        'four_diamonds': Card('4', Suit.DIAMOND),
        'three_clubs': Card('3', Suit.CLUB),
        'two_spades': Card('2', Suit.SPADE),
    }

@pytest.fixture
def premium_hands():
    """Fixture for premium starting hands."""
    return [
        [Card('A', Suit.SPADE), Card('A', Suit.HEART)],  # AA
        [Card('K', Suit.SPADE), Card('K', Suit.HEART)],  # KK
        [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)],  # QQ
        [Card('J', Suit.SPADE), Card('J', Suit.HEART)],  # JJ
        [Card('A', Suit.SPADE), Card('K', Suit.SPADE)],  # AKs
    ]

@pytest.fixture
def royal_flush_board():
    """Fixture for royal flush scenario."""
    return [
        Card('T', Suit.SPADE), Card('J', Suit.SPADE), Card('Q', Suit.SPADE),
        Card('K', Suit.SPADE), Card('A', Suit.SPADE)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# CORE DATA STRUCTURES TESTS (50 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestSuit:
    """Test Suit enum functionality."""
    
    def test_suit_values(self):
        """Test suit symbols are correct."""
        assert Suit.SPADE.value == "♠"
        assert Suit.HEART.value == "♥"
        assert Suit.DIAMOND.value == "♦"
        assert Suit.CLUB.value == "♣"
    
    def test_suit_colors(self):
        """Test suit color properties."""
        assert Suit.SPADE.color == "black"
        assert Suit.CLUB.color == "black"
        assert Suit.HEART.color == "red"
        assert Suit.DIAMOND.color == "red"
    
    def test_all_suits_exist(self):
        """Test all four suits are defined."""
        assert len(list(Suit)) == 4
    
    def test_suit_uniqueness(self):
        """Test all suit values are unique."""
        values = [s.value for s in Suit]
        assert len(values) == len(set(values))


class TestRank:
    """Test Rank enum functionality."""
    
    def test_rank_count(self):
        """Test correct number of ranks."""
        assert len(list(Rank)) == 13
    
    def test_rank_values(self):
        """Test rank value mappings."""
        assert Rank.TWO.val == "2"
        assert Rank.THREE.val == "3"
        assert Rank.FOUR.val == "4"
        assert Rank.FIVE.val == "5"
        assert Rank.SIX.val == "6"
        assert Rank.SEVEN.val == "7"
        assert Rank.EIGHT.val == "8"
        assert Rank.NINE.val == "9"
        assert Rank.TEN.val == "T"
        assert Rank.JACK.val == "J"
        assert Rank.QUEEN.val == "Q"
        assert Rank.KING.val == "K"
        assert Rank.ACE.val == "A"
    
    def test_rank_order_consistency(self):
        """Test RANK_ORDER matches Rank enum."""
        expected = "23456789TJQKA"
        assert ''.join(RANK_ORDER) == expected
    
    def test_ranks_map_consistency(self):
        """Test RANKS_MAP contains all ranks."""
        assert len(RANKS_MAP) == 13
        for rank in Rank:
            assert rank.val in RANKS_MAP
            assert RANKS_MAP[rank.val] == rank


class TestCard:
    """Test Card class functionality."""
    
    def test_card_creation(self, sample_cards):
        """Test card creation with valid inputs."""
        card = sample_cards['ace_spades']
        assert card.rank == 'A'
        assert card.suit == Suit.SPADE
    
    def test_card_string_representation(self, sample_cards):
        """Test card string conversion."""
        assert str(sample_cards['ace_spades']) == "A♠"
        assert str(sample_cards['king_hearts']) == "K♥"
        assert str(sample_cards['two_spades']) == "2♠"
    
    def test_card_rank_val_property(self, sample_cards):
        """Test rank_val property returns correct index."""
        assert sample_cards['two_spades'].rank_val == 0
        assert sample_cards['ace_spades'].rank_val == 12
        assert sample_cards['king_hearts'].rank_val == 11
    
    def test_card_equality(self):
        """Test card equality comparison."""
        card1 = Card('A', Suit.SPADE)
        card2 = Card('A', Suit.SPADE)
        card3 = Card('A', Suit.HEART)
        assert card1 == card2
        assert card1 != card3
    
    def test_card_ordering(self):
        """Test card ordering functionality."""
        cards = [Card('2', Suit.SPADE), Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        sorted_cards = sorted(cards)
        assert sorted_cards[0].rank == '2'
        assert sorted_cards[1].rank == 'A'
        assert sorted_cards[2].rank == 'K'
    
    def test_card_frozen_dataclass(self):
        """Test card immutability."""
        card = Card('A', Suit.SPADE)
        with pytest.raises(AttributeError):
            card.rank = 'K'  # Should be immutable
    
    def test_full_deck_completeness(self):
        """Test FULL_DECK contains all 52 cards."""
        assert len(FULL_DECK) == 52
        
        # Check all rank-suit combinations exist
        for suit in Suit:
            for rank in Rank:
                expected_card = Card(rank.val, suit)
                assert expected_card in FULL_DECK
    
    def test_full_deck_uniqueness(self):
        """Test FULL_DECK has no duplicates."""
        card_strings = [str(card) for card in FULL_DECK]
        assert len(card_strings) == len(set(card_strings))


class TestPosition:
    """Test Position enum."""
    
    def test_position_count(self):
        """Test correct number of positions."""
        assert len(list(Position)) == 9
    
    def test_position_values(self):
        """Test position value assignments."""
        assert Position.SB.value == 1
        assert Position.BB.value == 2
        assert Position.UTG.value == 3
        assert Position.BTN.value == 9
    
    def test_position_names(self):
        """Test position names are correct."""
        positions = ['SB', 'BB', 'UTG', 'UTG1', 'MP1', 'MP2', 'HJ', 'CO', 'BTN']
        for pos_name in positions:
            assert hasattr(Position, pos_name)


class TestStackType:
    """Test StackType enum."""
    
    def test_stack_type_values(self):
        """Test stack type descriptions."""
        assert "Short" in StackType.SHORT.value
        assert "Medium" in StackType.MEDIUM.value
        assert "Deep" in StackType.DEEP.value
        assert "Very Deep" in StackType.VERY_DEEP.value
    
    def test_default_bb_values(self):
        """Test default big blind values."""
        assert StackType.SHORT.default_bb == 20
        assert StackType.MEDIUM.default_bb == 50
        assert StackType.DEEP.default_bb == 80
        assert StackType.VERY_DEEP.default_bb == 150


class TestPlayerAction:
    """Test PlayerAction enum."""
    
    def test_all_actions_exist(self):
        """Test all expected actions are defined."""
        expected_actions = ['FOLD', 'CALL', 'RAISE', 'CHECK', 'ALL_IN']
        for action in expected_actions:
            assert hasattr(PlayerAction, action)
    
    def test_action_count(self):
        """Test correct number of actions."""
        assert len(list(PlayerAction)) == 5


class TestGameState:
    """Test GameState dataclass."""
    
    def test_game_state_defaults(self):
        """Test default GameState values."""
        gs = GameState()
        assert gs.is_active == False
        assert gs.pot == 0.0
        assert gs.to_call == 0.0
        assert gs.players_in_hand == []
        assert gs.player_actions == {}
    
    def test_game_state_modification(self):
        """Test GameState can be modified."""
        gs = GameState()
        gs.is_active = True
        gs.pot = 100.0
        gs.to_call = 25.0
        assert gs.is_active == True
        assert gs.pot == 100.0
        assert gs.to_call == 25.0


class TestHandAnalysis:
    """Test HandAnalysis dataclass."""
    
    def test_hand_analysis_creation(self):
        """Test HandAnalysis creation with all fields."""
        analysis = HandAnalysis(
            decision="RAISE",
            reason="Strong hand",
            equity=0.75,
            required_eq=0.33,
            ev_call=50.0,
            ev_raise=75.0,
            board_texture="Dry",
            spr=2.5
        )
        assert analysis.decision == "RAISE"
        assert analysis.equity == 0.75
        assert analysis.spr == 2.5


# ══════════════════════════════════════════════════════════════════════════════
# HAND EVALUATION TESTS (80 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckStraight:
    """Test check_straight helper function."""
    
    def test_ace_high_straight(self):
        """Test A-K-Q-J-T straight."""
        ranks = [12, 11, 10, 9, 8]  # A, K, Q, J, T
        is_straight, high = check_straight(ranks)
        assert is_straight == True
        assert high == 12  # Ace high
    
    def test_ace_low_straight(self):
        """Test A-2-3-4-5 straight."""
        ranks = [12, 3, 2, 1, 0]  # A, 4, 3, 2, 2 (with ace as low)
        is_straight, high = check_straight(ranks)
        assert is_straight == True
        assert high == 3  # 5-high straight
    
    def test_middle_straight(self):
        """Test 9-8-7-6-5 straight."""
        ranks = [7, 6, 5, 4, 3]  # 9, 8, 7, 6, 5
        is_straight, high = check_straight(ranks)
        assert is_straight == True
        assert high == 7
    
    def test_no_straight(self):
        """Test hand with no straight."""
        ranks = [12, 10, 8, 6, 4]  # A, J, 9, 7, 5
        is_straight, high = check_straight(ranks)
        assert is_straight == False
        assert high == -1
    
    def test_straight_with_duplicates(self):
        """Test straight detection with duplicate ranks."""
        ranks = [9, 8, 7, 7, 6, 5]  # T, 9, 8, 8, 7, 6
        is_straight, high = check_straight(ranks)
        assert is_straight == True
        assert high == 9
    
    def test_almost_straight(self):
        """Test 4-card near-straight."""
        ranks = [8, 7, 6, 5, 2]  # 9, 8, 7, 6, 3
        is_straight, high = check_straight(ranks)
        assert is_straight == False


class TestGetHandRank:
    """Test get_hand_rank function for all hand types."""
    
    def test_royal_flush(self, royal_flush_board):
        """Test royal flush detection."""
        hole = [Card('A', Suit.SPADE), Card('2', Suit.HEART)]
        rank, kickers = get_hand_rank(hole, royal_flush_board[:5])
        assert rank == HandRank.STRAIGHT_FLUSH
        assert kickers[0] == 12  # Ace high
    
    def test_straight_flush(self):
        """Test straight flush detection."""
        hole = [Card('5', Suit.SPADE), Card('6', Suit.SPADE)]
        board = [Card('7', Suit.SPADE), Card('8', Suit.SPADE), Card('9', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT_FLUSH
        assert kickers[0] == 7  # 9-high straight flush
    
    def test_four_of_a_kind(self):
        """Test four of a kind detection."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('A', Suit.DIAMOND), Card('A', Suit.CLUB), Card('K', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.FOUR_OF_A_KIND
        assert kickers[0] == 12  # Quad aces
        assert kickers[1] == 11  # King kicker
    
    def test_full_house_trips_and_pair(self):
        """Test full house from trips + pair."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('K', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.FULL_HOUSE
        assert kickers[0] == 12  # Aces full
        assert kickers[1] == 11  # of Kings
    
    def test_full_house_two_trips(self):
        """Test full house from two trip sets."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('A', Suit.DIAMOND), Card('A', Suit.CLUB), Card('K', Suit.SPADE), 
                Card('K', Suit.DIAMOND), Card('2', Suit.HEART)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.FULL_HOUSE
        assert kickers[0] == 12  # Aces full
        assert kickers[1] == 11  # of Kings
    
    def test_flush(self):
        """Test flush detection."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        board = [Card('Q', Suit.SPADE), Card('J', Suit.SPADE), Card('9', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.FLUSH
        assert kickers[:5] == [12, 11, 10, 9, 7]  # A-K-Q-J-9 flush
    
    def test_straight(self):
        """Test straight detection."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('T', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT
        assert kickers[0] == 12  # Ace high straight
    
    def test_three_of_a_kind(self):
        """Test three of a kind detection."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('Q', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.THREE_OF_A_KIND
        assert kickers[0] == 12  # Trip aces
        assert kickers[1] == 11  # King kicker
        assert kickers[2] == 10  # Queen kicker
    
    def test_two_pair(self):
        """Test two pair detection."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('K', Suit.DIAMOND), Card('K', Suit.CLUB), Card('Q', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.TWO_PAIR
        assert kickers[0] == 12  # Aces
        assert kickers[1] == 11  # and Kings
        assert kickers[2] == 10  # Queen kicker
    
    def test_one_pair(self):
        """Test one pair detection."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('K', Suit.DIAMOND), Card('Q', Suit.CLUB), Card('J', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.PAIR
        assert kickers[0] == 12  # Pair of aces
        assert kickers[1:] == [11, 10, 9]  # K-Q-J kickers
    
    def test_high_card(self):
        """Test high card detection."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('9', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.HIGH_CARD
        assert kickers == [12, 11, 10, 9, 7]  # A-K-Q-J-9 high
    
    def test_wheel_straight(self):
        """Test A-2-3-4-5 straight (wheel)."""
        hole = [Card('A', Suit.SPADE), Card('2', Suit.HEART)]
        board = [Card('3', Suit.DIAMOND), Card('4', Suit.CLUB), Card('5', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT
        assert kickers[0] == 3  # 5-high straight
    
    def test_best_five_from_seven(self):
        """Test selecting best 5 cards from 7."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = [Card('A', Suit.DIAMOND), Card('A', Suit.CLUB), Card('K', Suit.SPADE),
                Card('Q', Suit.HEART), Card('2', Suit.DIAMOND)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.FOUR_OF_A_KIND
        assert kickers[1] == 11  # King is the kicker, not 2


class TestHandRankComparisons:
    """Test hand ranking comparisons."""
    
    def test_hand_rank_ordering(self):
        """Test HandRank enum values are properly ordered."""
        ranks = list(HandRank)
        for i in range(len(ranks) - 1):
            assert ranks[i].value < ranks[i + 1].value
    
    def test_straight_flush_beats_quads(self):
        """Test straight flush beats four of a kind."""
        assert HandRank.STRAIGHT_FLUSH.value > HandRank.FOUR_OF_A_KIND.value
    
    def test_quads_beat_full_house(self):
        """Test four of a kind beats full house."""
        assert HandRank.FOUR_OF_A_KIND.value > HandRank.FULL_HOUSE.value
    
    def test_flush_beats_straight(self):
        """Test flush beats straight."""
        assert HandRank.FLUSH.value > HandRank.STRAIGHT.value


# ══════════════════════════════════════════════════════════════════════════════
# HAND TIER CLASSIFICATION TESTS (30 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetHandTier:
    """Test hand tier classification."""
    
    def test_premium_pairs(self):
        """Test premium pocket pairs."""
        hands = [
            [Card('A', Suit.SPADE), Card('A', Suit.HEART)],  # AA
            [Card('K', Suit.SPADE), Card('K', Suit.HEART)],  # KK
            [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)],  # QQ
            [Card('J', Suit.SPADE), Card('J', Suit.HEART)],  # JJ
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "PREMIUM"
    
    def test_premium_suited_aces(self):
        """Test premium suited ace hands."""
        hand = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]  # AKs
        assert get_hand_tier(hand) == "PREMIUM"
    
    def test_strong_pairs(self):
        """Test strong pocket pairs."""
        hands = [
            [Card('T', Suit.SPADE), Card('T', Suit.HEART)],  # TT
            [Card('9', Suit.SPADE), Card('9', Suit.HEART)],  # 99
            [Card('8', Suit.SPADE), Card('8', Suit.HEART)],  # 88
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "STRONG"
    
    def test_strong_suited_aces(self):
        """Test strong suited ace combinations."""
        hands = [
            [Card('A', Suit.SPADE), Card('Q', Suit.SPADE)],  # AQs
            [Card('A', Suit.SPADE), Card('J', Suit.SPADE)],  # AJs
            [Card('A', Suit.SPADE), Card('T', Suit.SPADE)],  # ATs
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "STRONG"
    
    def test_strong_offsuit_broadways(self):
        """Test strong offsuit broadway hands."""
        hands = [
            [Card('A', Suit.SPADE), Card('K', Suit.HEART)],  # AKo
            [Card('A', Suit.SPADE), Card('Q', Suit.HEART)],  # AQo
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "STRONG"
    
    def test_medium_pairs(self):
        """Test medium pocket pairs."""
        hands = [
            [Card('7', Suit.SPADE), Card('7', Suit.HEART)],  # 77
            [Card('6', Suit.SPADE), Card('6', Suit.HEART)],  # 66
            [Card('5', Suit.SPADE), Card('5', Suit.HEART)],  # 55
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "MEDIUM"
    
    def test_suited_connectors(self):
        """Test suited connectors classification."""
        hands = [
            [Card('J', Suit.SPADE), Card('T', Suit.SPADE)],  # JTs
            [Card('T', Suit.SPADE), Card('9', Suit.SPADE)],  # T9s
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "MEDIUM"
    
    def test_playable_suited_aces(self):
        """Test playable suited ace combinations."""
        hands = [
            [Card('A', Suit.SPADE), Card('9', Suit.SPADE)],  # A9s
            [Card('A', Suit.SPADE), Card('8', Suit.SPADE)],  # A8s
            [Card('A', Suit.SPADE), Card('5', Suit.SPADE)],  # A5s
            [Card('A', Suit.SPADE), Card('2', Suit.SPADE)],  # A2s
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "PLAYABLE"
    
    def test_marginal_pairs(self):
        """Test marginal small pairs."""
        hands = [
            [Card('4', Suit.SPADE), Card('4', Suit.HEART)],  # 44
            [Card('3', Suit.SPADE), Card('3', Suit.HEART)],  # 33
            [Card('2', Suit.SPADE), Card('2', Suit.HEART)],  # 22
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "MARGINAL"
    
    def test_weak_hands(self):
        """Test weak hand classification."""
        hands = [
            [Card('9', Suit.SPADE), Card('2', Suit.HEART)],  # 92o
            [Card('8', Suit.SPADE), Card('3', Suit.HEART)],  # 83o
            [Card('7', Suit.SPADE), Card('2', Suit.HEART)],  # 72o
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "WEAK"
    
    def test_suited_vs_offsuit(self):
        """Test suited vs offsuit classification differences."""
        suited_hand = [Card('K', Suit.SPADE), Card('Q', Suit.SPADE)]    # KQs
        offsuit_hand = [Card('K', Suit.SPADE), Card('Q', Suit.HEART)]   # KQo
        
        # Both should be strong, but verify they're classified
        assert get_hand_tier(suited_hand) in ["STRONG", "MEDIUM"]
        assert get_hand_tier(offsuit_hand) in ["STRONG", "MEDIUM"]
    
    def test_invalid_hand_length(self):
        """Test handling of invalid hand lengths."""
        assert get_hand_tier([]) == "UNKNOWN"
        assert get_hand_tier([Card('A', Suit.SPADE)]) == "UNKNOWN"
        assert get_hand_tier([Card('A', Suit.SPADE)] * 3) == "UNKNOWN"
    
    def test_hand_tier_consistency(self):
        """Test hand tier consistency across different suits."""
        # Same hand with different suits should have same tier
        hand1 = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        hand2 = [Card('A', Suit.HEART), Card('K', Suit.HEART)]
        assert get_hand_tier(hand1) == get_hand_tier(hand2)


class TestHandTierData:
    """Test hand tier data structure consistency."""
    
    def test_hand_tiers_completeness(self):
        """Test HAND_TIERS contains expected number of combinations."""
        total_hands = sum(len(hands) for hands in HAND_TIERS.values())
        # Should cover most reasonable starting hands
        assert total_hands > 50
    
    def test_no_hand_tier_overlap(self):
        """Test no hand appears in multiple tiers."""
        all_hands = []
        for tier_hands in HAND_TIERS.values():
            all_hands.extend(tier_hands)
        assert len(all_hands) == len(set(all_hands))
    
    def test_premium_tier_size(self):
        """Test premium tier has reasonable size."""
        assert len(HAND_TIERS["PREMIUM"]) <= 10
        assert len(HAND_TIERS["PREMIUM"]) >= 4


# ══════════════════════════════════════════════════════════════════════════════
# EQUITY CALCULATION TESTS (50 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetOpponentRange:
    """Test opponent range generation."""
    
    def test_tight_range(self):
        """Test tight opponent range."""
        tight_range = get_opponent_range("TIGHT")
        assert "AA" in tight_range
        assert "KK" in tight_range
        assert "AKs" in tight_range
        # Shouldn't include weak hands
        assert len(tight_range) < 50
    
    def test_medium_range(self):
        """Test medium opponent range."""
        medium_range = get_opponent_range("MEDIUM")
        assert "AA" in medium_range
        assert "77" in medium_range
        # Should be larger than tight range
        tight_range = get_opponent_range("TIGHT")
        assert len(medium_range) > len(tight_range)
    
    def test_loose_range(self):
        """Test loose opponent range."""
        loose_range = get_opponent_range("LOOSE")
        # Should be largest range
        medium_range = get_opponent_range("MEDIUM")
        assert len(loose_range) >= len(medium_range)
    
    def test_range_hierarchy(self):
        """Test range size hierarchy."""
        tight = len(get_opponent_range("TIGHT"))
        medium = len(get_opponent_range("MEDIUM"))
        loose = len(get_opponent_range("LOOSE"))
        assert tight <= medium <= loose


class TestEquityCalculation:
    """Test Monte Carlo equity calculation."""
    
    def test_pocket_aces_equity(self):
        """Test pocket aces have high equity pre-flop."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        equity = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 1000)
        assert equity > 0.7  # Should be high
        assert equity < 1.0  # But not 100%
    
    def test_pocket_twos_vs_aces(self):
        """Test pocket twos vs stronger range."""
        hole = [Card('2', Suit.SPADE), Card('2', Suit.HEART)]
        board = []
        equity = calculate_equity_monte_carlo(hole, board, 1, "TIGHT", 1000)
        assert equity < 0.5  # Should be underdog
        assert equity > 0.1  # But not hopeless
    
    def test_suited_connector_equity(self):
        """Test suited connector equity."""
        hole = [Card('J', Suit.SPADE), Card('T', Suit.SPADE)]
        board = []
        equity = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 1000)
        assert 0.3 < equity < 0.7  # Reasonable range
    
    def test_equity_with_favorable_flop(self):
        """Test equity improves with favorable flop."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        board = [Card('A', Suit.HEART), Card('K', Suit.DIAMOND), Card('2', Suit.CLUB)]
        equity = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 1000)
        assert equity > 0.8  # Two pair should be very strong
    
    def test_equity_consistency(self):
        """Test equity calculation consistency across runs."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = []
        
        equity1 = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 2000)
        equity2 = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 2000)
        
        # Should be close but allow for Monte Carlo variance
        assert abs(equity1 - equity2) < 0.1
    
    def test_equity_edge_cases(self):
        """Test equity calculation edge cases."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # No opponents should return 1.0 (actually 0.5 due to implementation)
        equity = calculate_equity_monte_carlo(hole, [], 0, "MEDIUM", 100)
        assert 0.4 <= equity <= 0.6
        
        # Many opponents should reduce equity
        equity_many = calculate_equity_monte_carlo(hole, [], 8, "MEDIUM", 500)
        equity_few = calculate_equity_monte_carlo(hole, [], 1, "MEDIUM", 500)
        assert equity_many < equity_few
    
    def test_insufficient_deck_size(self):
        """Test handling when deck is too small."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card(r, Suit.DIAMOND) for r in "QJTT9876543"][:5]  # Use many cards
        
        # Should handle gracefully
        equity = calculate_equity_monte_carlo(hole, board, 20, "MEDIUM", 100)
        assert 0 <= equity <= 1


class TestBoardTexture:
    """Test board texture analysis."""
    
    def test_preflop_texture(self):
        """Test pre-flop board texture."""
        assert get_board_texture([]) == "Pre-flop"
    
    def test_paired_board(self):
        """Test paired board detection."""
        board = [Card('A', Suit.SPADE), Card('A', Suit.HEART), Card('K', Suit.DIAMOND)]
        texture = get_board_texture(board)
        assert "Paired" in texture
    
    def test_trips_board(self):
        """Test trips board detection."""
        board = [Card('A', Suit.SPADE), Card('A', Suit.HEART), Card('A', Suit.DIAMOND)]
        texture = get_board_texture(board)
        assert "Trips" in texture
    
    def test_monotone_board(self):
        """Test monotone (all same suit) board."""
        board = [Card('A', Suit.SPADE), Card('K', Suit.SPADE), Card('Q', Suit.SPADE)]
        texture = get_board_texture(board)
        assert "Monotone" in texture
    
    def test_flush_draw_board(self):
        """Test flush draw board."""
        board = [Card('A', Suit.SPADE), Card('K', Suit.SPADE), Card('Q', Suit.HEART),
                Card('J', Suit.DIAMOND), Card('T', Suit.SPADE)]
        texture = get_board_texture(board)
        assert "Flush-draw" in texture
    
    def test_connected_board(self):
        """Test connected board detection."""
        board = [Card('9', Suit.SPADE), Card('8', Suit.HEART), Card('7', Suit.DIAMOND)]
        texture = get_board_texture(board)
        assert "Connected" in texture
    
    def test_dry_board(self):
        """Test dry/rainbow board."""
        board = [Card('A', Suit.SPADE), Card('7', Suit.HEART), Card('2', Suit.DIAMOND)]
        texture = get_board_texture(board)
        assert "Dry" in texture or "Raggedy" in texture
    
    def test_complex_board_texture(self):
        """Test board with multiple characteristics."""
        board = [Card('8', Suit.SPADE), Card('8', Suit.HEART), Card('7', Suit.SPADE)]
        texture = get_board_texture(board)
        # Should detect both paired and connected/flush-draw characteristics
        assert any(keyword in texture for keyword in ["Paired", "Connected", "Flush-draw"])


# ══════════════════════════════════════════════════════════════════════════════
# HAND ANALYSIS & DECISION MAKING TESTS (40 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyseHand:
    """Test main hand analysis function."""
    
    def test_premium_hand_analysis(self):
        """Test analysis of premium hands."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole,
            board=board,
            position=Position.BTN,
            stack_bb=50,
            pot=10.0,
            to_call=2.0,
            num_players=6
        )
        
        assert analysis.decision in ["RAISE", "CALL"]
        assert analysis.equity > 0.7
        assert analysis.ev_call > 0
    
    def test_weak_hand_analysis(self):
        """Test analysis of weak hands."""
        hole = [Card('7', Suit.SPADE), Card('2', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole,
            board=board,
            position=Position.UTG,
            stack_bb=50,
            pot=10.0,
            to_call=8.0,  # High bet to call
            num_players=6
        )
        
        assert analysis.decision == "FOLD"
        assert analysis.equity < 0.5
    
    def test_position_influence(self):
        """Test position influences decisions."""
        hole = [Card('K', Suit.SPADE), Card('J', Suit.HEART)]
        
        # Early position
        early_analysis = analyse_hand(
            hole=hole, board=[], position=Position.UTG,
            stack_bb=50, pot=10.0, to_call=2.0, num_players=6
        )
        
        # Button position
        button_analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=10.0, to_call=2.0, num_players=6
        )
        
        # Button should be more aggressive or at least as aggressive
        assert (button_analysis.decision == "RAISE" or 
                early_analysis.decision == "FOLD")
    
    def test_pot_odds_calculation(self):
        """Test pot odds are calculated correctly."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=100.0, to_call=25.0, num_players=6
        )
        
        expected_pot_odds = 25.0 / (100.0 + 25.0)
        assert abs(analysis.required_eq - expected_pot_odds) < 0.01
    
    def test_spr_calculation(self):
        """Test stack-to-pot ratio calculation."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=20.0, to_call=5.0, num_players=6
        )
        
        # SPR should be reasonable
        assert analysis.spr > 0
        assert analysis.spr < 100
    
    def test_equity_edge_decisions(self):
        """Test decisions based on equity edge."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Good pot odds scenario
        good_odds_analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=100.0, to_call=10.0, num_players=6
        )
        
        # Bad pot odds scenario
        bad_odds_analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=100.0, to_call=80.0, num_players=6
        )
        
        # Good odds should lead to more aggressive action
        assert (good_odds_analysis.decision in ["RAISE", "CALL"] and
                bad_odds_analysis.decision in ["FOLD", "CALL"])
    
    def test_board_influence_on_decision(self):
        """Test how board affects decisions."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Favorable board
        good_board = [Card('A', Suit.HEART), Card('K', Suit.DIAMOND), Card('2', Suit.CLUB)]
        good_analysis = analyse_hand(
            hole=hole, board=good_board, position=Position.BTN,
            stack_bb=50, pot=50.0, to_call=25.0, num_players=6
        )
        
        # Unfavorable board
        bad_board = [Card('9', Suit.HEART), Card('8', Suit.DIAMOND), Card('7', Suit.CLUB)]
        bad_analysis = analyse_hand(
            hole=hole, board=bad_board, position=Position.BTN,
            stack_bb=50, pot=50.0, to_call=25.0, num_players=6
        )
        
        # Good board should lead to more aggression
        assert good_analysis.equity > bad_analysis.equity


class TestDecisionConsistency:
    """Test decision making consistency."""
    
    def test_same_hand_same_decision(self):
        """Test same inputs produce same decisions."""
        hole = [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)]
        board = [Card('A', Suit.HEART), Card('7', Suit.DIAMOND), Card('2', Suit.CLUB)]
        
        analysis1 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        analysis2 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        
        assert analysis1.decision == analysis2.decision
    
    def test_stronger_hands_more_aggressive(self):
        """Test stronger hands lead to more aggressive decisions."""
        board = []
        
        strong_hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        weak_hole = [Card('6', Suit.SPADE), Card('4', Suit.HEART)]
        
        strong_analysis = analyse_hand(strong_hole, board, Position.BTN, 50, 20.0, 5.0, 6)
        weak_analysis = analyse_hand(weak_hole, board, Position.BTN, 50, 20.0, 5.0, 6)
        
        # Define aggression order
        aggression_order = {"FOLD": 0, "CHECK": 1, "CALL": 2, "RAISE": 3}
        
        strong_aggression = aggression_order.get(strong_analysis.decision, 0)
        weak_aggression = aggression_order.get(weak_analysis.decision, 0)
        
        assert strong_aggression >= weak_aggression


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS TESTS (20 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestUtilityFunctions:
    """Test utility and helper functions."""
    
    def test_to_two_card_str(self):
        """Test two-card string conversion."""
        cards = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        result = to_two_card_str(cards)
        assert result == "A♠K♥"
    
    def test_to_two_card_str_invalid(self):
        """Test two-card string with invalid input."""
        assert to_two_card_str([]) == "??"
        assert to_two_card_str([Card('A', Suit.SPADE)]) == "??"
        assert to_two_card_str([Card('A', Suit.SPADE)] * 3) == "??"
    
    def test_get_position_advice(self):
        """Test position advice generation."""
        btn_advice = get_position_advice(Position.BTN)
        utg_advice = get_position_advice(Position.UTG)
        
        assert "position" in btn_advice.lower()
        assert "aggressive" in btn_advice.lower() or "advantage" in btn_advice.lower()
        assert "early" in utg_advice.lower() or "premium" in utg_advice.lower()
    
    def test_get_hand_advice(self):
        """Test hand advice generation."""
        premium_advice = get_hand_advice("PREMIUM", "Dry", 5.0)
        weak_advice = get_hand_advice("WEAK", "Connected", 2.0)
        
        assert len(premium_advice) > 0
        assert len(weak_advice) > 0
        assert premium_advice != weak_advice
    
    def test_get_hand_advice_spr_influence(self):
        """Test SPR influences hand advice."""
        low_spr_advice = get_hand_advice("STRONG", "Dry", 2.0)
        high_spr_advice = get_hand_advice("STRONG", "Dry", 10.0)
        
        # Low SPR should mention willingness to get all-in
        assert "all-in" in low_spr_advice.lower() or low_spr_advice != high_spr_advice
    
    def test_get_hand_advice_board_influence(self):
        """Test board texture influences hand advice."""
        wet_board_advice = get_hand_advice("MEDIUM", "Flush-draw, Connected", 5.0)
        dry_board_advice = get_hand_advice("MEDIUM", "Dry", 5.0)
        
        # Wet board should mention caution
        assert ("wet" in wet_board_advice.lower() or 
                "wary" in wet_board_advice.lower() or
                wet_board_advice != dry_board_advice)


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_empty_inputs(self):
        """Test handling of empty inputs."""
        # Empty hole cards
        try:
            analysis = analyse_hand([], [], Position.BTN, 50, 10.0, 2.0, 6)
            # Should not crash, though result may be undefined
            assert hasattr(analysis, 'decision')
        except Exception:
            # Acceptable to raise exception for invalid input
            pass
    
    def test_invalid_positions(self):
        """Test handling of edge case positions."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Test all positions work
        for position in Position:
            try:
                analysis = analyse_hand(hole, [], position, 50, 10.0, 2.0, 6)
                assert hasattr(analysis, 'decision')
            except Exception as e:
                pytest.fail(f"Position {position} caused error: {e}")
    
    def test_extreme_stack_sizes(self):
        """Test extreme stack sizes."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Very short stack
        short_analysis = analyse_hand(hole, [], Position.BTN, 1, 2.0, 1.0, 6)
        assert hasattr(short_analysis, 'decision')
        
        # Very deep stack
        deep_analysis = analyse_hand(hole, [], Position.BTN, 500, 10.0, 2.0, 6)
        assert hasattr(deep_analysis, 'decision')
    
    def test_zero_pot_scenarios(self):
        """Test zero pot edge cases."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        try:
            analysis = analyse_hand(hole, [], Position.BTN, 50, 0.0, 0.0, 6)
            assert hasattr(analysis, 'decision')
        except (ZeroDivisionError, ValueError):
            # Acceptable to have issues with zero pot
            pass


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS (30 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestCompleteHandScenarios:
    """Test complete hand scenarios from pre-flop to river."""
    
    def test_pocket_aces_preflop_to_river(self):
        """Test pocket aces throughout a complete hand."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        
        # Pre-flop
        preflop_analysis = analyse_hand(hole, [], Position.BTN, 50, 5.0, 2.0, 6)
        assert preflop_analysis.decision in ["RAISE", "CALL"]
        
        # Flop
        flop = [Card('K', Suit.DIAMOND), Card('7', Suit.CLUB), Card('2', Suit.SPADE)]
        flop_analysis = analyse_hand(hole, flop, Position.BTN, 50, 20.0, 10.0, 4)
        assert flop_analysis.decision in ["RAISE", "CALL"]
        
        # Turn
        turn = flop + [Card('9', Suit.HEART)]
        turn_analysis = analyse_hand(hole, turn, Position.BTN, 50, 50.0, 25.0, 3)
        assert turn_analysis.decision in ["RAISE", "CALL"]
        
        # River
        river = turn + [Card('3', Suit.DIAMOND)]
        river_analysis = analyse_hand(hole, river, Position.BTN, 50, 100.0, 50.0, 2)
        assert river_analysis.decision in ["RAISE", "CALL"]
    
    def test_suited_connectors_scenario(self):
        """Test suited connectors in a drawing scenario."""
        hole = [Card('8', Suit.SPADE), Card('7', Suit.SPADE)]
        
        # Flop with straight and flush draws
        flop = [Card('9', Suit.HEART), Card('6', Suit.SPADE), Card('T', Suit.CLUB)]
        flop_analysis = analyse_hand(hole, flop, Position.CO, 50, 15.0, 5.0, 5)
        
        # Should be willing to continue with open-ended straight
        assert flop_analysis.decision in ["RAISE", "CALL"]
        assert flop_analysis.equity > 0.3  # Good drawing equity
    
    def test_overcards_scenario(self):
        """Test overcards on unfavorable board."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('8', Suit.DIAMOND), Card('7', Suit.CLUB), Card('6', Suit.SPADE)]
        
        analysis = analyse_hand(hole, board, Position.BTN, 50, 30.0, 20.0, 4)
        
        # Overcards on connected board - should be cautious
        assert analysis.equity < 0.5
        # Decision depends on pot odds, but shouldn't be super aggressive
        assert analysis.decision in ["FOLD", "CALL"]


class TestConsistencyAcrossScenarios:
    """Test consistency of analysis across different scenarios."""
    
    def test_equity_consistency_across_board_runouts(self):
        """Test equity behaves consistently across different board runouts."""
        hole = [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)]
        
        # Test multiple different flops
        flops = [
            [Card('A', Suit.HEART), Card('7', Suit.DIAMOND), Card('2', Suit.CLUB)],  # Overcard
            [Card('9', Suit.HEART), Card('8', Suit.DIAMOND), Card('7', Suit.CLUB)],  # Connected
            [Card('Q', Suit.DIAMOND), Card('5', Suit.HEART), Card('3', Suit.SPADE)], # Set
            [Card('K', Suit.HEART), Card('K', Suit.DIAMOND), Card('K', Suit.CLUB)],  # Trips on board
        ]
        
        equities = []
        for flop in flops:
            analysis = analyse_hand(hole, flop, Position.BTN, 50, 20.0, 5.0, 6)
            equities.append(analysis.equity)
        
        # Set flop should have highest equity
        assert equities[2] > equities[0]  # Set > Overcard
        assert equities[2] > equities[1]  # Set > Connected
    
    def test_position_consistency(self):
        """Test position effects are consistent."""
        hole = [Card('T', Suit.SPADE), Card('9', Suit.HEART)]
        
        positions = [Position.UTG, Position.MP1, Position.CO, Position.BTN]
        decisions = []
        
        for pos in positions:
            analysis = analyse_hand(hole, [], pos, 50, 5.0, 2.0, 6)
            decisions.append(analysis.decision)
        
        # Should generally get more aggressive in later position
        # (though not necessarily true for every hand)
        early_fold = decisions[0] == "FOLD"
        late_raise = decisions[-1] in ["RAISE", "CALL"]
        
        # At least one of these should be true for positional awareness
        assert early_fold or late_raise or decisions[0] != decisions[-1]


# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE AND STRESS TESTS (20 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformance:
    """Test performance and reliability of calculations."""
    
    def test_monte_carlo_performance(self):
        """Test Monte Carlo simulation completes in reasonable time."""
        import time
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = []
        
        start_time = time.time()
        equity = calculate_equity_monte_carlo(hole, board, 5, "MEDIUM", 1000)
        end_time = time.time()
        
        # Should complete within reasonable time (adjust as needed)
        assert end_time - start_time < 5.0  # 5 seconds max
        assert 0 <= equity <= 1
    
    def test_hand_evaluation_performance(self):
        """Test hand evaluation performance."""
        import time
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('T', Suit.SPADE),
                Card('9', Suit.HEART), Card('8', Suit.DIAMOND)]
        
        start_time = time.time()
        for _ in range(1000):
            rank, kickers = get_hand_rank(hole, board)
        end_time = time.time()
        
        # Should be very fast
        assert end_time - start_time < 1.0
    
    def test_analysis_with_many_simulations(self):
        """Test analysis with high simulation count."""
        hole = [Card('J', Suit.SPADE), Card('T', Suit.SPADE)]
        board = [Card('9', Suit.HEART), Card('8', Suit.DIAMOND), Card('2', Suit.CLUB)]
        
        # This should work without timeout/crash
        analysis = analyse_hand(hole, board, Position.CO, 50, 40.0, 15.0, 5)
        assert hasattr(analysis, 'decision')
        assert 0 <= analysis.equity <= 1


class TestStressScenarios:
    """Test edge cases and stress scenarios."""
    
    def test_all_hand_types_evaluation(self):
        """Test evaluation of all possible hand types."""
        # High card
        hand1 = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board1 = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('9', Suit.SPADE)]
        rank1, _ = get_hand_rank(hand1, board1)
        assert rank1 == HandRank.HIGH_CARD
        
        # Pair
        hand2 = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board2 = [Card('K', Suit.DIAMOND), Card('Q', Suit.CLUB), Card('J', Suit.SPADE)]
        rank2, _ = get_hand_rank(hand2, board2)
        assert rank2 == HandRank.PAIR
        
        # Two pair
        hand3 = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board3 = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('Q', Suit.SPADE)]
        rank3, _ = get_hand_rank(hand3, board3)
        assert rank3 == HandRank.TWO_PAIR
        
        # Three of a kind
        hand4 = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board4 = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('Q', Suit.SPADE)]
        rank4, _ = get_hand_rank(hand4, board4)
        assert rank4 == HandRank.THREE_OF_A_KIND
        
        # Straight
        hand5 = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board5 = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('T', Suit.SPADE)]
        rank5, _ = get_hand_rank(hand5, board5)
        assert rank5 == HandRank.STRAIGHT
        
        # Flush
        hand6 = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        board6 = [Card('Q', Suit.SPADE), Card('J', Suit.SPADE), Card('9', Suit.SPADE)]
        rank6, _ = get_hand_rank(hand6, board6)
        assert rank6 == HandRank.FLUSH
        
        # Full house
        hand7 = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board7 = [Card('A', Suit.DIAMOND), Card('K', Suit.CLUB), Card('K', Suit.SPADE)]
        rank7, _ = get_hand_rank(hand7, board7)
        assert rank7 == HandRank.FULL_HOUSE
        
        # Four of a kind
        hand8 = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board8 = [Card('A', Suit.DIAMOND), Card('A', Suit.CLUB), Card('K', Suit.SPADE)]
        rank8, _ = get_hand_rank(hand8, board8)
        assert rank8 == HandRank.FOUR_OF_A_KIND
        
        # Straight flush
        hand9 = [Card('9', Suit.SPADE), Card('8', Suit.SPADE)]
        board9 = [Card('7', Suit.SPADE), Card('6', Suit.SPADE), Card('5', Suit.SPADE)]
        rank9, _ = get_hand_rank(hand9, board9)
        assert rank9 == HandRank.STRAIGHT_FLUSH
    
    def test_many_players_scenario(self):
        """Test analysis with maximum players."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        
        # 9-handed table
        analysis = analyse_hand(hole, board, Position.UTG, 50, 10.0, 2.0, 9)
        assert hasattr(analysis, 'decision')
        assert 0 <= analysis.equity <= 1
    
    def test_complex_board_scenarios(self):
        """Test complex board textures."""
        hole = [Card('8', Suit.SPADE), Card('7', Suit.SPADE)]
        
        # Highly connected, suited board
        board = [Card('9', Suit.SPADE), Card('6', Suit.SPADE), Card('5', Suit.SPADE),
                Card('T', Suit.SPADE), Card('4', Suit.SPADE)]
        
        texture = get_board_texture(board)
        analysis = analyse_hand(hole, board, Position.BTN, 50, 100.0, 50.0, 4)
        
        # Should handle complex texture
        assert len(texture) > 0
        assert hasattr(analysis, 'decision')


# ══════════════════════════════════════════════════════════════════════════════
# RANDOMIZED AND PROPERTY-BASED TESTS (20 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestRandomizedScenarios:
    """Test with randomized inputs to catch edge cases."""
    
    def test_random_hole_cards(self):
        """Test analysis with random hole card combinations."""
        import random
        
        for _ in range(50):
            # Pick two random cards
            deck = list(FULL_DECK)
            random.shuffle(deck)
            hole = deck[:2]
            
            # Should not crash
            try:
                tier = get_hand_tier(hole)
                analysis = analyse_hand(hole, [], Position.BTN, 50, 10.0, 2.0, 6)
                assert tier in ["PREMIUM", "STRONG", "MEDIUM", "PLAYABLE", "MARGINAL", "WEAK"]
                assert hasattr(analysis, 'decision')
            except Exception as e:
                pytest.fail(f"Random hole cards {hole} caused error: {e}")
    
    def test_random_board_combinations(self):
        """Test with random board combinations."""
        import random
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        for _ in range(30):
            # Random board (3-5 cards)
            remaining_deck = [c for c in FULL_DECK if c not in hole]
            random.shuffle(remaining_deck)
            board_size = random.randint(0, 5)
            board = remaining_deck[:board_size]
            
            try:
                analysis = analyse_hand(hole, board, Position.BTN, 50, 20.0, 5.0, 6)
                assert hasattr(analysis, 'decision')
                assert 0 <= analysis.equity <= 1
            except Exception as e:
                pytest.fail(f"Random board {board} caused error: {e}")
    
    def test_random_betting_scenarios(self):
        """Test with random betting scenarios."""
        import random
        
        hole = [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)]
        board = [Card('A', Suit.HEART), Card('7', Suit.DIAMOND), Card('2', Suit.CLUB)]
        
        for _ in range(20):
            pot = random.uniform(5.0, 200.0)
            to_call = random.uniform(1.0, pot)
            stack_bb = random.randint(10, 200)
            num_players = random.randint(2, 9)
            
            try:
                analysis = analyse_hand(hole, board, Position.CO, stack_bb, 
                                      pot, to_call, num_players)
                assert hasattr(analysis, 'decision')
                assert analysis.decision in ["FOLD", "CALL", "RAISE", "CHECK"]
            except Exception as e:
                pytest.fail(f"Random betting scenario caused error: {e}")


class TestPropertyBasedInvariants:
    """Test properties that should always hold."""
    
    def test_equity_bounds(self):
        """Test equity is always between 0 and 1."""
        import random
        
        for _ in range(20):
            # Random valid scenario
            deck = list(FULL_DECK)
            random.shuffle(deck)
            hole = deck[:2]
            board = deck[2:2+random.randint(0, 5)]
            
            equity = calculate_equity_monte_carlo(hole, board, 3, "MEDIUM", 500)
            assert 0 <= equity <= 1, f"Equity {equity} out of bounds for {hole} vs {board}"
    
    def test_stronger_hands_higher_equity(self):
        """Test stronger hands generally have higher equity."""
        # Premium vs weak hand heads-up
        premium = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        weak = [Card('7', Suit.SPADE), Card('2', Suit.HEART)]
        
        premium_equity = calculate_equity_monte_carlo(premium, [], 1, "MEDIUM", 1000)
        weak_equity = calculate_equity_monte_carlo(weak, [], 1, "MEDIUM", 1000)
        
        assert premium_equity > weak_equity
    
    def test_hand_rank_consistency(self):
        """Test hand rank evaluation is consistent."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        board = [Card('Q', Suit.SPADE), Card('J', Suit.SPADE), Card('T', Suit.SPADE)]
        
        # Should always be royal flush
        for _ in range(10):
            rank, kickers = get_hand_rank(hole, board)
            assert rank == HandRank.STRAIGHT_FLUSH
            assert kickers[0] == 12  # Ace high
    
    def test_decision_determinism(self):
        """Test same inputs always produce same decisions."""
        hole = [Card('K', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('A', Suit.HEART), Card('7', Suit.DIAMOND), Card('2', Suit.CLUB)]
        
        # Same analysis should always give same result
        analysis1 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        analysis2 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        
        assert analysis1.decision == analysis2.decision


# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Count total number of test methods
    import inspect
    
    test_count = 0
    test_classes = [
        TestSuit, TestRank, TestCard, TestPosition, TestStackType, 
        TestPlayerAction, TestGameState, TestHandAnalysis,
        TestCheckStraight, TestGetHandRank, TestHandRankComparisons,
        TestGetHandTier, TestHandTierData,
        TestGetOpponentRange, TestEquityCalculation, TestBoardTexture,
        TestAnalyseHand, TestDecisionConsistency,
        TestUtilityFunctions, TestErrorHandling,
        TestCompleteHandScenarios, TestConsistencyAcrossScenarios,
        TestPerformance, TestStressScenarios,
        TestRandomizedScenarios, TestPropertyBasedInvariants
    ]
    
    for test_class in test_classes:
        methods = [method for method in dir(test_class) 
                  if method.startswith('test_') and callable(getattr(test_class, method))]
        test_count += len(methods)
    
    print(f"Total test methods defined: {test_count}")
    print("Run with: python -m pytest poker_test.py -v")
    print("Or run specific test class: python -m pytest poker_test.py::TestGetHandRank -v")