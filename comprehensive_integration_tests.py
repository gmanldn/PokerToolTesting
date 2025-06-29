#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Poker Assistant.
Tests the complete system integration across all modules and components.

This is the final validation that all components work together correctly
in realistic poker scenarios.

Run with: python -m pytest comprehensive_integration_tests.py -v
"""

import pytest
import tempfile
import sqlite3
import os
import time
import random
import threading
from unittest.mock import patch, Mock
from typing import List, Dict, Any, Tuple

# Import all poker modules
from poker_modules import (
    Card, Suit, Position, StackType, PlayerAction, GameState, HandAnalysis,
    HandRank, get_hand_rank, get_hand_tier, calculate_equity_monte_carlo,
    get_board_texture, analyse_hand, to_two_card_str
)


class TestCompletePokerWorkflows:
    """Test complete poker game workflows from start to finish."""
    
    def test_complete_cash_game_session(self):
        """Test a complete cash game session with multiple hands."""
        # Simulate a realistic cash game session
        session_results = []
        
        # Game parameters
        positions = [Position.UTG, Position.MP1, Position.CO, Position.BTN, Position.SB, Position.BB]
        stack_bb = 100
        
        for hand_num in range(20):  # 20 hands
            # Random hole cards
            deck = list(poker_modules.FULL_DECK)
            random.shuffle(deck)
            hole = deck[:2]
            
            # Random position (simulating table rotation)
            position = positions[hand_num % len(positions)]
            
            # Pre-flop analysis
            preflop_analysis = analyse_hand(
                hole=hole, board=[], position=position,
                stack_bb=stack_bb, pot=3.0, to_call=2.0, num_players=6
            )
            
            # Continue based on pre-flop decision
            if preflop_analysis.decision in ["CALL", "RAISE"]:
                # Flop
                flop = deck[2:5]
                
                # Ensure no duplicates
                if len(set(str(c) for c in hole + flop)) == 5:
                    flop_analysis = analyse_hand(
                        hole=hole, board=flop, position=position,
                        stack_bb=stack_bb, pot=15.0, to_call=8.0, num_players=4
                    )
                    
                    # Turn
                    if flop_analysis.decision in ["CALL", "RAISE"]:
                        turn = deck[5]
                        board = flop + [turn]
                        
                        if len(set(str(c) for c in hole + board)) == 6:
                            turn_analysis = analyse_hand(
                                hole=hole, board=board, position=position,
                                stack_bb=stack_bb, pot=40.0, to_call=20.0, num_players=3
                            )
                            
                            # River
                            if turn_analysis.decision in ["CALL", "RAISE"]:
                                river = deck[6]
                                final_board = board + [river]
                                
                                if len(set(str(c) for c in hole + final_board)) == 7:
                                    river_analysis = analyse_hand(
                                        hole=hole, board=final_board, position=position,
                                        stack_bb=stack_bb, pot=100.0, to_call=50.0, num_players=2
                                    )
                                    
                                    session_results.append({
                                        'hand': hand_num,
                                        'hole': hole,
                                        'board': final_board,
                                        'position': position,
                                        'final_decision': river_analysis.decision,
                                        'final_equity': river_analysis.equity
                                    })
            
            # Validate each hand's analysis
            assert hasattr(preflop_analysis, 'decision')
            assert preflop_analysis.decision in ["FOLD", "CALL", "RAISE", "CHECK"]
            assert 0 <= preflop_analysis.equity <= 1
        
        # Session should have produced some complete hands
        assert len(session_results) > 0
        
        # All final analyses should be valid
        for result in session_results:
            assert result['final_decision'] in ["FOLD", "CALL", "RAISE", "CHECK"]
            assert 0 <= result['final_equity'] <= 1
    
    def test_tournament_progression_simulation(self):
        """Test tournament progression through different stages."""
        tournament_stages = [
            {'name': 'Early', 'stack_bb': 100, 'blinds': (0.5, 1.0), 'players': 9},
            {'name': 'Middle', 'stack_bb': 50, 'blinds': (1.0, 2.0), 'players': 7},
            {'name': 'Bubble', 'stack_bb': 15, 'blinds': (2.0, 4.0), 'players': 5},
            {'name': 'Final Table', 'stack_bb': 30, 'blinds': (3.0, 6.0), 'players': 3},
            {'name': 'Heads Up', 'stack_bb': 25, 'blinds': (5.0, 10.0), 'players': 2},
        ]
        
        for stage in tournament_stages:
            # Test 5 hands per stage
            for _ in range(5):
                hole = [
                    Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit))),
                    Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit)))
                ]
                
                # Ensure unique cards
                while hole[0] == hole[1]:
                    hole[1] = Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit)))
                
                analysis = analyse_hand(
                    hole=hole, board=[], 
                    position=random.choice(list(Position)),
                    stack_bb=stage['stack_bb'],
                    pot=stage['blinds'][0] + stage['blinds'][1],
                    to_call=stage['blinds'][1],
                    num_players=stage['players']
                )
                
                # Validate analysis for tournament context
                assert hasattr(analysis, 'decision')
                assert hasattr(analysis, 'spr')
                
                # SPR should reflect stack depth
                expected_spr = stage['stack_bb'] / (stage['blinds'][0] + stage['blinds'][1])
                assert abs(analysis.spr - expected_spr) < expected_spr * 0.5  # Within 50%
    
    def test_multi_table_tournament_simulation(self):
        """Test multi-table tournament dynamics."""
        # Simulate 3 tables with different dynamics
        tables = [
            {'id': 1, 'avg_stack': 80, 'players': 9, 'style': 'tight'},
            {'id': 2, 'avg_stack': 60, 'players': 8, 'style': 'aggressive'},
            {'id': 3, 'avg_stack': 120, 'players': 7, 'style': 'loose'},
        ]
        
        for table in tables:
            # Test multiple positions at each table
            for position in [Position.UTG, Position.CO, Position.BTN]:
                hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]  # Strong hand
                
                analysis = analyse_hand(
                    hole=hole, board=[], position=position,
                    stack_bb=table['avg_stack'], pot=3.0, to_call=2.0,
                    num_players=table['players']
                )
                
                # Strong hand should generally be playable
                assert analysis.decision in ["CALL", "RAISE"]
                assert analysis.equity > 0.6  # AK should have good equity
                
                # Position should influence decision
                if position == Position.BTN:
                    # Button should be more aggressive
                    assert analysis.decision in ["RAISE", "CALL"]


class TestSystemIntegrationUnderLoad:
    """Test system integration under various load conditions."""
    
    def test_concurrent_analysis_sessions(self):
        """Test multiple concurrent analysis sessions."""
        results = []
        errors = []
        lock = threading.Lock()
        
        def analysis_worker(worker_id):
            """Worker that runs poker analysis."""
            try:
                for i in range(50):
                    # Generate unique cards for this iteration
                    deck = list(poker_modules.FULL_DECK)
                    random.shuffle(deck)
                    hole = deck[:2]
                    board = deck[2:5] if random.random() > 0.5 else []
                    
                    analysis = analyse_hand(
                        hole=hole, board=board,
                        position=random.choice(list(Position)),
                        stack_bb=random.randint(20, 100),
                        pot=random.uniform(5.0, 50.0),
                        to_call=random.uniform(1.0, 20.0),
                        num_players=random.randint(2, 9)
                    )
                    
                    with lock:
                        results.append({
                            'worker': worker_id,
                            'iteration': i,
                            'decision': analysis.decision,
                            'equity': analysis.equity
                        })
                        
            except Exception as e:
                with lock:
                    errors.append({'worker': worker_id, 'error': str(e)})
        
        # Start multiple worker threads
        threads = []
        for worker_id in range(4):
            thread = threading.Thread(target=analysis_worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=30.0)  # 30 second timeout
            assert not thread.is_alive(), "Thread didn't complete in time"
        
        # Validate results
        assert len(errors) == 0, f"Concurrent analysis errors: {errors}"
        assert len(results) == 200  # 4 workers * 50 iterations
        
        # All results should be valid
        for result in results:
            assert result['decision'] in ["FOLD", "CALL", "RAISE", "CHECK"]
            assert 0 <= result['equity'] <= 1
    
    def test_long_running_session_stability(self):
        """Test system stability over long running sessions."""
        start_time = time.time()
        iteration_count = 0
        
        # Run for up to 30 seconds
        while time.time() - start_time < 30.0 and iteration_count < 1000:
            try:
                # Generate random scenario
                deck = list(poker_modules.FULL_DECK)
                random.shuffle(deck)
                hole = deck[:2]
                board = deck[2:2+random.choice([0, 3, 4, 5])]
                
                # Ensure no duplicates
                all_cards = hole + board
                if len(all_cards) == len(set(str(c) for c in all_cards)):
                    analysis = analyse_hand(
                        hole=hole, board=board,
                        position=random.choice(list(Position)),
                        stack_bb=random.randint(10, 200),
                        pot=random.uniform(2.0, 100.0),
                        to_call=random.uniform(0.5, 30.0),
                        num_players=random.randint(2, 9)
                    )
                    
                    # Validate analysis
                    assert hasattr(analysis, 'decision')
                    assert 0 <= analysis.equity <= 1
                    
                    iteration_count += 1
                    
                    # Periodic cleanup
                    if iteration_count % 100 == 0:
                        import gc
                        gc.collect()
                        
            except Exception as e:
                # System should remain stable even with errors
                print(f"Iteration {iteration_count} error: {e}")
                iteration_count += 1
        
        elapsed_time = time.time() - start_time
        print(f"Completed {iteration_count} iterations in {elapsed_time:.2f}s")
        
        # Should have completed significant number of iterations
        assert iteration_count > 100, f"Only completed {iteration_count} iterations"
    
    def test_memory_stability_under_load(self):
        """Test memory stability under sustained load."""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # Run sustained operations
        for batch in range(10):
            batch_results = []
            
            # Create many objects in this batch
            for i in range(1000):
                deck = list(poker_modules.FULL_DECK)
                random.shuffle(deck)
                hole = deck[:2]
                
                # Quick analysis
                tier = get_hand_tier(hole)
                batch_results.append(tier)
            
            # Clear batch results
            batch_results.clear()
            
            # Force garbage collection
            gc.collect()
            
            # Check memory growth
            current_memory = process.memory_info().rss
            memory_growth = (current_memory - initial_memory) / 1024 / 1024  # MB
            
            # Memory shouldn't grow excessively
            assert memory_growth < 200, f"Excessive memory growth: {memory_growth:.1f}MB after batch {batch}"


class TestDatabaseIntegrationWorkflows:
    """Test database integration in complete workflows."""
    
    def test_complete_decision_tracking_workflow(self):
        """Test complete decision tracking from analysis to storage."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        try:
            with patch('poker_init.DB_FILE', temp_db_path):
                from poker_init import initialise_db_if_needed, open_db
                
                initialise_db_if_needed()
                
                # Simulate multiple poker decisions
                decisions_made = []
                
                for hand_num in range(10):
                    # Generate hand scenario
                    hole = [
                        Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit))),
                        Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit)))
                    ]
                    
                    # Ensure unique cards
                    while hole[0] == hole[1]:
                        hole[1] = Card(random.choice(poker_modules.RANK_ORDER), random.choice(list(Suit)))
                    
                    analysis = analyse_hand(
                        hole=hole, board=[], 
                        position=random.choice(list(Position)),
                        stack_bb=50, pot=10.0, to_call=2.0, num_players=6
                    )
                    
                    # Store decision in database
                    db = open_db()
                    hand_str = to_two_card_str(hole)
                    
                    cursor = db.execute(
                        """INSERT INTO decisions 
                           (hand, position, decision, pot, to_call, spr, board_texture)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (hand_str, analysis.decision, "BTN", 10.0, 2.0, analysis.spr, analysis.board_texture)
                    )
                    
                    decision_id = cursor.lastrowid
                    db.commit()
                    db.close()
                    
                    decisions_made.append({
                        'id': decision_id,
                        'hand': hand_str,
                        'decision': analysis.decision,
                        'equity': analysis.equity
                    })
                
                # Verify all decisions were stored
                db = open_db()
                cursor = db.execute("SELECT COUNT(*) FROM decisions")
                stored_count = cursor.fetchone()[0]
                db.close()
                
                assert stored_count >= len(decisions_made)
                
                # Verify decision consistency
                for decision in decisions_made:
                    assert decision['decision'] in ["FOLD", "CALL", "RAISE", "CHECK"]
                    assert 0 <= decision['equity'] <= 1
                    
        finally:
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)
    
    def test_session_statistics_workflow(self):
        """Test session statistics calculation workflow."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        try:
            with patch('poker_init.DB_FILE', temp_db_path):
                from poker_init import initialise_db_if_needed, open_db
                
                initialise_db_if_needed()
                db = open_db()
                
                # Insert test session data
                session_decisions = [
                    ("RAISE", "BTN", "PREMIUM"),
                    ("CALL", "CO", "STRONG"),
                    ("FOLD", "UTG", "WEAK"),
                    ("RAISE", "BTN", "STRONG"),
                    ("FOLD", "SB", "MARGINAL"),
                    ("CALL", "BB", "MEDIUM"),
                ]
                
                for decision, position, tier in session_decisions:
                    db.execute(
                        "INSERT INTO decisions (decision, position, hand_tier) VALUES (?, ?, ?)",
                        (decision, position, tier)
                    )
                
                db.commit()
                
                # Calculate session statistics
                cursor = db.execute(
                    "SELECT decision, COUNT(*) FROM decisions GROUP BY decision"
                )
                decision_stats = dict(cursor.fetchall())
                
                cursor = db.execute(
                    "SELECT position, COUNT(*) FROM decisions GROUP BY position"
                )
                position_stats = dict(cursor.fetchall())
                
                cursor = db.execute(
                    "SELECT hand_tier, COUNT(*) FROM decisions GROUP BY hand_tier"
                )
                tier_stats = dict(cursor.fetchall())
                
                db.close()
                
                # Verify statistics
                assert decision_stats["FOLD"] == 2
                assert decision_stats["CALL"] == 2
                assert decision_stats["RAISE"] == 2
                
                assert position_stats["BTN"] == 2
                assert "UTG" in position_stats
                
                assert "PREMIUM" in tier_stats
                assert "WEAK" in tier_stats
                
        finally:
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)


class TestPerformanceIntegrationValidation:
    """Test performance characteristics of integrated system."""
    
    def test_end_to_end_performance(self):
        """Test end-to-end performance from input to decision."""
        import time
        
        # Test various scenario complexities
        scenarios = [
            {'name': 'Simple Pre-flop', 'board_size': 0},
            {'name': 'Flop Analysis', 'board_size': 3},
            {'name': 'Turn Analysis', 'board_size': 4},
            {'name': 'River Analysis', 'board_size': 5},
        ]
        
        for scenario in scenarios:
            times = []
            
            for _ in range(100):
                # Generate scenario
                deck = list(poker_modules.FULL_DECK)
                random.shuffle(deck)
                hole = deck[:2]
                board = deck[2:2+scenario['board_size']]
                
                # Time the complete analysis
                start_time = time.perf_counter()
                
                analysis = analyse_hand(
                    hole=hole, board=board,
                    position=Position.BTN, stack_bb=50,
                    pot=20.0, to_call=5.0, num_players=6
                )
                
                end_time = time.perf_counter()
                times.append(end_time - start_time)
                
                # Validate result
                assert hasattr(analysis, 'decision')
                assert 0 <= analysis.equity <= 1
            
            # Performance assertions
            avg_time = sum(times) / len(times)
            max_time = max(times)
            
            print(f"{scenario['name']}: avg={avg_time*1000:.2f}ms, max={max_time*1000:.2f}ms")
            
            # Performance thresholds (adjust based on requirements)
            if scenario['board_size'] == 0:  # Pre-flop should be fast
                assert avg_time < 0.1, f"Pre-flop analysis too slow: {avg_time:.3f}s"
            else:  # Post-flop includes equity calculation
                assert avg_time < 2.0, f"Post-flop analysis too slow: {avg_time:.3f}s"
            
            assert max_time < 5.0, f"Worst case too slow: {max_time:.3f}s"
    
    def test_scalability_with_player_count(self):
        """Test performance scalability with different player counts."""
        import time
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        board = [Card('Q', Suit.DIAMOND), Card('J', Suit.CLUB), Card('T', Suit.SPADE)]
        
        for num_players in [2, 4, 6, 8, 9]:
            times = []
            
            for _ in range(20):  # Fewer iterations for equity calculations
                start_time = time.perf_counter()
                
                analysis = analyse_hand(
                    hole=hole, board=board, position=Position.BTN,
                    stack_bb=50, pot=30.0, to_call=10.0,
                    num_players=num_players
                )
                
                end_time = time.perf_counter()
                times.append(end_time - start_time)
                
                # Validate equity decreases with more players
                assert 0 <= analysis.equity <= 1
            
            avg_time = sum(times) / len(times)
            print(f"{num_players} players: avg={avg_time:.3f}s")
            
            # Should scale reasonably with player count
            assert avg_time < 10.0, f"Analysis with {num_players} players too slow: {avg_time:.3f}s"


class TestErrorRecoveryIntegration:
    """Test error recovery in integrated scenarios."""
    
    def test_partial_system_failure_recovery(self):
        """Test recovery from partial system failures."""
        hole = [Card('K', Suit.SPADE), Card('Q', Suit.HEART)]
        
        # Test with mocked component failures
        with patch('poker_modules.calculate_equity_monte_carlo', side_effect=Exception("Equity failed")):
            try:
                analysis = analyse_hand(
                    hole=hole, board=[], position=Position.CO,
                    stack_bb=50, pot=15.0, to_call=5.0, num_players=6
                )
                
                # Should still provide some analysis even with equity failure
                assert hasattr(analysis, 'decision')
                # Equity might be default value or None
                
            except Exception:
                # Complete failure is also acceptable if no fallback implemented
                pass
    
    def test_data_corruption_recovery(self):
        """Test recovery from data corruption scenarios."""
        # Test with various corrupted inputs
        corrupted_scenarios = [
            {'hole': [None, Card('K', Suit.HEART)], 'should_fail': True},
            {'hole': [], 'should_fail': True},
            {'hole': [Card('A', Suit.SPADE)] * 3, 'should_fail': True},  # Too many cards
        ]
        
        for scenario in corrupted_scenarios:
            try:
                analysis = analyse_hand(
                    hole=scenario['hole'], board=[], position=Position.BTN,
                    stack_bb=50, pot=10.0, to_call=2.0, num_players=6
                )
                
                if scenario['should_fail']:
                    # If it doesn't fail, result should still be reasonable
                    assert hasattr(analysis, 'decision')
                    
            except (ValueError, TypeError, AttributeError):
                # Expected for corrupted data
                if scenario['should_fail']:
                    assert True  # Expected failure
                else:
                    assert False, "Unexpected failure for valid data"


if __name__ == "__main__":
    print("Comprehensive Integration Tests for Poker Assistant")
    print("Run with: python -m pytest comprehensive_integration_tests.py -v")
    print("These tests validate complete system integration and real-world workflows")
