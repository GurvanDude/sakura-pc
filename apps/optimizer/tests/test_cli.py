"""Tests du point d'entrée de Sakura Optimizer."""
import subprocess
import sys
from pathlib import Path

import sakura_opt

OPTIMIZER = Path(__file__).resolve().parents[1] / 'optimizer.py'


def test_monitor():
    result = subprocess.run([sys.executable, str(OPTIMIZER), 'monitor'], capture_output=True, text=True)

    assert result.returncode == 0


def test_version():
    assert sakura_opt.__version__ == '0.1.0'
