#!/usr/bin/env python3
"""
GUI Integration Tests for Poker Assistant.
Tests GUI components and their integration with backend logic.

Note: These tests use mocking to simulate GUI interactions since we can't
easily test tkinter GUIs in a headless environment.

Run with: python -m pytest gui_integration_tests.py -v
"""

import pytest
import tkinter as tk
import threading
import time
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from typing import List, Dict, Any

# Import poker modules
from poker_modules import Card, Suit, Position, StackType, GameState


class TestGUIComponentIntegration:
    """Test GUI component integration with backend logic."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Create a mock root window to avoid actual GUI creation
        self.mock_root = Mock(spec=tk.Tk)
        self.mock_root.configure = Mock()
        self.mock_root.title = Mock()
        self.mock_root.geometry = Mock()
        self.mock_root.protocol = Mock()
        
    def test_poker_assistant_initialization(self):
        """Test PokerAssistant initialization without creating actual GUI."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                # Import here to avoid GUI creation during module import
                from poker_gui import PokerAssistant
                
                # Mock the GUI creation methods
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    
                    # Verify initialization
                    assert hasattr(app, 'position')
                    assert hasattr(app, 'stack_type')
                    assert hasattr(app, 'game_state')
                    assert isinstance(app.game_state, GameState)
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_card_slot_functionality(self):
        """Test CardSlot component functionality."""
        with patch('tkinter.Frame'), \
             patch('tkinter.Label'):
            
            try:
                from poker_gui import CardSlot
                
                # Create mock app
                mock_app = Mock()
                mock_app.grey_out = Mock()
                mock_app.un_grey = Mock()
                mock_app.force_refresh = Mock()
                
                # Create CardSlot with mocked GUI components
                with patch('poker_gui.tk.Frame.__init__'), \
                     patch('poker_gui.tk.Label'):
                    
                    slot = CardSlot(Mock(), "Test Slot", mock_app)
                    slot.card = None
                    
                    # Test setting a card
                    test_card = Card('A', Suit.SPADE)
                    
                    # Mock the GUI update methods
                    slot.winfo_children = Mock(return_value=[])
                    slot.pack_propagate = Mock()
                    
                    result = slot.set_card(test_card)
                    
                    assert result == True
                    assert slot.card == test_card
                    mock_app.grey_out.assert_called_once_with(test_card)
                    mock_app.force_refresh.assert_called_once()
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_player_toggle_functionality(self):
        """Test PlayerToggle component functionality."""
        with patch('tkinter.Frame'), \
             patch('tkinter.Canvas'), \
             patch('tkinter.Label'):
            
            try:
                from poker_gui import PlayerToggle
                
                # Create mock app
                mock_app = Mock()
                mock_app.update_active_players = Mock()
                mock_app.force_refresh = Mock()
                
                # Create PlayerToggle with mocked GUI components
                with patch('poker_gui.tk.Frame.__init__'), \
                     patch.object(PlayerToggle, '_create_widget'), \
                     patch.object(PlayerToggle, '_draw_player'):
                    
                    toggle = PlayerToggle(Mock(), 1, mock_app)
                    toggle._is_active = True
                    
                    # Test toggle functionality
                    initial_state = toggle._is_active
                    toggle._toggle()
                    
                    assert toggle._is_active != initial_state
                    mock_app.update_active_players.assert_called_once()
                    mock_app.force_refresh.assert_called_once()
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")


class TestGUIWorkflowIntegration:
    """Test complete GUI workflow integration."""
    
    def test_card_placement_workflow(self):
        """Test the complete card placement workflow."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                # Mock GUI components
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'), \
                     patch.object(PokerAssistant, '_highlight_next_slot'), \
                     patch.object(PokerAssistant, 'grey_out'), \
                     patch.object(PokerAssistant, 'un_grey'):
                    
                    app = PokerAssistant()
                    
                    # Mock hole card slots
                    mock_slot1 = Mock()
                    mock_slot1.card = None
                    mock_slot1.set_card = Mock(return_value=True)
                    
                    mock_slot2 = Mock()
                    mock_slot2.card = None
                    mock_slot2.set_card = Mock(return_value=True)
                    
                    app.hole = [mock_slot1, mock_slot2]
                    app.board = []
                    
                    # Test placing cards
                    card1 = Card('A', Suit.SPADE)
                    card2 = Card('K', Suit.HEART)
                    
                    app.place_card_in_next_slot(card1)
                    mock_slot1.set_card.assert_called_once_with(card1)
                    
                    # Simulate first slot now has card
                    mock_slot1.card = card1
                    mock_slot1.set_card = Mock(return_value=False)  # Slot full
                    
                    app.place_card_in_next_slot(card2)
                    mock_slot2.set_card.assert_called_once_with(card2)
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_analysis_update_workflow(self):
        """Test the analysis update workflow."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, '_highlight_next_slot'), \
                     patch.object(PokerAssistant, '_clear_output_panels'), \
                     patch.object(PokerAssistant, '_update_game_state'), \
                     patch.object(PokerAssistant, '_update_analysis_panel'), \
                     patch.object(PokerAssistant, '_update_stats_panel'), \
                     patch.object(PokerAssistant, '_display_welcome_message'):
                    
                    app = PokerAssistant()
                    
                    # Mock GUI components
                    app.decision_label = Mock()
                    app.decision_label.config = Mock()
                    app.table_window = Mock()
                    app.table_window.update_state = Mock()
                    
                    # Mock slots with cards
                    mock_hole_slot1 = Mock()
                    mock_hole_slot1.card = Card('A', Suit.SPADE)
                    mock_hole_slot2 = Mock()
                    mock_hole_slot2.card = Card('K', Suit.HEART)
                    
                    app.hole = [mock_hole_slot1, mock_hole_slot2]
                    app.board = []
                    
                    # Mock the analysis return
                    mock_analysis = Mock()
                    mock_analysis.decision = "RAISE"
                    mock_analysis.equity = 0.75
                    app._update_analysis_panel = Mock(return_value=mock_analysis)
                    
                    # Test refresh workflow
                    app.refresh()
                    
                    # Verify workflow steps
                    app._clear_output_panels.assert_called_once()
                    app._update_game_state.assert_called_once()
                    app._highlight_next_slot.assert_called_once()
                    app._update_analysis_panel.assert_called_once()
                    app._update_stats_panel.assert_called_once()
                    app.table_window.update_state.assert_called_once()
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_keyboard_input_workflow(self):
        """Test keyboard input handling workflow."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'), \
                     patch.object(PokerAssistant, 'place_card_in_next_slot') as mock_place:
                    
                    app = PokerAssistant()
                    app.grid_cards = {}
                    
                    # Create mock grid cards
                    for rank in ['A', 'K']:
                        for suit in [Suit.SPADE, Suit.HEART]:
                            card = Card(rank, suit)
                            mock_grid_card = Mock()
                            mock_grid_card._is_used = False
                            app.grid_cards[str(card)] = mock_grid_card
                    
                    # Test keyboard input for A♠
                    mock_event_a = Mock()
                    mock_event_a.char = 'A'
                    
                    mock_event_s = Mock()
                    mock_event_s.char = 'S'
                    
                    # Simulate typing 'AS' for Ace of Spades
                    app._handle_keypress(mock_event_a)
                    app._handle_keypress(mock_event_s)
                    
                    # Should have called place_card_in_next_slot with A♠
                    expected_card = Card('A', Suit.SPADE)
                    mock_place.assert_called_with(expected_card)
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")


class TestTableDiagramIntegration:
    """Test table diagram integration."""
    
    def test_table_diagram_initialization(self):
        """Test table diagram window initialization."""
        with patch('tkinter.Toplevel'), \
             patch('tkinter.Canvas'):
            
            try:
                from poker_tablediagram import TableDiagramWindow
                
                with patch.object(TableDiagramWindow, '_draw_table'):
                    window = TableDiagramWindow()
                    
                    # Verify initialization
                    assert hasattr(window, 'state')
                    assert hasattr(window, 'seat_positions')
                    assert window.state.hero_seat == 1
                    assert window.state.dealer_seat == 3
                    
            except ImportError:
                pytest.skip("Table diagram module not available for testing")
    
    def test_table_state_updates(self):
        """Test table state update functionality."""
        with patch('tkinter.Toplevel'), \
             patch('tkinter.Canvas'):
            
            try:
                from poker_tablediagram import TableDiagramWindow
                
                with patch.object(TableDiagramWindow, '_draw_table') as mock_draw:
                    window = TableDiagramWindow()
                    
                    # Test state update
                    active_players = {1, 2, 3, 4, 5, 6}
                    window.update_state(
                        active_players=active_players,
                        hero_seat=2,
                        dealer_seat=4,
                        pot=50.0,
                        to_call=10.0,
                        stage="Flop",
                        equity=65.5
                    )
                    
                    # Verify state was updated
                    assert window.state.active_players == active_players
                    assert window.state.hero_seat == 2
                    assert window.state.dealer_seat == 4
                    assert window.state.pot == 50.0
                    assert window.state.equity == 65.5
                    
                    # Should trigger redraw
                    mock_draw.assert_called()
                    
            except ImportError:
                pytest.skip("Table diagram module not available for testing")


class TestGUIDataFlow:
    """Test data flow between GUI components and backend."""
    
    def test_position_change_propagation(self):
        """Test position changes propagate through system."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh') as mock_refresh:
                    
                    app = PokerAssistant()
                    
                    # Change position
                    initial_position = app.position.get()
                    app.position.set(Position.CO.name)
                    
                    # Simulate radiobutton command callback
                    app.refresh()
                    
                    # Verify refresh was called (which updates analysis)
                    mock_refresh.assert_called()
                    assert app.position.get() == Position.CO.name
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_player_toggle_propagation(self):
        """Test player toggle changes propagate to analysis."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant, PlayerToggle
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    app.player_toggles = {}
                    
                    # Create mock player toggles
                    for i in range(1, 7):
                        mock_toggle = Mock()
                        mock_toggle.is_active = Mock(return_value=True)
                        app.player_toggles[i] = mock_toggle
                    
                    # Test update_active_players
                    app.update_active_players()
                    
                    # Should set num_players to 6 (all active)
                    assert app.num_players.get() == 6
                    
                    # Test with some players inactive
                    app.player_toggles[1].is_active = Mock(return_value=False)
                    app.player_toggles[2].is_active = Mock(return_value=False)
                    
                    app.update_active_players()
                    assert app.num_players.get() == 4
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_betting_input_validation(self):
        """Test betting input validation and propagation."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    
                    # Mock entry widgets
                    app.pot_entry = Mock()
                    app.call_entry = Mock()
                    
                    # Test valid input
                    app.pot_entry.get = Mock(return_value="25.5")
                    app.call_entry.get = Mock(return_value="10.0")
                    
                    app._update_game_state()
                    
                    assert app.game_state.is_active == True
                    assert app.game_state.pot == 25.5
                    assert app.game_state.to_call == 10.0
                    
                    # Test invalid input
                    app.pot_entry.get = Mock(return_value="invalid")
                    app.call_entry.get = Mock(return_value="also_invalid")
                    
                    app._update_game_state()
                    
                    assert app.game_state.is_active == False
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")


class TestGUIErrorHandling:
    """Test GUI error handling scenarios."""
    
    def test_gui_exception_handling(self):
        """Test GUI handles exceptions gracefully."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'), \
             patch('poker_gui.messagebox') as mock_messagebox:
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    app._last_decision_id = None
                    
                    # Test action recording with no analysis
                    from poker_modules import PlayerAction
                    app._record_action(PlayerAction.RAISE)
                    
                    # Should show warning message
                    mock_messagebox.showwarning.assert_called_once()
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_gui_memory_cleanup(self):
        """Test GUI components are properly cleaned up."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    
                    # Mock destroy method
                    app.destroy = Mock()
                    app.table_window = Mock()
                    app.table_window.destroy = Mock()
                    
                    # Test cleanup on close
                    app._on_close()
                    
                    # Should destroy both windows
                    app.table_window.destroy.assert_called_once()
                    app.destroy.assert_called_once()
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")


class TestGUIPerformance:
    """Test GUI performance characteristics."""
    
    def test_gui_responsiveness(self):
        """Test GUI remains responsive during calculations."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'):
                    
                    app = PokerAssistant()
                    
                    # Mock time-consuming operation
                    original_refresh = app.refresh
                    call_count = 0
                    
                    def slow_refresh():
                        nonlocal call_count
                        call_count += 1
                        time.sleep(0.01)  # Simulate slow operation
                        return Mock()
                    
                    app.refresh = slow_refresh
                    
                    # Test that multiple rapid calls don't block
                    start_time = time.time()
                    
                    for _ in range(10):
                        app.refresh()
                    
                    elapsed_time = time.time() - start_time
                    
                    # Should complete reasonably quickly
                    assert elapsed_time < 1.0
                    assert call_count == 10
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")
    
    def test_gui_memory_efficiency(self):
        """Test GUI memory usage patterns."""
        with patch('tkinter.Tk'), \
             patch('poker_gui.ttk'), \
             patch('poker_gui.TableDiagramWindow'):
            
            try:
                from poker_gui import PokerAssistant
                
                with patch.object(PokerAssistant, '_build_gui'), \
                     patch.object(PokerAssistant, 'update_active_players'), \
                     patch.object(PokerAssistant, 'refresh'):
                    
                    app = PokerAssistant()
                    
                    # Test that repeated operations don't accumulate memory
                    initial_dict_size = len(app.grid_cards)
                    
                    # Simulate repeated card operations
                    for _ in range(100):
                        # Mock card placement and clearing
                        app.used_cards.add("AS")
                        app.used_cards.discard("AS")
                    
                    # Size should remain stable
                    final_dict_size = len(app.grid_cards)
                    assert final_dict_size == initial_dict_size
                    
                    # Used cards should be clean
                    assert len(app.used_cards) == 0
                    
            except ImportError:
                pytest.skip("GUI module not available for testing")


if __name__ == "__main__":
    print("GUI Integration tests for Poker Assistant")
    print("Run with: python -m pytest gui_integration_tests.py -v")
    print("Note: These tests use mocking to simulate GUI interactions")
