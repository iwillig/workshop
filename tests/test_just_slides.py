import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("just") is None, reason="just is required")
def test_slides_recipe_accepts_source_path_and_cleans_up(tmp_path):
    source_dir = tmp_path / "slides with spaces"
    source_dir.mkdir()
    source = source_dir / "my deck.md"
    source.write_text("# Slide\n")
    tools = tmp_path / "tools"
    tools.mkdir()
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    brew = tools / "brew"
    brew.write_text(f"#!/bin/sh\nprintf '%s\\n' '{prefix}'\n")
    brew.chmod(0o755)
    pipenv = prefix / "bin" / "pipenv"
    pipenv.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
    )
    pipenv.chmod(0o755)
    env = os.environ | {"PATH": str(tools) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(
        ["just", "slides", str(source)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["args"][:7] == [
        "run",
        "pandoc",
        "--standalone",
        "--to",
        "slidy",
        "--slide-level=1",
        "--embed-resources",
    ]
    assert "--filter=pandoc-plantuml" in data["args"]
    assert "--metadata=plantuml-format=svg" in data["args"]
    assert str(source) in data["args"]
    assert data["args"][-2:] == ["-o", str(source.with_suffix(".html"))]
    assert not Path(data["cwd"]).exists()


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_SLIDES_INTEGRATION") != "1",
    reason="set WORKSHOP_SLIDES_INTEGRATION=1 for a real Pandoc build",
)
def test_real_slides_build_embeds_plantuml(tmp_path):
    source = tmp_path / "diagram.md"
    source.write_text("# Example\n\n```plantuml\nAlice -> Bob: Hello\n```\n")
    result = subprocess.run(
        ["just", "slides", str(source)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert "data:image/svg+xml" in source.with_suffix(".html").read_text()
    assert not (tmp_path / "plantuml-images").exists()


@pytest.mark.skipif(shutil.which("just") is None, reason="just is required")
def test_slides_rejects_non_markdown_input(tmp_path):
    source = tmp_path / "slide.html"
    source.write_text("existing")
    result = subprocess.run(
        ["just", "slides", str(source)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert source.read_text() == "existing"
