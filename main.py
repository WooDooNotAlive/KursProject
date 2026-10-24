"""Точка входа приложения.

Запуск из корня проекта::

    python main.py
    python main.py --date "2021-12-31 16:44:00" --period M
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.main import main  # noqa: E402

if __name__ == "__main__":
    main()
