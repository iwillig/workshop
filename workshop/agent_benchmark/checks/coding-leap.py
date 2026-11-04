import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "years", Path(sys.argv[1]) / "years.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.is_leap_year(2000) is True
assert module.is_leap_year(1900) is False
assert module.is_leap_year(2024) is True
assert module.is_leap_year(2023) is False
assert module.is_leap_year(2100) is False
