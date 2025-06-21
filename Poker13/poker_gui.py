#!/usr/bin/env python3
"""
Graphical user interface and in-game flow for Poker-Assistant.
Now with a larger, information-rich table graphic: the dealer
button is shown in RED and folded seats are dimmed.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import weakref, logging, math, re
from typing import List, Dict, Tuple, Optional

# ──────────────────────────────────────────────────────
#  Third-Party / Local modules
# ──────────────────────────────────────────────────────
from poker_modules import (
    Suit, Rank, RANKS_MAP, Card, Position, StackType, PlayerAction,
    HandAnalysis, GameState, get_hand_tier, analyse_hand, to_two_card_str,
    get_position_advice, get_hand_advice, RANK_ORDER
)
from poker_init import open_db, record_decision

# ──────────────────────────────────────────────────────
#  Constants & Colours
# ──────────────────────────────────────────────────────
log = logging.getLogger(__name__)

C_BG, C_PANEL, C_TABLE, C_CARD, C_CARD_INACTIVE, C_TEXT, C_TEXT_DIM, C_BORDER = \
"#1a1a1a", "#242424", "#1a5f3f", "#ffffff", "#3a3a3a", "#e8e8e8", "#888888", "#3a3a3a"
C_BTN_PRIMARY, C_BTN_SUCCESS, C_BTN_DANGER, C_BTN_WARNING, C_BTN_INFO, C_BTN_DARK = \
"#10b981", "#10b981", "#ef4444", "#f59e0b", "#3b82f6", "#374151"
C_BTN_PRIMARY_HOVER, C_BTN_SUCCESS_HOVER, C_BTN_DANGER_HOVER, C_BTN_WARNING_HOVER, C_BTN_INFO_HOVER, C_BTN_DARK_HOVER = \
"#34d399", "#34d399", "#f87171", "#fbbf24", "#60a5fa", "#4b5563"

# ──────────────────────────────────────────────────────
#  GUI Widgets
# ──────────────────────────────────────────────────────
class StyledButton(tk.Button):
    def __init__(self, parent, text="", color=C_BTN_PRIMARY, hover_color=None, **kwargs):
        default_fg = "black" if color in (C_BTN_PRIMARY, C_BTN_SUCCESS) else "white"
        fg_color = kwargs.pop("fg", default_fg)
        defaults = {"font": ("Arial", 10, "bold"), "fg": fg_color, "bg": color,
                    "activebackground": hover_color or color, "activeforeground": fg_color,
                    "bd": 0, "padx": 12, "pady": 6, "cursor": "hand2", "relief": "flat"}
        defaults.update(kwargs)
        super().__init__(parent, text=text, **defaults)
        self._bg, self._hover_bg = color, hover_color
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg or self._bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

class DraggableCard(tk.Label):
    def __init__(self, master: tk.Widget, card: Card, app):
        super().__init__(master, text=str(card), font=("Arial", 12, "bold"),
                         fg=card.suit.color, bg=C_CARD, width=3, height=2,
                         bd=1, relief="solid", highlightthickness=0)
        self.card, self._app = card, weakref.proxy(app)
        self._start, self._dragging = (0, 0), False
        self.bind("<Button-1>", self._click_start)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _click_start(self, ev): self._start, self._dragging = (ev.x, ev.y), False; self.lift()
    def _drag(self, ev):
        if abs(ev.x - self._start[0]) > 3 or abs(ev.y - self._start[1]) > 3: self._dragging = True
        self.place(x=self.winfo_x() + (ev.x - self._start[0]), y=self.winfo_y() + (ev.y - self._start[1]))

    def _release(self, ev):
        target = self.winfo_containing(ev.x_root, ev.y_root)
        if self._dragging and hasattr(target, "accept"): target.accept(self)
        else: self.place_forget(); self.pack(side="left", padx=2, pady=2); self._app.place_next_free(self.card)

class CardSlot(tk.Frame):
    def __init__(self, master: tk.Widget, name: str, app):
        super().__init__(master, width=60, height=80, bg="#0d3a26", bd=2, relief="groove",
                         highlightbackground=C_BORDER, highlightthickness=1)
        self.pack_propagate(False)
        self._label = tk.Label(self, text=name, bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)
        self.card, self._app = None, weakref.proxy(app)

    def accept(self, widget: DraggableCard):
        if self.card: widget.place_forget(); widget.pack(side="left", padx=2, pady=2); return
        self.set_card(widget.card)
        widget.place_forget()
        widget._app.grey_out(widget.card)
        self._app.refresh()

    def set_card(self, card: Card):
        self.card = card
        for w in self.winfo_children(): w.destroy()
        inner = tk.Label(self, text=str(card), font=("Arial", 16, "bold"),
                         fg=card.suit.color, bg=C_CARD, bd=1, relief="solid")
        inner.pack(expand=True, fill="both", padx=2, pady=2)
        inner.bind("<Double-Button-1>", lambda *_: self.clear())

    def clear(self):
        if not self.card: return
        self._app.un_grey(self.card)
        self.card = None
        for w in self.winfo_children(): w.destroy()
        self._label = tk.Label(self, text="Empty", bg="#0d3a26", fg=C_TEXT_DIM, font=("Arial", 9))
        self._label.pack(expand=True)
        self._app.refresh()

# ──────────────────────────────────────────────────────
#  Table visualisation – completely revamped
# ──────────────────────────────────────────────────────
class TableVisualization(tk.Canvas):
    """
    • Larger canvas (default 380×260)
    • Dealer button shown in RED
    • Dimmed / grey seats = player has folded
    • Centre of table shows Pot, To-Call, Stage, and (if available) Hero equity
    """
    def __init__(self, parent, app, width: int = 380, height: int = 260):
        super().__init__(parent, width=width, height=height, bg=C_PANEL, highlightthickness=0)
        self.W, self.H = width, height
        self._app = weakref.proxy(app)
        self.table_rotation = 0
        # Runtime info (updated by PokerAssistant.refresh)
        self._pot = 0.0
        self._to_call = 0.0
        self._stage = "Pre-flop"
        self._hero_equity: Optional[float] = None
        self._draw_table()

    # Public – PokerAssistant calls this on every refresh --------------------
    def update_info(self, pot: float, to_call: float, stage: str, equity: Optional[float]):
        self._pot, self._to_call, self._stage, self._hero_equity = pot, to_call, stage, equity
        self._draw_table()

    # Rotation helpers --------------------------------------------------------
    def rotate_clockwise(self):
        self.table_rotation = (self.table_rotation - 1) % self._app.num_players.get()
        self._draw_table()

    def rotate_counter_clockwise(self):
        self.table_rotation = (self.table_rotation + 1) % self._app.num_players.get()
        self._draw_table()

    # Internal ----------------------------------------------------------------
    def _draw_table(self):
        self.delete("all")
        cx, cy = self.W // 2, self.H // 2
        rx, ry = int(self.W * 0.35), int(self.H * 0.27)

        # Main oval
        self.create_oval(cx - rx, cy - ry, cx + rx, cy + ry,
                         fill="#0d3a26", outline="#1a5f3f", width=3)
        self.create_oval(cx - rx + 10, cy - ry + 10, cx + rx - 10, cy + ry - 10,
                         fill="", outline="#1a5f3f", width=1)

        # Centre information --------------------------------------------------
        txt = f"Pot: ${self._pot:.2f}\nTo Call: ${self._to_call:.2f}\n{self._stage}"
        if self._hero_equity is not None:
            txt += f"\nEquity: {self._hero_equity*100:4.1f}%"
        self.create_text(cx, cy, text=txt, fill="white",
                         font=("Consolas", 10, "bold"), justify="center")

        # Players -------------------------------------------------------------
        num_players = self._app.num_players.get()
        your_seat = Position[self._app.position.get()].value
        active_players = set(self._app.game_state.players_in_hand) if self._app.game_state.is_active else set(range(1, num_players + 1))

        for seat in range(1, num_players + 1):
            visual_pos = (seat - 1 - self.table_rotation) % num_players
            angle = (visual_pos * 2 * math.pi / num_players) - (math.pi / 2)
            px, py = cx + int(rx * 1.25 * math.cos(angle)), cy + int(ry * 1.25 * math.sin(angle))

            is_hero = seat == your_seat
            is_dealer = seat == Position.BTN.value
            in_hand = seat in active_players

            radius = 24 if is_hero else 20
            # Colour logic ----------------------------------------------------
            if is_hero:
                fill, outline, text_c = "#fbbf24", "#fbbf24", "black"
                label, weight = "YOU", "bold"
            elif is_dealer:
                fill, outline, text_c = "#ef4444", "#ef4444", "white"
                label, weight = "BTN", "bold"
            else:
                fill, outline, text_c = (C_BTN_DARK, C_BORDER, "white") if in_hand else ("#4b5563", "#4b5563", "#aaaaaa")
                label, weight = f"P{seat}", "normal"

            self.create_oval(px - radius, py - radius, px + radius, py + radius,
                             fill=fill, outline=outline, width=2 if (is_hero or is_dealer) else 1)
            self.create_text(px, py, text=label, font=("Arial", 10, weight), fill=text_c)

            # Blinds labels
            if seat == Position.SB.value:
                self.create_text(px, py + radius + 10, text="SB", font=("Arial", 9, "bold"), fill=C_BTN_INFO)
            elif seat == Position.BB.value:
                self.create_text(px, py + radius + 10, text="BB", font=("Arial", 9, "bold"), fill=C_BTN_INFO)
# ──────────────────────────────────────────────────────
#  Main application window
# ──────────────────────────────────────────────────────
class PokerAssistant(tk.Tk):
    FONT_HEADER = ("Arial", 12, "bold")
    FONT_SUBHEADER = ("Arial", 11, "bold")
    FONT_BODY = ("Consolas", 10)
    FONT_SMALL_LABEL = ("Arial", 9)
    STYLE_ENTRY = {"bg": C_BTN_DARK, "fg": "white", "bd": 1, "relief": "solid",
                   "insertbackground": "white",
                   "font": ("Arial", 10),
                   "highlightthickness": 1,
                   "highlightcolor": C_BTN_PRIMARY,
                   "highlightbackground": C_BORDER}

    def __init__(self):
        super().__init__()
        self.title("Poker Assistant v13 - Pro Edition")
        self.geometry("1400x900")
        self.minsize(1200, 800)
        self.configure(bg=C_BG)
        self.option_add("*Font", "Arial 10")

        # State vars
        self.position = tk.StringVar(value=Position.BTN.name)
        self.stack_type = tk.StringVar(value=StackType.MEDIUM.value)
        self.small_blind = tk.DoubleVar(value=0.5)
        self.big_blind = tk.DoubleVar(value=1.0)
        self.num_players = tk.IntVar(value=6)

        # Game state
        self.game_state = GameState()

        # UI state
        self.grid_cards: Dict[str, DraggableCard] = {}
        self.used_cards: set[str] = set()
        self._last_decision_id: Optional[int] = None
        self._refresh_scheduled = False

        self._build_gui()
        self.after(100, self.refresh)

    # -----------------------------------------------------------------------
    #  GUI construction
    # -----------------------------------------------------------------------
    def _build_gui(self):
        main = tk.Frame(self, bg=C_BG); main.pack(fill="both", expand=True, padx=15, pady=10)

        # Left panel (deck + big table)
        left_panel = tk.Frame(main, bg=C_PANEL, width=400)  # widened
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)
        self._build_card_grid(left_panel)
        self._build_table_view(left_panel)

        # Right panel (everything else)
        right_panel = tk.Frame(main, bg=C_BG)
        right_panel.pack(side="left", fill="both", expand=True, padx=(15, 0))
        self._build_table_area(right_panel)
        self._build_control_panel(right_panel)
        self._build_action_panel(right_panel)
        self._build_analysis_area(right_panel)

    # ------------ unchanged helper builders up to Table View ---------------
    # (… existing code for _build_card_grid remains identical …)
    # -----------------------------------------------------------------------
    def _build_card_grid(self, parent):
        tk.Label(parent, text="CARD DECK", font=("Arial", 11, "bold"),
                 bg=C_PANEL, fg=C_TEXT).pack(pady=(10, 5))
        card_container = tk.Frame(parent, bg=C_PANEL)
        card_container.pack(fill="x", expand=False, padx=10)

        for suit in [Suit.SPADE, Suit.HEART, Suit.DIAMOND, Suit.CLUB]:
            sf = tk.LabelFrame(card_container, text=f" {suit.value} ",
                               fg=suit.color if suit.color == "red" else C_TEXT,
                               bg=C_PANEL, font=("Arial", 10, "bold"),
                               bd=1, relief="groove", labelanchor="w", padx=5, pady=5)
            sf.pack(fill="x", pady=3)
            rows = tk.Frame(sf, bg=C_PANEL); rows.pack()
            r1, r2 = tk.Frame(rows, bg=C_PANEL), tk.Frame(rows, bg=C_PANEL)
            r1.pack(); r2.pack(pady=(3, 0))
            for i, r_val in enumerate(RANK_ORDER):
                card = Card(r_val, suit)
                w = DraggableCard(r1 if i < 7 else r2, card, self)
                w.pack(side="left", padx=2)
                self.grid_cards[str(card)] = w

    def _build_table_view(self, parent):
        tf = tk.LabelFrame(parent, text=" TABLE ", bg=C_PANEL, fg=C_TEXT,
                           font=("Arial", 10, "bold"), bd=1, relief="groove")
        tf.pack(fill="x", padx=10, pady=10)
        self.table_viz = TableVisualization(tf, self)  # bigger canvas
        self.table_viz.pack(pady=5)
        # rotate buttons (small)
        rf = tk.Frame(tf, bg=C_PANEL); rf.pack(pady=(0, 10))
        StyledButton(rf, text="◀", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER,
                     command=self.table_viz.rotate_counter_clockwise,
                     width=3, padx=5, pady=3).pack(side="left", padx=5)
        tk.Label(rf, text="Rotate", bg=C_PANEL, fg=C_TEXT_DIM).pack(side="left", padx=10)
        StyledButton(rf, text="▶", color=C_BTN_DARK, hover_color=C_BTN_DARK_HOVER,
                     command=self.table_viz.rotate_clockwise,
                     width=3, padx=5, pady=3).pack(side="left", padx=5)

    # -------------------- (all original builder methods stay the same) -----
    #  … existing _build_table_area, _build_control_panel, etc. …

    # ────────────────────────────────────────────────────────────────────
    #  Refresh logic – only the parts that changed are shown
    # ────────────────────────────────────────────────────────────────────
    def refresh(self):
        hole = [s.card for s in self.hole if s.card]
        board = [s.card for s in self.board if s.card]

        self._clear_output_panels()

        # Decide stage for the table visual
        stage_lookup = {0: "Pre-flop", 3: "Flop", 4: "Turn", 5: "River"}
        stage = stage_lookup.get(len(board), "Post-flop")

        analysis: Optional[HandAnalysis] = None
        if len(hole) == 2:
            analysis = self._update_analysis_panel(hole, board)
        else:
            self._display_welcome_message()

        self._update_stats_panel()

        # Always update the table graphic with live info
        pot = self.game_state.pot if self.game_state.is_active else (self.small_blind.get() + self.big_blind.get())
        to_call = self.game_state.to_call if self.game_state.is_active else self.big_blind.get()
        equity = analysis.equity if analysis else None
        self.table_viz.update_info(pot, to_call, stage, equity)

    # (The rest of the class remains unchanged – only _update_analysis_panel
    # now returns the HandAnalysis object so refresh() can pass equity.)

    def _update_analysis_panel(self, hole, board) -> HandAnalysis:
        pos = Position[self.position.get()]
        stack_bb = StackType(self.stack_type.get()).default_bb
        pot = self.game_state.pot if self.game_state.is_active else (self.small_blind.get() + self.big_blind.get())
        to_call = self.game_state.to_call if self.game_state.is_active else self.big_blind.get()
        num_players_in_hand = len(self.game_state.players_in_hand) if self.game_state.is_active else self.num_players.get()

        analysis = analyse_hand(hole, board, pos, stack_bb, pot, to_call, num_players_in_hand)
        tier = get_hand_tier(hole)
        board_str = ' '.join(map(str, board))
        self._last_decision_id = record_decision(analysis, pos, tier, stack_bb, pot, to_call, board_str)

        colors = {"RAISE": C_BTN_WARNING, "CALL": C_BTN_SUCCESS, "FOLD": C_BTN_DANGER, "CHECK": C_BTN_INFO}
        self.decision_label.config(text=f"→ {analysis.decision}", fg=colors.get(analysis.decision, C_TEXT))

        self.out_body.insert("end", f"Hand: {to_two_card_str(hole)} ({tier})\n", "header")
        self.out_body.insert("end", f"Board: {board_str or 'Pre-flop'} ({analysis.board_texture})\n", "dim")
        self.out_body.insert("end", f"Position: {pos.name} | Pot: ${pot:.2f} | SPR: {analysis.spr:.1f}\n\n", "dim")
        self.out_body.insert("end", "ADVICE\n", "subheader")
        self.out_body.insert("end", f"{get_position_advice(pos)}\n{get_hand_advice(tier, analysis.board_texture, analysis.spr)}\n\n", "dim")
        self.out_body.insert("end", "ANALYSIS\n", "subheader")
        self.out_body.insert("end", f"{analysis.reason}\n\n")
        self.out_body.insert("end", "EQUITY (Monte-Carlo)\n", "subheader")
        edge = analysis.equity - analysis.required_eq
        self.out_body.insert("end", f"Your Equity:     {analysis.equity:6.1%}\n")
        self.out_body.insert("end", f"Required Equity: {analysis.required_eq:6.1%}\n")
        self.out_body.insert("end", f"Edge:           {edge:+6.1%}\n", "positive" if edge >= 0 else "negative")

        return analysis  # <- NEW

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        app = PokerAssistant()
        app.mainloop()
    except Exception as e:
        log.error("Unhandled exception", exc_info=True)
        messagebox.showerror("Fatal Error", f"A critical error occurred: {e}")