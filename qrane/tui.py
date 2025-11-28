#!/usr/bin/env python3
# qrane/tui.py - Split-screen Terminal Interface
import curses
import time
import threading
import re

class QonqreteTUI:
    def __init__(self):
        self.stdscr = None
        self.top_win = None
        self.bottom_win = None
        self.log_lock = threading.Lock()

        self.COLOR_DEFAULT = 1
        self.COLOR_GREEN = 2
        self.COLOR_RED = 3
        self.COLOR_YELLOW = 4
        self.COLOR_CYAN = 5
        self.COLOR_BLUE = 6

    def __enter__(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        curses.curs_set(0)

        # Define pairs
        curses.init_pair(self.COLOR_DEFAULT, -1, -1)
        curses.init_pair(self.COLOR_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(self.COLOR_RED, curses.COLOR_RED, -1)
        curses.init_pair(self.COLOR_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.COLOR_CYAN, curses.COLOR_CYAN, -1)
        curses.init_pair(self.COLOR_BLUE, curses.COLOR_BLUE, -1)

        self.setup_windows()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def setup_windows(self):
        rows, cols = self.stdscr.getmaxyx()
        split_point = rows // 2

        # TOP WINDOW (Qommander / Flow)
        # H: split_point, W: cols, Y: 0, X: 0
        self.top_win = curses.newwin(split_point, cols, 0, 0)
        self.top_win.scrollok(True)
        self.top_win.idlok(True)

        # BOTTOM WINDOW (Qonsole / Logs)
        # H: rows - split_point, W: cols, Y: split_point, X: 0
        self.bottom_win = curses.newwin(rows - split_point, cols, split_point, 0)
        self.bottom_win.scrollok(True)
        self.bottom_win.idlok(True)

        self.refresh_borders()

    def close(self):
        if self.stdscr:
            curses.curs_set(1)
            self.stdscr.keypad(False)
            curses.echo()
            curses.nocbreak()
            curses.endwin()

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def refresh_borders(self):
        # Draw borders and titles
        self.top_win.box()
        self.top_win.addstr(0, 2, " Qommander (Flow) ", curses.A_BOLD | curses.color_pair(self.COLOR_CYAN))

        self.bottom_win.box()
        self.bottom_win.addstr(0, 2, " Qonsole (Agents) ", curses.A_BOLD | curses.color_pair(self.COLOR_YELLOW))

        self.top_win.refresh()
        self.bottom_win.refresh()

    def _append_to_win(self, window, text: str, color_attr, is_top=False):
        """Helper to append text to a scrollable window inside a box."""
        with self.log_lock:
            h, w = window.getmaxyx()
            clean_text = self._strip_ansi(text)

            # Simple line splitting
            lines = clean_text.split('\n')
            for line in lines:
                if len(line) > w - 4: line = line[:w-4]

                # Write to the line just above the bottom border
                try:
                    window.addstr(h-2, 2, line + "\n", color_attr)
                except curses.error:
                    pass

                # Redraw Box and Title after scroll
                window.box()
                if is_top:
                    window.addstr(0, 2, " Qommander (Flow) ", curses.A_BOLD | curses.color_pair(self.COLOR_CYAN))
                else:
                    window.addstr(0, 2, " Qonsole (Agents) ", curses.A_BOLD | curses.color_pair(self.COLOR_YELLOW))

            window.refresh()

    # --- PUBLIC API ---

    def log_main(self, text: str):
        """Log to Top Window (High Level Flow)."""
        # Auto-color cues based on text
        attr = curses.color_pair(self.COLOR_DEFAULT) | curses.A_BOLD
        if "Cycle" in text: attr = curses.color_pair(self.COLOR_CYAN) | curses.A_BOLD
        if "Ingesting" in text: attr = curses.color_pair(self.COLOR_BLUE)
        if "Success" in text: attr = curses.color_pair(self.COLOR_GREEN)

        self._append_to_win(self.top_win, text, attr, is_top=True)

    def log_agent(self, text: str):
        """Log to Bottom Window (Agent Output)."""
        attr = curses.color_pair(self.COLOR_DEFAULT)
        lower = text.lower()
        if "error" in lower or "critical" in lower: attr = curses.color_pair(self.COLOR_RED)
        elif "exec" in lower: attr = curses.color_pair(self.COLOR_YELLOW)

        self._append_to_win(self.bottom_win, text, attr, is_top=False)

    def get_input(self, prompt: str) -> str:
        """Pauses execution to get input from the Top window."""
        # Print prompt
        self.log_main(prompt)

        curses.echo()
        curses.curs_set(1)

        # We cheat a bit and just ask for input at the top line (0,0) of stdscr to avoid complex window input logic
        # Or cleaner: input in top window last line
        h, w = self.top_win.getmaxyx()
        self.top_win.addstr(h-2, 2, "> ", curses.color_pair(self.COLOR_YELLOW))
        self.top_win.refresh()

        inp = self.top_win.getstr(h-2, 4, 20)

        curses.noecho()
        curses.curs_set(0)

        return inp.decode('utf-8').strip()
