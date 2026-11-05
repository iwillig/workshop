from pathlib import Path
import os
import subprocess
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_builds_before_trusted_publication():
    workflow = yaml.load(
        (ROOT / ".github/workflows/publish.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "llm-workshop"
    assert workflow["on"]["release"]["types"] == ["published"]
    build = workflow["jobs"]["build"]
    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"] == {"id-token": "write"}
    assert any(
        step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
        for step in publish["steps"]
    )
    assert any(
        "python -m build" in step.get("run", "") for step in build["steps"]
    )
    assert any("RELEASE_TAG" in step.get("env", {}) for step in build["steps"])
    assert any(
        step.get("uses", "").startswith("actions/upload-artifact@")
        for step in build["steps"]
    )
    assert any(
        step.get("uses", "").startswith("actions/download-artifact@")
        for step in publish["steps"]
    )


def test_release_tag_guard_accepts_only_matching_version():
    workflow = yaml.load(
        (ROOT / ".github/workflows/publish.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    guard = next(
        step["run"]
        for step in workflow["jobs"]["build"]["steps"]
        if "RELEASE_TAG" in step.get("env", {})
    )
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    for tag, expected in [(f"v{version}", 0), ("v9999.0.0", 1)]:
        result = subprocess.run(
            ["sh", "-c", guard],
            cwd=ROOT,
            env=os.environ | {"RELEASE_TAG": tag},
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected, result.stderr
