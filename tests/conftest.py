"""Test setup supports `pytest` without installing the package as a wheel."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
