#!/usr/bin/env python3
# qrane/tui.py - Split-screen Terminal Interface
import curses
import time
import threading
import re
import subprocess
import os

class QonqreteTUI:
    def __init__(self):
        self.stdscr = None
        self.top_win = None
        self.bottom_win = None
        self.log_lock = threading.Lock()

        self.show_qonsole = True
        self.wonqrete_mode = False

        self.top_win_buffer = []
        self.bottom_win_buffer = []


        # Colors
        self.COLOR_DEFAULT = 1
        self.COLOR_GREEN = 2
        self.COLOR_RED = 3
        self.COLOR_YELLOW = 4
        self.COLOR_CYAN = 5
        self.COLOR_BLUE = 6
        self.COLOR_MAGENTA = 7
        self.COLOR_WHITE = 8

    def __enter__(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.use_default_colors()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        curses.curs_set(0)
        self.stdscr.nodelay(True) # Non-blocking input

        curses.init_pair(self.COLOR_DEFAULT, -1, -1)
        curses.init_pair(self.COLOR_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(self.COLOR_RED, curses.COLOR_RED, -1)
        curses.init_pair(self.COLOR_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.COLOR_CYAN, curses.COLOR_CYAN, -1)
        curses.init_pair(self.COLOR_BLUE, curses.COLOR_BLUE, -1)
        curses.init_pair(self.COLOR_MAGENTA, curses.COLOR_MAGENTA, -1)
        curses.init_pair(self.COLOR_WHITE, curses.COLOR_WHITE, -1)

        self.setup_windows()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def setup_windows(self):
        self.stdscr.clear()
        self.stdscr.refresh()
        rows, cols = self.stdscr.getmaxyx()

        # Reserve bottom line for Helper Bar
        main_rows = rows - 1

        if self.show_qonsole:
            split_point = main_rows // 2
            self.top_win = curses.newwin(split_point, cols, 0, 0)
            self.bottom_win = curses.newwin(main_rows - split_point, cols, split_point, 0)
        else:
            # Fullscreen Qommander
            self.top_win = curses.newwin(main_rows, cols, 0, 0)
            self.bottom_win = None # Disable bottom

        self.top_win.scrollok(True)
        self.top_win.idlok(True)

        if self.bottom_win:
            self.bottom_win.scrollok(True)
            self.bottom_win.idlok(True)

        # Redraw from buffers
        for text, attr in self.top_win_buffer:
            self._append_to_win(self.top_win, text, attr, buffer_only=False)
        for text, attr in self.bottom_win_buffer:
            self._append_to_win(self.bottom_win, text, attr, buffer_only=False)


        self.refresh_borders()
        self.draw_helper_bar()

    def toggle_qonsole(self):
        self.show_qonsole = not self.show_qonsole
        # Clear buffers for a clean redraw on toggle, as window sizes change
        self.top_win_buffer.clear()
        self.bottom_win_buffer.clear()
        self.setup_windows()

    def toggle_wonqrete(self):
        self.wonqrete_mode = not self.wonqrete_mode
        self.refresh_borders()

    def close(self):
        if self.stdscr:
            curses.curs_set(1)
            self.stdscr.keypad(False)
            curses.echo()
            curses.nocbreak()
            self.stdscr.nodelay(False)
            curses.endwin()

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def draw_helper_bar(self):
        h, w = self.stdscr.getmaxyx()
        bar = " [Space] Toggle Qonsole | [W] Toggle WoNQrete | [Esc] BreaQ | [K] Kill Agents "
        try:
            self.stdscr.addstr(h-1, 0, bar.ljust(w), curses.color_pair(self.COLOR_BLUE) | curses.A_REVERSE)
            self.stdscr.refresh()
        except: pass

    def refresh_borders(self):
        self.top_win.box()
        title = " Qommander (Flow) "
        if self.wonqrete_mode: title = " WoNQrete (Flow) "
        self.top_win.addstr(0, 2, title, curses.A_BOLD | curses.color_pair(self.COLOR_CYAN))

        if self.bottom_win:
            self.bottom_win.box()
            self.bottom_win.addstr(0, 2, " Qonsole (Raw Logs) ", curses.A_BOLD | curses.color_pair(self.COLOR_YELLOW))
            self.bottom_win.refresh()

        self.top_win.refresh()

    def _append_to_win(self, window, text: str, color_attr, buffer_only=False):
        if not window: return
        with self.log_lock:
            if buffer_only:
                if window == self.top_win: self.top_win_buffer.append((text, color_attr))
                else: self.bottom_win_buffer.append((text, color_attr))

            h, w = window.getmaxyx()
            clean_text = self._strip_ansi(text)

            lines = clean_text.split('\n')
            for line in lines:
                if len(line) > w - 4: line = line[:w-4]
                try:
                    # Use insertln to scroll content up
                    window.move(h-2, 2)
                    window.insertln()
                    window.addstr(2, 2, line, color_attr)
                except: pass

                window.box()
                # Redraw title
                if window == self.top_win:
                    t = " WoNQrete (Flow) " if self.wonqrete_mode else " Qommander (Flow) "
                    c = self.COLOR_CYAN
                else:
                    t = " Qonsole (Raw Logs) "
                    c = self.COLOR_YELLOW
                window.addstr(0, 2, t, curses.A_BOLD | curses.color_pair(c))

            window.refresh()

    def log_main(self, text: str):
        attr = curses.color_pair(self.COLOR_DEFAULT) | curses.A_BOLD
        if "instruQtor" in text: attr = curses.color_pair(self.COLOR_GREEN)
        elif "construQtor" in text: attr = curses.color_pair(self.COLOR_CYAN)
        elif "inspeQtor" in text: attr = curses.color_pair(self.COLOR_MAGENTA)
        elif "Qrane" in text: attr = curses.color_pair(self.COLOR_WHITE)
        self.top_win_buffer.append((text, attr))
        self._append_to_win(self.top_win, text, attr, buffer_only=False)

    def log_agent(self, text: str):
        if not self.show_qonsole: return
        attr = curses.color_pair(self.COLOR_DEFAULT)
        if "error" in text.lower(): attr = curses.color_pair(self.COLOR_RED)
        self.bottom_win_buffer.append((text, attr))
        self._append_to_win(self.bottom_win, text, attr, buffer_only=False)

    def get_key_nonblocking(self):
        try:
            return self.stdscr.getch()
        except: return -1

    def get_input_blocking(self, prompt: str) -> str:
        """Used for checkpoints, blocks execution."""
        self.stdscr.nodelay(False)
        self.log_main(prompt)
        curses.echo()
        curses.curs_set(1)
        h, w = self.top_win.getmaxyx()
        input_win = curses.newwin(3, w - 4, h - 4, 2)
        input_win.box()
        input_win.addstr(1, 2, "> ")
        input_win.refresh()

        inp_str = input_win.getstr(1, 4, 20).decode('utf-8').strip()

        curses.noecho()
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        # Clear the input window area
        self.top_win.touchwin()
        self.top_win.refresh()

        return inp_str

    def suspend_and_run(self, cmd_list):
        curses.def_prog_mode()
        curses.endwin()
        try: subprocess.run(cmd_list, check=False)
        except: pass
        curses.reset_prog_mode()
        self.stdscr.refresh()
        self.setup_windows()
