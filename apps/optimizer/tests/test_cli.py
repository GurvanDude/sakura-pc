"""Tests du point d'entrée de Sakura Optimizer."""
import subprocess
import sys
from pathlib import Path

import sakura_opt
from optimizer import build_parser

OPTIMIZER = Path(__file__).resolve().parents[1] / 'optimizer.py'


def test_monitor():
    result = subprocess.run(
        [sys.executable, str(OPTIMIZER), 'monitor', '--once'],
        capture_output=True,
        text=True, encoding="utf-8",
    )

    assert result.returncode == 0


def test_version():
    assert sakura_opt.__version__ == '0.1.0'


def test_commande_diagnose_accepte_minutes_et_json():
    args = build_parser().parse_args(['diagnose', '--minutes', '15', '--json'])

    assert args.command == 'diagnose'
    assert args.minutes == 15
    assert args.json is True
