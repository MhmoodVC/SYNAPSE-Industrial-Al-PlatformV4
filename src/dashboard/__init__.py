"""Presentation layer package for SYNAPSE Streamlit dashboard."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import main

__all__ = ["main"]
