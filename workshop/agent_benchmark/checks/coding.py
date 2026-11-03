"""Trusted local check; generated code runs with the user's permissions."""

import importlib.util
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "calculator.py"
spec = importlib.util.spec_from_file_location("calculator", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.total([]) == 0
assert module.total([1, 2, 3]) == 6
assert module.total([-2, 1]) == -1
