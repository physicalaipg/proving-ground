"""Allow the repository's uninstalled packages with the pytest console script."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
