"""Point d'entrée de Sakura AI."""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core import paths  # noqa: E402

ROOT = paths.app("ai")
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

