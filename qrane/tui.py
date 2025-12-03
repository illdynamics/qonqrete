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

    def main_loop(self, tick_callback=None):
        """A basic main loop to keep the TUI alive, with resize handling."""
        while True:
            key = self.get_key_nonblocking()
            if key == curses.KEY_RESIZE:
                self.setup_windows()
            elif key != -1:
                # Handle other keys if necessary, e.g., exit key
                if key == 27: # ESC
                    break

            if tick_callback:
                tick_callback()

            time.sleep(0.05) # Reduce CPU usage
    
    def __enter__(self):
        try:
            self.stdscr = curses.initscr()
            curses.start_color()
            curses.use_default_colors()
            curses.noecho()
            curses.cbreak()
            self.stdscr.keypad(True)
            curses.curs_set(0)
            self.stdscr.nodelay(True)

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
        except curses.error as e:
            # Clean up curses state before raising
            self.close()
            raise RuntimeError(f"Curses initialization failed: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def setup_windows(self):
        try:
            self.stdscr.clear()
            self.stdscr.refresh()
            rows, cols = self.stdscr.getmaxyx()

            # Reserve bottom line for Helper Bar
            main_rows = rows - 1
            if main_rows < 5: return # Not enough space to draw

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

            # Redraw from buffers (last N lines that fit)
            self._redraw_buffers()

            self.refresh_borders()
            self.draw_helper_bar()
        except curses.error:
            # Ignore errors during resize, as they are frequent
            pass
    
    def _redraw_buffers(self):
        if self.top_win:
            h, w = self.top_win.getmaxyx()
            for text, attr in self.top_win_buffer[-(h-2):]:
                self._append_to_win(self.top_win, text, attr, buffer_only=False, redraw=True)
        if self.bottom_win:
            h, w = self.bottom_win.getmaxyx()
            for text, attr in self.bottom_win_buffer[-(h-2):]:
                self._append_to_win(self.bottom_win, text, attr, buffer_only=False, redraw=True)

    def toggle_qonsole(self):
        self.show_qonsole = not self.show_qonsole
        self.setup_windows()


    def toggle_wonqrete(self):
        self.wonqrete_mode = not self.wonqrete_mode
        self.refresh_borders()

    def close(self):
        if self.stdscr:
            try:
                curses.curs_set(1)
                self.stdscr.keypad(False)
                curses.echo()
                curses.nocbreak()
                self.stdscr.nodelay(False)
                curses.endwin()
            except curses.error:
                # Ignore errors on exit, as the terminal might already be gone
                pass
            finally:
                self.stdscr = None

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def draw_helper_bar(self):
        try:
            h, w = self.stdscr.getmaxyx()
            if h > 0:
                bar = " [Space] Toggle Qonsole | [W] Toggle WoNQrete | [Esc] BreaQ | [K] Kill Agents "
                self.stdscr.addstr(h-1, 0, bar.ljust(w), curses.color_pair(self.COLOR_BLUE) | curses.A_REVERSE)
                self.stdscr.refresh()
        except curses.error:
            pass # Ignore if window is too small

    def refresh_borders(self):
        try:
            if self.top_win:
                self.top_win.box()
                title = " Qommander (Flow) "
                if self.wonqrete_mode: title = " WoNQrete (Flow) "
                self.top_win.addstr(0, 2, title, curses.A_BOLD | curses.color_pair(self.COLOR_CYAN))
                self.top_win.refresh()

            if self.bottom_win:
                self.bottom_win.box()
                self.bottom_win.addstr(0, 2, " Qonsole (Raw Logs) ", curses.A_BOLD | curses.color_pair(self.COLOR_YELLOW))
                self.bottom_win.refresh()
        except curses.error:
            pass # Ignore if window is too small


    def _append_to_win(self, window, text: str, color_attr, buffer_only=False, redraw=False):
        if not window: return

        with self.log_lock:
            # Only add to buffer if it's not a redraw operation
            if not redraw:
                if window == self.top_win:
                    self.top_win_buffer.append((text, color_attr))
                elif self.bottom_win:
                    self.bottom_win_buffer.append((text, color_attr))

            if buffer_only: return

            try:
                h, w = window.getmaxyx()
                if h <= 2 or w <= 4: return # Can't draw in this window

                clean_text = self._strip_ansi(text)
                lines = clean_text.split('\n')

                for line in lines:
                    # Truncate line to fit window
                    display_line = line[:w - 3]
                    
                    # Move cursor to the line before the border, scroll up, then add the new line
                    window.move(h - 2, 2)
                    window.insertln()
                    window.addstr(2, 2, display_line, color_attr)

                # Redraw borders and title after adding text
                if window == self.top_win:
                    title = " WoNQrete (Flow) " if self.wonqrete_mode else " Qommander (Flow) "
                    color = self.COLOR_CYAN
                else:
                    title = " Qonsole (Raw Logs) "
                    color = self.COLOR_YELLOW
                
                window.box()
                window.addstr(0, 2, title, curses.A_BOLD | curses.color_pair(color))
                window.refresh()

            except curses.error:
                # This can happen if the window is resized while drawing
                pass


    def log_main(self, text: str):
        attr = curses.color_pair(self.COLOR_DEFAULT) | curses.A_BOLD
        if "instruQtor" in text: attr = curses.color_pair(self.COLOR_GREEN)
        elif "construQtor" in text: attr = curses.color_pair(self.COLOR_CYAN)
        elif "inspeQtor" in text: attr = curses.color_pair(self.COLOR_MAGENTA)
        elif "Qrane" in text: attr = curses.color_pair(self.COLOR_WHITE)
        self.top_win_buffer.append((text, attr))
        self._append_to_win(self.top_win, text, attr, buffer_only=False)

    def log_agent(self, text: str):
        if not self.show_qonsole or not self.bottom_win: return
        attr = curses.color_pair(self.COLOR_DEFAULT)
        if "error" in text.lower(): attr = curses.color_pair(self.COLOR_RED)
        self._append_to_win(self.bottom_win, text, attr)

    def get_key_nonblocking(self):
        try:
            return self.stdscr.getch()
        except curses.error:
             return -1


    def get_input_blocking(self, prompt: str) -> str:
        """Used for checkpoints, blocks execution."""
        self.log_main(prompt)
        h, w = self.stdscr.getmaxyx()
        
        # Position the input box at the bottom of the main window area
        input_win_h, input_win_w = 3, w
        input_win_y, input_win_x = h - input_win_h -1, 0
        
        try:
            # Create a temporary window for input
            input_win = curses.newwin(input_win_h, input_win_w, input_win_y, input_win_x)
            input_win.box()
            input_win.addstr(1, 2, "> ")
            
            self.stdscr.nodelay(False)
            curses.echo()
            curses.curs_set(1)
            
            input_win.refresh()
            inp_str = input_win.getstr(1, 4, input_win_w - 6).decode('utf-8').strip()
            
        except curses.error:
            inp_str = "" # Return empty on error
        finally:
            # Restore previous state
            curses.noecho()
            curses.curs_set(0)
            self.stdscr.nodelay(True)
            
            # This is crucial: redraw the main screen to erase the input box
            self.stdscr.touchwin()
            self.stdscr.refresh()
            self.setup_windows()

        return inp_str


    def suspend_and_run(self, cmd_list):
        """Temporarily suspends curses to run an external command."""
        try:
            curses.def_prog_mode()
            curses.endwin()
            subprocess.run(cmd_list, check=False)
        except (subprocess.SubprocessError, OSError) as e:
            # Log this error? For now, we just ensure TUI resumes.
            pass
        finally:
            # Restore the TUI
            curses.reset_prog_mode()
            # In modern curses, re-initializing might be safer
            self.stdscr = curses.initscr() 
            self.stdscr.refresh()
            self.setup_windows()

