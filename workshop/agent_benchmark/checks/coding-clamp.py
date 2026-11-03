import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "numbers", Path(sys.argv[1]) / "numbers.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.clamp(-3, 0, 10) == 0
assert module.clamp(15, 0, 10) == 10
assert module.clamp(5, 0, 10) == 5
