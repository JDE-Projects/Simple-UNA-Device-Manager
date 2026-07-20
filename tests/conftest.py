"""Put the repo root on sys.path so the tests can import the app module
regardless of how pytest is invoked (bare `pytest` does not add it)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
