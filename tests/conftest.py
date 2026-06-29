"""Test fixtures for Neuron."""

import os
import sys
import tempfile

# Ensure src/ is on path for the package import
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
