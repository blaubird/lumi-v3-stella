# pyright: reportMissingImports=false
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_imports() -> None:
    import api  # noqa: F401
    import handlers  # noqa: F401
    import routers  # noqa: F401
    from handlers.ai import AiHandler  # noqa: F401
    from routers import webhook  # noqa: F401

    assert AiHandler is not None
    assert webhook is not None
