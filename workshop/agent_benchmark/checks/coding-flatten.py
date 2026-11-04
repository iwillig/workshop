import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "nested", Path(sys.argv[1]) / "nested.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.flatten([[1, 2], [3]]) == [1, 2, 3]
assert module.flatten([]) == []
assert module.flatten([[], [4]]) == [4]
