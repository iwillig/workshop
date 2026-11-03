import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "text", Path(sys.argv[1]) / "text.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.normalize("  Hello  ") == "hello"
assert module.normalize("\tABC\n") == "abc"
assert module.normalize("") == ""
