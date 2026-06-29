"""Smoke tests for the MCP server."""

import os
import sys
import tempfile

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def test_import_package():
    """Verify the neuron package imports correctly."""
    import neuron
    assert hasattr(neuron, "__version__")
    assert neuron.__version__ == "3.2.0"


def test_import_server():
    """Verify the server module imports without error."""
    from importlib import reload
    import neuron.server
    # Just verify it's importable — don't start the server
    assert hasattr(neuron.server, "main")


def test_import_engine():
    """Verify the engine module imports correctly."""
    import neuron.engine
    assert hasattr(neuron.engine, "Neuron")
    assert hasattr(neuron.engine, "create_local")
    assert hasattr(neuron.engine, "create_openai")
