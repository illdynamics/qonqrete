import unittest
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "worqer"))

import lib_ai

class ChunkingRobustnessTests(unittest.TestCase):
    def test_ack_normalization_basic(self):
        ack = "ACK CHUNK 1/1 HASH abc"
        self.assertEqual(lib_ai._normalize_ack_response(ack), ack)
        self.assertEqual(lib_ai._normalize_ack_response("  " + ack + "  "), ack)

    def test_ack_normalization_with_think(self):
        ack = "ACK CHUNK 1/1 HASH abc"
        raw = f"<think>\nReasoning here...\n</think>\n{ack}"
        self.assertEqual(lib_ai._normalize_ack_response(raw), ack)

    def test_ack_normalization_with_multi_think(self):
        ack = "ACK CHUNK 1/1 HASH abc"
        raw = f"<think>Reasoning 1</think><think>Reasoning 2</think>{ack}"
        self.assertEqual(lib_ai._normalize_ack_response(raw), ack)

    def test_ack_normalization_with_stray_think_tag(self):
        ack = "ACK CHUNK 1/1 HASH abc"
        # If there's just a <think> tag at the start but no content after it except the ACK
        raw = f"<think>{ack}"
        self.assertEqual(lib_ai._normalize_ack_response(raw), ack)

    def test_ack_normalization_case_insensitive(self):
        ack = "ACK CHUNK 1/1 HASH abc"
        raw = f"<THINK>Reasoning</THINK>{ack}"
        self.assertEqual(lib_ai._normalize_ack_response(raw), ack)

if __name__ == "__main__":
    unittest.main()
