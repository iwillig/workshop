import json

import pytest
from click.testing import CliRunner
from git import Repo

from research_context.__main__ import cli


@pytest.fixture
def repository(tmp_path):
    repo = Repo.init(tmp_path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test Author")
        config.set_value("user", "email", "test@example.com")
    (tmp_path / "file.txt").write_text("original\n")
    repo.index.add(["file.txt"])
    repo.index.commit("Initial commit")
    yield repo
    repo.close()


def invoke(*args):
    return CliRunner().invoke(cli, ["git", *args])


def test_status_and_diff(repository):
    root = repository.working_tree_dir
    from pathlib import Path

    path = Path(root)
    (path / "file.txt").write_text("staged\n")
    repository.index.add(["file.txt"])
    (path / "file.txt").write_text("unstaged\n")
    (path / "new.txt").write_text("new\n")
    result = invoke("status", "--repo", root)
    assert result.exit_code == 0, result.output
    changes = {
        item["path"]: item for item in json.loads(result.output)["changes"]
    }
    assert (changes["file.txt"]["index"], changes["file.txt"]["worktree"]) == (
        "M",
        "M",
    )
    assert changes["new.txt"]["index"] == "?"
    for flags, expected in [((), "+unstaged"), (("--staged",), "+staged")]:
        result = invoke("diff", "--repo", root, *flags)
        assert result.exit_code == 0, result.output
        patch = json.loads(result.output)["patch"]
        assert expected in patch
        assert "new.txt" not in patch


def test_log_and_nested_directory(repository):
    from pathlib import Path

    nested = Path(repository.working_tree_dir) / "nested"
    nested.mkdir()
    result = invoke("log", "--repo", str(nested), "--limit", "1")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["message"] == "Initial commit"


def test_empty_and_invalid_repositories(tmp_path):
    repo = Repo.init(tmp_path / "empty")
    repo.close()
    result = invoke("log", "--repo", str(tmp_path / "empty"))
    assert result.exit_code == 0
    assert json.loads(result.output) == []
    result = invoke("status", "--repo", str(tmp_path))
    assert result.exit_code != 0
    assert "Not a Git repository" in result.output
