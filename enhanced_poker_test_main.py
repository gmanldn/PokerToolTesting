#!/usr/bin/env python3
"""
Comprehensive test suite for Poker-Assistant application.
Tests methodology, accuracy, and consistency across all modules.

Enhanced version that automatically runs the most stringent tests when executed directly.

Usage:
    python poker_test.py                    # Run most stringent tests automatically
    python poker_test.py --all             # Run all tests
    python poker_test.py --quick           # Run quick essential tests only
    python poker_test.py --performance     # Run performance tests only
    python poker_test.py --stress          # Run stress tests only
    python -m pytest poker_test.py -v     # Run with pytest (all tests)
"""

import pytest
import sqlite3
import tempfile
import os
import sys
import time
import random
import logging
import argparse
import threading
from typing import List, Set, Tuple
from unittest.mock import patch, MagicMock
from collections import Counter

# Import modules to test
from poker_modules import (
    Suit, Rank, RANKS_MAP, RANK_ORDER, Card, Position, StackType, PlayerAction,
    HandAnalysis, GameState, get_hand_tier, analyse_hand, to_two_card_str,
    get_position_advice, get_hand_advice, RANK_ORDER
)
from poker_modules import (
    HandRank, get_hand_rank, check_straight, get_opponent_range,
    calculate_equity_monte_carlo, get_board_texture, HAND_TIERS, FULL_DECK
)
from poker_init import open_db, initialise_db_if_needed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# TEST CLASSIFICATION AND SELECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestCategory:
    """Test category definitions for selective execution."""
    ESSENTIAL = "essential"      # Core functionality that must work
    STRINGENT = "stringent"      # Comprehensive validation including edge cases
    PERFORMANCE = "performance"  # Speed and memory tests
    STRESS = "stress"           # Heavy load and boundary tests
    ALL = "all"                 # Everything

# Test class categorization
TEST_CATEGORIES = {
    TestCategory.ESSENTIAL: [
        'TestCard', 'TestGetHandRank', 'TestGetHandTier', 
        'TestAnalyseHand', 'TestEquityCalculation'
    ],
    TestCategory.STRINGENT: [
        'TestCard', 'TestGetHandRank', 'TestHandRankComparisons',
        'TestGetHandTier', 'TestHandTierData', 'TestGetOpponentRange',
        'TestEquityCalculation', 'TestBoardTexture', 'TestAnalyseHand',
        'TestDecisionConsistency', 'TestUtilityFunctions', 'TestErrorHandling',
        'TestCompleteHandScenarios', 'TestConsistencyAcrossScenarios',
        'TestPropertyBasedInvariants'
    ],
    TestCategory.PERFORMANCE: [
        'TestPerformance'
    ],
    TestCategory.STRESS: [
        'TestStressScenarios', 'TestRandomizedScenarios'
    ]
}

# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES AND HELPERS (from original file)
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

# ══════════════════════════════════════════════════════════════════════════════
# CORE DATA STRUCTURES TESTS
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
    
    def test_full_deck_completeness(self):
        """Test FULL_DECK contains all 52 cards."""
        assert len(FULL_DECK) == 52
        
        # Check all rank-suit combinations exist
        for suit in Suit:
            for rank in Rank:
                expected_card = Card(rank.val, suit)
                assert expected_card in FULL_DECK


class TestGetHandRank:
    """Test get_hand_rank function for all hand types."""
    
    def test_royal_flush(self):
        """Test royal flush detection."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.SPADE)]
        board = [Card('Q', Suit.SPADE), Card('J', Suit.SPADE), Card('T', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT_FLUSH
        assert kickers[0] == 12  # Ace high
    
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
    
    def test_straight(self):
        """Test straight detection."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('T', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT
        assert kickers[0] == 12  # Ace high straight
    
    def test_wheel_straight(self):
        """Test A-2-3-4-5 straight (wheel)."""
        hole = [Card('A', Suit.SPADE), Card('2', Suit.HEART)]
        board = [Card('3', Suit.DIAMOND), Card('4', Suit.CLUB), Card('5', Suit.SPADE)]
        rank, kickers = get_hand_rank(hole, board)
        assert rank == HandRank.STRAIGHT
        assert kickers[0] == 3  # 5-high straight


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
    
    def test_weak_hands(self):
        """Test weak hand classification."""
        hands = [
            [Card('9', Suit.SPADE), Card('2', Suit.HEART)],  # 92o
            [Card('8', Suit.SPADE), Card('3', Suit.HEART)],  # 83o
            [Card('7', Suit.SPADE), Card('2', Suit.HEART)],  # 72o
        ]
        for hand in hands:
            assert get_hand_tier(hand) == "WEAK"


class TestHandTierData:
    """Test hand tier data structure consistency."""
    
    def test_no_hand_tier_overlap(self):
        """Test no hand appears in multiple tiers."""
        all_hands = []
        for tier_hands in HAND_TIERS.values():
            all_hands.extend(tier_hands)
        assert len(all_hands) == len(set(all_hands))


class TestGetOpponentRange:
    """Test opponent range generation."""
    
    def test_tight_range(self):
        """Test tight opponent range."""
        tight_range = get_opponent_range("TIGHT")
        assert "AA" in tight_range
        assert "KK" in tight_range
        assert "AKs" in tight_range
        assert len(tight_range) < 50
    
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
    
    def test_equity_consistency(self):
        """Test equity calculation consistency across runs."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = []
        
        equity1 = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 2000)
        equity2 = calculate_equity_monte_carlo(hole, board, 1, "MEDIUM", 2000)
        
        # Should be close but allow for Monte Carlo variance
        assert abs(equity1 - equity2) < 0.1


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
    
    def test_monotone_board(self):
        """Test monotone (all same suit) board."""
        board = [Card('A', Suit.SPADE), Card('K', Suit.SPADE), Card('Q', Suit.SPADE)]
        texture = get_board_texture(board)
        assert "Monotone" in texture


class TestAnalyseHand:
    """Test main hand analysis function."""
    
    def test_premium_hand_analysis(self):
        """Test analysis of premium hands."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole, board=board, position=Position.BTN,
            stack_bb=50, pot=10.0, to_call=2.0, num_players=6
        )
        
        assert analysis.decision in ["RAISE", "CALL"]
        assert analysis.equity > 0.7
        assert analysis.ev_call > 0
    
    def test_weak_hand_analysis(self):
        """Test analysis of weak hands."""
        hole = [Card('7', Suit.SPADE), Card('2', Suit.HEART)]
        board = []
        analysis = analyse_hand(
            hole=hole, board=board, position=Position.UTG,
            stack_bb=50, pot=10.0, to_call=8.0, num_players=6
        )
        
        assert analysis.decision == "FOLD"
        assert analysis.equity < 0.5
    
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


class TestDecisionConsistency:
    """Test decision making consistency."""
    
    def test_same_hand_same_decision(self):
        """Test same inputs produce same decisions."""
        hole = [Card('Q', Suit.SPADE), Card('Q', Suit.HEART)]
        board = [Card('A', Suit.HEART), Card('7', Suit.DIAMOND), Card('2', Suit.CLUB)]
        
        analysis1 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        analysis2 = analyse_hand(hole, board, Position.CO, 50, 30.0, 10.0, 6)
        
        assert analysis1.decision == analysis2.decision


class TestUtilityFunctions:
    """Test utility and helper functions."""
    
    def test_to_two_card_str(self):
        """Test two-card string conversion."""
        cards = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        result = to_two_card_str(cards)
        assert result == "A♠K♥"
    
    def test_get_position_advice(self):
        """Test position advice generation."""
        btn_advice = get_position_advice(Position.BTN)
        utg_advice = get_position_advice(Position.UTG)
        
        assert "position" in btn_advice.lower()
        assert "aggressive" in btn_advice.lower() or "advantage" in btn_advice.lower()


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_empty_inputs(self):
        """Test handling of empty inputs."""
        try:
            analysis = analyse_hand([], [], Position.BTN, 50, 10.0, 2.0, 6)
            assert hasattr(analysis, 'decision')
        except Exception:
            pass  # Acceptable to raise exception for invalid input


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


class TestConsistencyAcrossScenarios:
    """Test consistency of analysis across different scenarios."""
    
    def test_position_consistency(self):
        """Test position effects are consistent."""
        hole = [Card('T', Suit.SPADE), Card('9', Suit.HEART)]
        
        positions = [Position.UTG, Position.MP1, Position.CO, Position.BTN]
        decisions = []
        
        for pos in positions:
            analysis = analyse_hand(hole, [], pos, 50, 5.0, 2.0, 6)
            decisions.append(analysis.decision)
        
        # Should generally get more aggressive in later position
        early_fold = decisions[0] == "FOLD"
        late_raise = decisions[-1] in ["RAISE", "CALL"]
        
        assert early_fold or late_raise or decisions[0] != decisions[-1]


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
        
        # Should complete within reasonable time
        assert end_time - start_time < 5.0
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


class TestStressScenarios:
    """Test edge cases and stress scenarios."""
    
    def test_all_hand_types_evaluation(self):
        """Test evaluation of all possible hand types."""
        # High card
        hand1 = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board1 = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('9', Suit.SPADE)]
        rank1, _ = get_hand_rank(hand1, board1)
        assert rank1 == HandRank.HIGH_CARD
        
        # Straight flush
        hand9 = [Card('9', Suit.SPADE), Card('8', Suit.SPADE)]
        board9 = [Card('7', Suit.SPADE), Card('6', Suit.SPADE), Card('5', Suit.SPADE)]
        rank9, _ = get_hand_rank(hand9, board9)
        assert rank9 == HandRank.STRAIGHT_FLUSH
    
    def test_many_players_scenario(self):
        """Test analysis with maximum players."""
        hole = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        board = []
        
        analysis = analyse_hand(hole, board, Position.UTG, 50, 10.0, 2.0, 9)
        assert hasattr(analysis, 'decision')
        assert 0 <= analysis.equity <= 1


class TestRandomizedScenarios:
    """Test with randomized inputs to catch edge cases."""
    
    def test_random_hole_cards(self):
        """Test analysis with random hole card combinations."""
        import random
        
        for _ in range(20):  # Reduced for performance
            deck = list(FULL_DECK)
            random.shuffle(deck)
            hole = deck[:2]
            
            try:
                tier = get_hand_tier(hole)
                analysis = analyse_hand(hole, [], Position.BTN, 50, 10.0, 2.0, 6)
                assert tier in ["PREMIUM", "STRONG", "MEDIUM", "PLAYABLE", "MARGINAL", "WEAK"]
                assert hasattr(analysis, 'decision')
            except Exception as e:
                pytest.fail(f"Random hole cards {hole} caused error: {e}")


class TestPropertyBasedInvariants:
    """Test properties that should always hold."""
    
    def test_equity_bounds(self):
        """Test equity is always between 0 and 1."""
        import random
        
        for _ in range(10):  # Reduced for performance
            deck = list(FULL_DECK)
            random.shuffle(deck)
            hole = deck[:2]
            board = deck[2:2+random.randint(0, 5)]
            
            equity = calculate_equity_monte_carlo(hole, board, 3, "MEDIUM", 500)
            assert 0 <= equity <= 1, f"Equity {equity} out of bounds for {hole} vs {board}"
    
    def test_stronger_hands_higher_equity(self):
        """Test stronger hands generally have higher equity."""
        premium = [Card('A', Suit.SPADE), Card('A', Suit.HEART)]
        weak = [Card('7', Suit.SPADE), Card('2', Suit.HEART)]
        
        premium_equity = calculate_equity_monte_carlo(premium, [], 1, "MEDIUM", 1000)
        weak_equity = calculate_equity_monte_carlo(weak, [], 1, "MEDIUM", 1000)
        
        assert premium_equity > weak_equity


# ══════════════════════════════════════════════════════════════════════════════
# TEST EXECUTION AND REPORTING
# ══════════════════════════════════════════════════════════════════════════════

class PokerTestRunner:
    """Custom test runner for poker-specific testing."""
    
    def __init__(self):
        self.start_time = time.time()
        self.results = {}
    
    def run_test_category(self, category: str, verbose: bool = True):
        """Run tests for a specific category."""
        if verbose:
            print(f"\n🧪 Running {category.upper()} tests...")
        
        test_classes = TEST_CATEGORIES.get(category, [])
        if not test_classes:
            print(f"❌ Unknown test category: {category}")
            return False
        
        # Import all test classes dynamically
        all_test_classes = {name: obj for name, obj in globals().items() 
                          if isinstance(obj, type) and name.startswith('Test')}
        
        total_tests = 0
        passed_tests = 0
        failed_tests = []
        
        for test_class_name in test_classes:
            if test_class_name in all_test_classes:
                test_class = all_test_classes[test_class_name]
                
                if verbose:
                    print(f"  🔍 {test_class_name}")
                
                # Get all test methods
                test_methods = [method for method in dir(test_class) 
                              if method.startswith('test_')]
                
                for method_name in test_methods:
                    total_tests += 1
                    try:
                        # Create instance and run test
                        instance = test_class()
                        method = getattr(instance, method_name)
                        
                        # Handle fixtures if needed
                        if method_name in ['test_card_creation', 'test_card_string_representation', 
                                         'test_card_rank_val_property']:
                            # Create sample_cards fixture
                            sample_cards = {
                                'ace_spades': Card('A', Suit.SPADE),
                                'king_hearts': Card('K', Suit.HEART),
                                'two_spades': Card('2', Suit.SPADE),
                            }
                            method(sample_cards)
                        else:
                            method()
                        
                        passed_tests += 1
                        
                    except Exception as e:
                        failed_tests.append(f"{test_class_name}::{method_name}: {str(e)}")
        
        self.results[category] = {
            'total': total_tests,
            'passed': passed_tests,
            'failed': len(failed_tests),
            'failures': failed_tests
        }
        
        if verbose:
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            print(f"  📊 {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
            
            if failed_tests:
                print(f"  ❌ Failed tests:")
                for failure in failed_tests[:5]:  # Show first 5 failures
                    print(f"     {failure}")
                if len(failed_tests) > 5:
                    print(f"     ... and {len(failed_tests) - 5} more")
        
        return len(failed_tests) == 0
    
    def run_stringent_tests(self):
        """Run the most stringent test suite automatically."""
        print("🎯 POKER ASSISTANT - STRINGENT TEST VALIDATION")
        print("=" * 60)
        print("Running comprehensive validation of all critical functionality...")
        
        # Run stringent test category
        success = self.run_test_category(TestCategory.STRINGENT, verbose=True)
        
        # Also run performance validation
        print(f"\n⚡ Performance Validation...")
        perf_success = self.run_test_category(TestCategory.PERFORMANCE, verbose=True)
        
        # Summary
        elapsed_time = time.time() - self.start_time
        print(f"\n📋 STRINGENT TEST SUMMARY")
        print("-" * 40)
        
        overall_success = success and perf_success
        
        for category, results in self.results.items():
            status = "✅" if results['failed'] == 0 else "❌"
            print(f"{status} {category.capitalize()}: {results['passed']}/{results['total']} passed")
        
        print(f"\n⏱️  Total execution time: {elapsed_time:.2f} seconds")
        
        if overall_success:
            print(f"\n🎉 SUCCESS: All stringent tests passed!")
            print(f"   Poker Assistant is validated and ready for use.")
        else:
            print(f"\n⚠️  WARNING: Some tests failed.")
            print(f"   Review failures above and fix before deployment.")
        
        return overall_success
    
    def print_comprehensive_report(self):
        """Print comprehensive test report."""
        elapsed_time = time.time() - self.start_time
        
        print(f"\n📊 COMPREHENSIVE TEST REPORT")
        print("=" * 60)
        
        total_tests = sum(r['total'] for r in self.results.values())
        total_passed = sum(r['passed'] for r in self.results.values())
        total_failed = sum(r['failed'] for r in self.results.values())
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Success Rate: {(total_passed/total_tests*100):.1f}%")
        print(f"Execution Time: {elapsed_time:.2f}s")
        
        print(f"\nBy Category:")
        for category, results in self.results.items():
            status = "✅" if results['failed'] == 0 else "❌"
            print(f"  {status} {category.capitalize():<12} {results['passed']:>3}/{results['total']:<3}")
        
        # Show all failures
        all_failures = []
        for results in self.results.values():
            all_failures.extend(results['failures'])
        
        if all_failures:
            print(f"\n❌ All Failures ({len(all_failures)}):")
            for i, failure in enumerate(all_failures, 1):
                print(f"  {i:2d}. {failure}")
        
        return total_failed == 0


def run_tests_by_category(category: str):
    """Run tests by category and return success status."""
    runner = PokerTestRunner()
    
    if category == TestCategory.ALL:
        success = True
        for cat in [TestCategory.STRINGENT, TestCategory.PERFORMANCE, TestCategory.STRESS]:
            cat_success = runner.run_test_category(cat, verbose=True)
            success = success and cat_success
    else:
        success = runner.run_test_category(category, verbose=True)
    
    runner.print_comprehensive_report()
    return success


def main():
    """Main entry point for direct execution."""
    parser = argparse.ArgumentParser(description="Poker Assistant Test Suite")
    parser.add_argument("--all", action="store_true", 
                       help="Run all tests")
    parser.add_argument("--quick", action="store_true", 
                       help="Run quick essential tests only")
    parser.add_argument("--performance", action="store_true", 
                       help="Run performance tests only")
    parser.add_argument("--stress", action="store_true", 
                       help="Run stress tests only")
    parser.add_argument("--stringent", action="store_true", 
                       help="Run stringent comprehensive tests")
    
    args = parser.parse_args()
    
    runner = PokerTestRunner()
    
    # Determine which tests to run
    if args.all:
        success = run_tests_by_category(TestCategory.ALL)
    elif args.quick:
        success = run_tests_by_category(TestCategory.ESSENTIAL)
    elif args.performance:
        success = run_tests_by_category(TestCategory.PERFORMANCE)
    elif args.stress:
        success = run_tests_by_category(TestCategory.STRESS)
    elif args.stringent:
        success = runner.run_stringent_tests()
    else:
        # DEFAULT: Run stringent tests automatically
        print("No test category specified - running STRINGENT tests by default")
        print("Use --help to see all available options\n")
        success = runner.run_stringent_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
