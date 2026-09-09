"""Put the repo root on sys.path so `backend` imports resolve under pytest.

`pyproject.toml` declares no `[build-system]`, so the project is never installed
into the virtualenv. `uv run python -m pytest` worked only because `-m` happens
to prepend the CWD, while the bare `uv run pytest` console script does not —
so the documented command in CHANGELOG-v6.md ("uv run pytest") could not
actually collect the suite. This makes both invocations work.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
