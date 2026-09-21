"""Run tests and expose failure details in GitHub check annotations."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
for test, traceback in result.failures + result.errors:
    detail = (test.id() + '\n' + traceback).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=Test failure::' + detail, flush=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
