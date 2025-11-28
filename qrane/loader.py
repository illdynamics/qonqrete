#!/usr/bin/env python3
# qrane/loader.py - Visual utilities for the Qrane orchestrator
import sys
import time
import threading

class Colors:
    B = "\033[1;34m"; C = "\033[1;36m"; D = "\033[0;34m"; R = "\033[0m"
    YELLOW = "\033[1;33m"; MAGENTA = "\033[1;35m"; RED = "\033[1;31m"
    BOLD = "\033[1m"; GREEN = "\033[1;32m"; WHITE = "\033[1;37m"

class Spinner:
    """A threaded spinner replicating the style of wonqpipe.zsh."""
    def __init__(self, prefix: str = "", message: str = "", delay: float = 0.1):
        self.frames = [
            "﴾✇---------﴿", "﴾-✇--------﴿", "﴾--✇-------﴿", "﴾---✇------﴿",
            "﴾----✇-----﴿", "﴾-----✇----﴿", "﴾------✇---﴿", "﴾-------✇--﴿",
            "﴾--------✇-﴿", "﴾---------✇﴿"
        ]
        self.delay = delay
        self.running = False
        self.spinner_thread = None
        self.prefix = prefix
        self.message = message

    def start(self):
        self.running = True
        self.spinner_thread = threading.Thread(target=self._spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while self.running:
            frame = self.frames[i % len(self.frames)]
            # [CHANGE] Reduced spaces before ⸎ from 3 to 2
            output = f"{Colors.B}{self.prefix} {frame}  ⸎  {Colors.C}{self.message}{Colors.R}"
            sys.stdout.write(f"\r{output}")
            sys.stdout.flush()
            time.sleep(self.delay)
            i += 1
