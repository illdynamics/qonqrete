
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    print("Attempting to import worqer.lib_ai...")
    from worqer import lib_ai
    print("Import successful.")
except Exception as e:
    print(f"Import failed: {e}")
