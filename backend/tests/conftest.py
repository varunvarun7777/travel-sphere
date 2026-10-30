import os
import sys
import tempfile
from pathlib import Path

# Isolated SQLite file in the system temp dir; never call a real AI API in tests.
_DB = Path(tempfile.gettempdir()) / f"travelsphere_test_{os.getpid()}.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["TRAVELSPHERE_AI"] = "off"
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-0123456789")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
