#!/usr/bin/env python3
"""
Tiny launcher that wires everything together.

• All persistence-/DB code lives in  poker_init.py
• All pure poker logic lives in    poker_modules.py
• All GUI / game-flow code lives in poker_gui.py

Keeping this file small makes it easy to add command-line helpers or
alternative front-ends later without touching the GUI itself.
"""
import logging

# Ensure the database exists (side-effect is cheap / idempotent)
from poker_init import initialise_db_if_needed
initialise_db_if_needed()

# Import the GUI after the DB is ready
from poker_gui import PokerAssistant

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = PokerAssistant()
    app.mainloop()
