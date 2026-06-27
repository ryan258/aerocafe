"""Make factory.py importable from tests (it lives one dir up from tests/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
