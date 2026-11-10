"""Every test runs against a throwaway AWLCHEMY_HOME with a generated sample library,
so no real patterns, settings or network access are needed."""
import os
import runpy
import sys
import tempfile
from pathlib import Path

HOME = Path(tempfile.mkdtemp(prefix="awlchemy-test-"))
os.environ["AWLCHEMY_HOME"] = str(HOME)  # must be set before awlchemy.config is imported

TESTS = Path(__file__).resolve().parent
sys.path[:0] = [str(TESTS.parent), str(TESTS)]

_argv = sys.argv
sys.argv = ["make_fixtures.py", str(HOME)]
try:
    runpy.run_path(str(TESTS / "make_fixtures.py"), run_name="__main__")
finally:
    sys.argv = _argv
