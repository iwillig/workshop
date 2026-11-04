import importlib.util
import sys
from pathlib import Path

workspace = sys.argv[1]
sys.path.insert(0, workspace)
spec = importlib.util.spec_from_file_location(
    "stats", Path(workspace) / "stats.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.mean([1, 2, 3]) == 2
assert module.mean([5]) == 5
assert module.mean([]) is None
