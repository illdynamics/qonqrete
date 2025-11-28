# qrane/tui.py - Placeholder
# This file is not currently used in the primary headless workflow.
# TUI functionality can be re-implemented here in the future.

class TUI:
    def __init__(self, *args, **kwargs):
        print("[WARN] TUI class is a placeholder and not implemented.")
        pass

    def add_log_line(self, text: str):
        pass

    def set_status(self, text: str, style: int):
        pass

    def prompt_user(self, prompt: str) -> str:
        return ""

    def display_reqap(self, content: str):
        pass

    def close(self):
        pass