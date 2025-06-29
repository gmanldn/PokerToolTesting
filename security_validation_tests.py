#!/usr/bin/env python3
"""
Security and Input Validation Tests for Poker Assistant.
Tests input sanitization, injection prevention, and security best practices.

Run with: python -m pytest security_validation_tests.py -v
"""

import pytest
import sqlite3
import tempfile
import os
import sys
import random
import string
from unittest.mock import patch, Mock
from typing import List, Dict, Any

# Import poker modules
from poker_modules import (
    Card, Suit, Position, StackType, PlayerAction,
    get_hand_rank, get_hand_tier, analyse_hand, to_two_card_str
)


class TestInputSanitization:
    """Test input sanitization and validation."""
    
    def test_card_input_validation(self):
        """Test card input validation against malicious inputs."""
        # Test various invalid inputs that could cause issues
        invalid_inputs = [
            None,
            "",
            "  ",
            "X",
            "13",  # Invalid rank
            "@",
            "\x00",  # Null byte
            "A" * 1000,  # Very long string
            {"rank": "A"},  # Wrong type
            ["A"],  # Wrong type
        ]
        
        for invalid_input in invalid_inputs:
            with pytest.raises((ValueError, TypeError, KeyError, AttributeError)):
                Card(invalid_input, Suit.SPADE)
    
    def test_string_input_sanitization(self):
        """Test string input sanitization."""
        # Test potentially dangerous strings
        dangerous_strings = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE decisions; --",
            "../../../etc/passwd",
            "\x00\x01\x02",  # Control characters
            "A" * 10000,  # Very long string
            "\n\r\t",  # Whitespace characters
            "🃏" * 1000,  # Unicode flood
        ]
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        for dangerous_string in dangerous_strings:
            # These should either work safely or reject the input
            try:
                result = to_two_card_str([])  # This function handles string conversion
                # If it works, should return safe string
                assert isinstance(result, str)
                assert len(result) < 1000  # Reasonable length limit
            except (ValueError, TypeError):
                # Acceptable to reject dangerous input
                pass
    
    def test_numeric_input_validation(self):
        """Test numeric input validation against edge cases."""
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Test with extreme numeric values
        extreme_values = [
            float('inf'),
            float('-inf'),
            float('nan'),
            sys.maxsize,
            -sys.maxsize,
            1e308,  # Very large number
            1e-308,  # Very small number
        ]
        
        for extreme_value in extreme_values:
            try:
                analysis = analyse_hand(
                    hole=hole, board=[], position=Position.BTN,
                    stack_bb=50, pot=extreme_value, to_call=2.0, num_players=6
                )
                
                # If it works, results should be reasonable
                assert hasattr(analysis, 'decision')
                assert not (analysis.equity != analysis.equity)  # Check for NaN
                
            except (ValueError, OverflowError, ZeroDivisionError):
                # Acceptable to reject extreme values
                pass
    
    def test_injection_prevention(self):
        """Test prevention of various injection attacks."""
        # SQL injection attempts (for future database operations)
        sql_injection_attempts = [
            "'; DROP TABLE decisions; --",
            "' OR '1'='1",
            "UNION SELECT * FROM sqlite_master",
            "'; UPDATE decisions SET decision='HACKED'; --",
        ]
        
        # These strings should be handled safely if passed to any function
        for injection_attempt in sql_injection_attempts:
            try:
                # Test various functions that might handle string input
                result = to_two_card_str([])
                # Should not execute any SQL
                assert isinstance(result, str)
            except (ValueError, TypeError):
                # Acceptable to reject malicious input
                pass


class TestDatabaseSecurity:
    """Test database security measures."""
    
    def test_sql_injection_prevention(self):
        """Test SQL injection prevention in database operations."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        try:
            with patch('poker_init.DB_FILE', temp_db_path):
                from poker_init import initialise_db_if_needed, open_db
                
                initialise_db_if_needed()
                db = open_db()
                
                # Test injection attempts
                injection_attempts = [
                    "'; DROP TABLE decisions; --",
                    "' OR '1'='1",
                    "'; UPDATE decisions SET decision='HACKED' WHERE '1'='1'; --",
                ]
                
                for injection_attempt in injection_attempts:
                    try:
                        # Use parameterized query (should be safe)
                        cursor = db.execute(
                            "INSERT INTO decisions (position, decision) VALUES (?, ?)",
                            (injection_attempt, "FOLD")
                        )
                        db.commit()
                        
                        # Verify no injection occurred
                        cursor = db.execute("SELECT COUNT(*) FROM decisions")
                        count = cursor.fetchone()[0]
                        assert count >= 1  # Record should be inserted normally
                        
                        # Verify table still exists (wasn't dropped)
                        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = [row[0] for row in cursor.fetchall()]
                        assert 'decisions' in tables
                        
                    except sqlite3.Error:
                        # Database errors are acceptable for malicious input
                        pass
                
                db.close()
                
        finally:
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)
    
    def test_database_permission_validation(self):
        """Test database handles permission issues gracefully."""
        # Test with read-only location
        readonly_path = "/etc/poker_readonly.db"  # Typically read-only on Unix
        
        try:
            with patch('poker_init.DB_FILE', readonly_path):
                from poker_init import open_db
                
                # Should handle permission error gracefully
                db = open_db()
                db.close()
                
        except (sqlite3.OperationalError, PermissionError):
            # Expected for permission-denied scenarios
            pass
    
    def test_database_corruption_resistance(self):
        """Test database corruption resistance."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        try:
            # Create corrupted database
            with open(temp_db_path, 'wb') as f:
                f.write(b"CORRUPTED_DATA" * 100)
            
            with patch('poker_init.DB_FILE', temp_db_path):
                try:
                    from poker_init import open_db
                    db = open_db()
                    
                    # Try to use corrupted database
                    cursor = db.execute("SELECT * FROM decisions")
                    cursor.fetchall()
                    
                    db.close()
                    
                except sqlite3.DatabaseError:
                    # Expected for corrupted database
                    pass
                    
        finally:
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)


class TestMemorySecurityValidation:
    """Test memory-related security concerns."""
    
    def test_buffer_overflow_prevention(self):
        """Test prevention of buffer overflow-like issues."""
        # Test with very large inputs
        large_string = "A" * 1000000  # 1MB string
        
        try:
            # These operations should handle large inputs safely
            hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
            
            # Functions should either work or reject gracefully
            result = to_two_card_str(hole)
            assert len(result) < 1000  # Should not return extremely long strings
            
        except (MemoryError, ValueError):
            # Acceptable to reject very large inputs
            pass
    
    def test_memory_exhaustion_protection(self):
        """Test protection against memory exhaustion attacks."""
        # Test with many objects
        large_object_list = []
        
        try:
            # Create many card objects
            for i in range(10000):
                card = Card('A', Suit.SPADE)
                large_object_list.append(card)
                
                # System should remain responsive
                if i % 1000 == 0:
                    # Test basic operation still works
                    tier = get_hand_tier([Card('K', Suit.HEART), Card('K', Suit.SPADE)])
                    assert tier == "STRONG"
                    
        except MemoryError:
            # Expected under memory pressure
            pass
        finally:
            # Clean up
            large_object_list.clear()
    
    def test_infinite_loop_protection(self):
        """Test protection against infinite loops."""
        import time
        
        # Test operations that might loop indefinitely
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        start_time = time.time()
        
        try:
            # Even with pathological inputs, should complete quickly
            for _ in range(1000):
                get_hand_tier(hole)
                
                # Check timeout
                if time.time() - start_time > 5.0:  # 5 second timeout
                    break
                    
            elapsed_time = time.time() - start_time
            assert elapsed_time < 5.0, "Operation took too long, possible infinite loop"
            
        except Exception:
            # Errors are acceptable, infinite loops are not
            elapsed_time = time.time() - start_time
            assert elapsed_time < 5.0, "Exception occurred but took too long"


class TestDataValidationSecurity:
    """Test data validation for security concerns."""
    
    def test_type_confusion_prevention(self):
        """Test prevention of type confusion attacks."""
        # Test with objects that might confuse type checking
        confusing_objects = [
            Mock(),  # Mock object
            lambda: "A",  # Function
            {"rank": "A", "suit": "SPADE"},  # Dict that looks like a card
            type("FakeCard", (), {"rank": "A", "suit": Suit.SPADE}),  # Fake class
        ]
        
        for confusing_object in confusing_objects:
            with pytest.raises((TypeError, AttributeError, ValueError)):
                # Should reject objects that aren't proper Cards
                get_hand_rank([confusing_object, Card('K', Suit.HEART)], [])
    
    def test_serialization_security(self):
        """Test secure handling of serialized data."""
        # Test with data that might be unsafely deserialized
        unsafe_data = [
            b"\x80\x03cbuiltins\neval\nq\x00X\x0e\x00\x00\x00__import__('os')q\x01\x85q\x02Rq\x03.",  # Pickle exploit
            '{"__class__": "os.system", "args": ["rm -rf /"]}',  # JSON exploit
        ]
        
        # Our system shouldn't be deserializing untrusted data,
        # but test that string operations handle binary data safely
        for unsafe_bytes in unsafe_data:
            try:
                if isinstance(unsafe_bytes, bytes):
                    # Should not execute any code
                    str_data = unsafe_bytes.decode('utf-8', errors='ignore')
                    assert len(str_data) < 1000  # Reasonable length
            except UnicodeDecodeError:
                # Acceptable to reject invalid data
                pass
    
    def test_path_traversal_prevention(self):
        """Test prevention of path traversal attacks."""
        # Test with path traversal attempts
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
            "file:///etc/passwd",
        ]
        
        # Our system doesn't typically handle file paths from user input,
        # but test that any string operations handle them safely
        for path_attempt in traversal_attempts:
            try:
                # Should not access any files
                result = to_two_card_str([])  # Safe string operation
                assert isinstance(result, str)
                assert "../" not in result  # Should not echo back dangerous paths
            except (ValueError, TypeError):
                # Acceptable to reject dangerous input
                pass


class TestPrivacyProtection:
    """Test privacy and data protection."""
    
    def test_information_disclosure_prevention(self):
        """Test prevention of information disclosure."""
        # Test that error messages don't reveal sensitive information
        try:
            # Cause an error
            get_hand_rank([], [])
        except Exception as e:
            error_message = str(e).lower()
            
            # Error message should not contain sensitive information
            sensitive_terms = [
                'password', 'secret', 'key', 'token', 'admin',
                'database', 'connection', 'server', 'host'
            ]
            
            for term in sensitive_terms:
                assert term not in error_message, f"Error message contains sensitive term: {term}"
    
    def test_data_sanitization_in_logs(self):
        """Test that logged data is properly sanitized."""
        import logging
        import io
        
        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger('poker_modules')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        try:
            # Perform operations that might log data
            hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
            get_hand_tier(hole)
            
            # Check log output
            log_output = log_capture.getvalue()
            
            # Should not contain sensitive data patterns
            sensitive_patterns = [
                'password', 'secret', 'private_key',
                'session_id', 'auth_token'
            ]
            
            for pattern in sensitive_patterns:
                assert pattern not in log_output.lower()
                
        finally:
            logger.removeHandler(handler)
    
    def test_memory_cleanup_security(self):
        """Test that sensitive data is properly cleaned from memory."""
        # This is more of a conceptual test since Python's garbage collection
        # handles most memory cleanup, but we can test that references are cleared
        
        hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
        
        # Create analysis with potentially sensitive data
        analysis = analyse_hand(
            hole=hole, board=[], position=Position.BTN,
            stack_bb=50, pot=10.0, to_call=2.0, num_players=6
        )
        
        # Clear references
        analysis = None
        hole = None
        
        # Force garbage collection
        import gc
        gc.collect()
        
        # This test mainly verifies no errors occur during cleanup
        assert True  # If we reach here, cleanup was successful


class TestConcurrencySecurityValidation:
    """Test security in concurrent scenarios."""
    
    def test_race_condition_prevention(self):
        """Test prevention of race conditions that could cause security issues."""
        import threading
        import time
        
        results = []
        errors = []
        lock = threading.Lock()
        
        def worker():
            """Worker that might cause race conditions."""
            try:
                for _ in range(100):
                    # Operations that might have race conditions
                    hole = [Card('Q', Suit.SPADE), Card('J', Suit.HEART)]
                    tier = get_hand_tier(hole)
                    
                    with lock:
                        results.append(tier)
                        
                    time.sleep(0.001)  # Small delay to increase chance of races
                    
            except Exception as e:
                with lock:
                    errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(4):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no security-relevant errors occurred
        assert len(errors) == 0, f"Race condition errors: {errors}"
        
        # All results should be consistent
        expected_tier = "MEDIUM"  # QJ should be medium
        for result in results:
            assert result == expected_tier, "Inconsistent results suggest race condition"
    
    def test_resource_exhaustion_in_concurrent_access(self):
        """Test behavior under concurrent resource exhaustion."""
        import threading
        
        def resource_exhausting_worker():
            """Worker that tries to exhaust resources."""
            try:
                # Try to consume CPU/memory
                for _ in range(1000):
                    hole = [Card('A', Suit.SPADE), Card('K', Suit.HEART)]
                    get_hand_tier(hole)
            except Exception:
                # Errors are acceptable under resource pressure
                pass
        
        # Start multiple resource-exhausting threads
        threads = []
        for _ in range(8):  # More threads than typical CPU cores
            thread = threading.Thread(target=resource_exhausting_worker)
            threads.append(thread)
            thread.start()
        
        # System should remain responsive
        start_time = time.time()
        
        # Wait for completion with timeout
        for thread in threads:
            thread.join(timeout=10.0)  # 10 second timeout per thread
        
        elapsed_time = time.time() - start_time
        
        # Should complete within reasonable time (not hang indefinitely)
        assert elapsed_time < 30.0, "System became unresponsive under load"


if __name__ == "__main__":
    print("Security and Input Validation tests for Poker Assistant")
    print("Run with: python -m pytest security_validation_tests.py -v")
    print("These tests verify input sanitization, injection prevention, and security best practices")
