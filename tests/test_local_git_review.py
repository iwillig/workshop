import subprocess

import pytest


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "file.txt").write_text("base\n")
    git(tmp_path, "add", "file.txt")
    git(tmp_path, "commit", "-m", "base")
    git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "file.txt").write_text("committed\n")
    git(tmp_path, "commit", "-am", "feature")
    return tmp_path


def test_snapshot_pins_merge_base_and_reports_dirty(repo):
    from research_context.git_review import GitReview

    (repo / "file.txt").write_text("uncommitted\n")
    (repo / "new.txt").write_text("untracked\n")
    review = GitReview(repo, "main")
    snapshot = review.start()
    assert snapshot["branch"] == "feature"
    assert snapshot["head"] == git(repo, "rev-parse", "HEAD")
    assert snapshot["merge_base"] == git(repo, "rev-parse", "main")
    assert snapshot["dirty"] is True
    assert review.context() == snapshot


def test_read_file_uses_pinned_commits_not_worktree(repo):
    from research_context.git_review import GitReview

    review = GitReview(repo, "main")
    snapshot = review.start()
    (repo / "file.txt").write_text("working tree secret\n")
    assert review.read_file(snapshot["head"], "file.txt")["lines"] == [
        {"line": 1, "text": "committed"}
    ]
    assert review.read_file(snapshot["merge_base"], "file.txt")["lines"] == [
        {"line": 1, "text": "base"}
    ]
    with pytest.raises(ValueError):
        review.read_file(snapshot["head"], "../file.txt")
    with pytest.raises(ValueError):
        review.read_file("HEAD", "file.txt")


def test_read_file_pagination_binary_and_symlink(repo):
    from research_context.git_review import GitReview

    (repo / "lines.txt").write_text("one\ntwo\nthree\n")
    (repo / "binary.dat").write_bytes(b"hello\0world")
    (repo / "link").symlink_to("lines.txt")
    git(repo, "add", "lines.txt", "binary.dat", "link")
    git(repo, "commit", "-m", "files")
    review = GitReview(repo, "main")
    head = review.start()["head"]
    first = review.read_file(head, "lines.txt", limit=2)
    assert first == {
        "lines": [{"line": 1, "text": "one"}, {"line": 2, "text": "two"}],
        "complete": False,
        "next_offset": 3,
    }
    last = review.read_file(head, "lines.txt", offset=3)
    assert last["lines"] == [{"line": 3, "text": "three"}]
    assert last["complete"] is True
    with pytest.raises(ValueError, match="Binary"):
        review.read_file(head, "binary.dat")
    with pytest.raises(ValueError, match="regular"):
        review.read_file(head, "link")


def test_diff_uses_snapshot_and_excludes_uncommitted_changes(repo):
    from research_context.git_review import GitReview

    review = GitReview(repo, "main")
    snapshot = review.start()
    (repo / "file.txt").write_text("working tree only\n")
    result = review.diff()
    assert result["base"] == snapshot["merge_base"]
    assert result["head"] == snapshot["head"]
    assert "+committed" in result["patch"]
    assert "working tree only" not in result["patch"]
    assert result["complete"] is True


def test_diff_continues_beyond_output_cap(repo):
    from research_context.git_review import GitReview

    (repo / "large.txt").write_text("".join(
        f"line {i:05d} xxxxxxxxxx\n" for i in range(6000)
    ))
    git(repo, "add", "large.txt")
    git(repo, "commit", "-m", "large diff")
    review = GitReview(repo, "main")
    review.start()
    offset = 0
    pages = []
    while True:
        page = review.diff(offset=offset, limit=10000)
        pages.append(page["patch"])
        if page["complete"]:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    patch = "".join(pages)
    assert "+line 00000" in patch
    assert "+line 05999" in patch
    assert len(patch) > 50000


def test_diff_can_be_filtered_to_one_changed_path(repo):
    from research_context.git_review import GitReview

    (repo / "other.txt").write_text("new file\n")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-m", "other file")
    review = GitReview(repo, "main")
    review.start()
    patch = review.diff(path="file.txt")["patch"]
    assert "file.txt" in patch
    assert "other.txt" not in patch
    with pytest.raises(ValueError):
        review.diff(path="../other.txt")


def test_native_diff_tool_bounds_serialized_output(repo):
    from research_context.git_review_tools import GitReviewTools

    (repo / "escaped.txt").write_text(('"\\\\' * 12000) + "\n")
    git(repo, "add", "escaped.txt")
    git(repo, "commit", "-m", "escaped output")
    provider = GitReviewTools(repo, "main")
    provider.start_run()
    result = provider.execute({"tool": "git_review_diff", "arguments": {}})
    assert len(result["output"]) <= 40000
    assert result["returncode"] == 0


def test_native_diff_tool_accepts_patch_pagination(repo):
    import json
    from research_context.git_review_tools import GitReviewTools

    provider = GitReviewTools(repo, "main")
    provider.start_run()
    result = provider.execute({"tool": "git_review_diff", "arguments": {
        "offset": 0, "limit": 10
    }})
    assert result["returncode"] == 0
    assert json.loads(result["output"])["next_offset"] == 10


def test_changed_files_pages_and_reports_renames(repo):
    from research_context.git_review import GitReview

    git(repo, "checkout", "main", "--", "file.txt")
    git(repo, "mv", "file.txt", "renamed.txt")
    (repo / "added.txt").write_text("new\n")
    git(repo, "add", "added.txt")
    git(repo, "commit", "-m", "rename and add")
    review = GitReview(repo, "main")
    review.start()
    first = review.changed_files(offset=0, limit=1)
    assert len(first["files"]) == 1
    assert first["complete"] is False
    second = review.changed_files(offset=first["next_offset"], limit=1)
    files = first["files"] + second["files"]
    assert {item["status"] for item in files} == {"A", "R"}
    rename = next(item for item in files if item["status"] == "R")
    assert rename["path"] == "renamed.txt"
    assert rename["previous_path"] == "file.txt"
    assert second["complete"] is True


def test_inventory_pages_past_previous_capture_cap(repo):
    from research_context.git_review import GitReview

    for index in range(1000):
        (repo / f"added-{index:04d}-{'x' * 55}.txt").write_text("x\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "many files")
    review = GitReview(repo, "main")
    review.start()
    page = review.changed_files(offset=990, limit=20)
    assert len(page["files"]) == 11
    assert page["complete"] is True


def test_search_uses_pinned_head_and_literal_matching(repo):
    from research_context.git_review import GitReview

    (repo / "other.txt").write_text("alpha.*beta\nalphaZZbeta\n")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-m", "search fixture")
    review = GitReview(repo, "main")
    review.start()
    (repo / "other.txt").write_text("working tree only\n")
    result = review.search("alpha.*beta")
    assert result["matches"] == [
        {"path": "other.txt", "line": 1, "text": "alpha.*beta"}
    ]
    assert result["complete"] is True
    assert review.search("working tree only")["matches"] == []


def test_search_pages_through_pinned_matches(repo):
    from research_context.git_review import GitReview

    (repo / "matches.txt").write_text("needle one\nneedle two\nneedle three\n")
    git(repo, "add", "matches.txt")
    git(repo, "commit", "-m", "matches")
    review = GitReview(repo, "main")
    review.start()
    first = review.search("needle", offset=0, limit=2)
    assert [item["line"] for item in first["matches"]] == [1, 2]
    assert first["complete"] is False
    assert first["next_offset"] == 2
    last = review.search("needle", offset=first["next_offset"], limit=2)
    assert [item["line"] for item in last["matches"]] == [3]
    assert last["complete"] is True
    assert last["next_offset"] is None


def test_search_filters_literal_repository_path(repo):
    from research_context.git_review import GitReview

    (repo / "a.txt").write_text("needle a\n")
    (repo / "b.txt").write_text("needle b\n")
    git(repo, "add", "a.txt", "b.txt")
    git(repo, "commit", "-m", "search files")
    review = GitReview(repo, "main")
    review.start()
    matches = review.search("needle", path="a.txt")["matches"]
    assert [match["path"] for match in matches] == ["a.txt"]
    with pytest.raises(ValueError):
        review.search("needle", path="../a.txt")


def test_review_tools_handle_unusual_tracked_paths(repo):
    from research_context.git_review import GitReview

    name = "odd\nname-é.txt"
    (repo / name).write_text("needle unicode\n")
    git(repo, "add", name)
    git(repo, "commit", "-m", "unusual filename")
    review = GitReview(repo, "main")
    head = review.start()["head"]
    assert review.read_file(head, name)["lines"][0]["text"] == "needle unicode"
    assert review.search("needle")["matches"][0]["path"] == name
    assert name in [item["path"] for item in review.changed_files()["files"]]


def test_search_pages_past_previous_capture_cap(repo):
    from research_context.git_review import GitReview

    (repo / "many.txt").write_text("".join(
        f"needle {i:05d} xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" for i in range(2000)
    ))
    git(repo, "add", "many.txt")
    git(repo, "commit", "-m", "many matches")
    review = GitReview(repo, "main")
    review.start()
    page = review.search("needle", offset=1900, limit=100)
    assert page["matches"][0]["line"] == 1901
    assert page["matches"][-1]["line"] == 2000
    assert page["complete"] is True


def test_native_provider_starts_and_exposes_pinned_context(repo):
    import json
    from research_context.git_review_tools import GitReviewTools

    provider = GitReviewTools(repo, "main")
    provider.start_run()
    result = provider.execute({"tool": "git_review_context", "arguments": {}})
    assert result["returncode"] == 0
    assert json.loads(result["output"])["branch"] == "feature"
    assert {tool.name for tool in provider.tools} == {
        "git_review_context", "git_review_diff", "git_read_file", "git_search"
    }
    assert provider.finish_run()["changed"] is False


def test_configuration_accepts_git_tools_only_for_local(tmp_path):
    from workshop.config import load_workshop_config

    path = tmp_path / "workshop.yaml"
    template = (
        "version: 1\ngit: {base_ref: main}\nagents:\n  review:\n"
        "    model: {model_name: fake, protocol: native}\n"
        "    environment: {environment_class: ENVIRONMENT}\n"
        "    tools: {git_review_context: {}, git_read_file: {}}\n"
    )
    path.write_text(template.replace("ENVIRONMENT", "local"))
    assert "review" in load_workshop_config(path)["agents"]
    path.write_text(template.replace("ENVIRONMENT", "docker"))
    with pytest.raises(ValueError, match="local"):
        load_workshop_config(path)


def test_provider_reports_requested_and_unrequested_files(repo):
    from research_context.git_review_tools import GitReviewTools

    provider = GitReviewTools(repo, "main")
    provider.start_run()
    provider.execute(
        {"tool": "git_review_diff", "arguments": {"inventory": True}}
    )
    report = provider.coverage_summary()
    assert report["inventory_complete"] is True
    assert report["unrequested_files"] == ["file.txt"]
    provider.execute({"tool": "git_read_file", "arguments": {
        "commit": provider.review.context()["head"], "path": "file.txt"
    }})
    report = provider.coverage_summary()
    assert report["file_reads"] == ["file.txt"]
    assert report["unrequested_files"] == []


def test_agent_starts_review_and_reports_ref_check(repo, monkeypatch):
    from types import SimpleNamespace
    from workshop.agent.default_agent import DefaultAgent
    from workshop.agent.environments import LocalEnvironment
    from research_context.git_review_tools import GitReviewTools

    model = SimpleNamespace(config=SimpleNamespace(protocol="native"))
    agent = DefaultAgent(model, LocalEnvironment(cwd=str(repo)))
    provider = GitReviewTools(repo, "main")
    agent.tool_providers.append(provider)

    def run(task, **kwargs):
        assert provider.review.context()["branch"] == "feature"
        return {"exit_status": "Submitted", "submission": "done"}

    monkeypatch.setattr(agent, "_run", run)
    result = agent.run("review")
    assert result["git_review"]["refs"]["changed"] is False


def test_cli_prints_runtime_review_metadata(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from click.testing import CliRunner
    from workshop.cli import cli

    path = tmp_path / "workshop.yaml"
    path.write_text(
        "version: 1\ndefault_agent: x\nagents:\n  x:\n"
        "    model: {model_name: fake}\n"
    )
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(run=lambda task: {
            "exit_status": "Submitted", "submission": "done",
            "git_review": {"refs": {"changed": True, "error": None},
                           "coverage": []},
        }),
    )
    result = CliRunner().invoke(
        cli, ["--workshop-config", str(path), "agent", "run", "-t", "review"]
    )
    assert result.exit_code == 0, result.output
    assert '"changed": true' in result.output
    assert "Git review metadata" in result.output


def test_project_includes_branch_reviewer_configuration():
    from workshop.config import load_workshop_config

    project = load_workshop_config("workshop.yaml")
    assert project["git"]["base_ref"]
    tools = project["agents"]["branch-reviewer"]["tools"]
    assert set(tools) == {
        "git_review_context", "git_review_diff", "git_read_file", "git_search"
    }


def test_final_check_detects_branch_switch_at_same_commit(repo):
    from research_context.git_review import GitReview

    review = GitReview(repo, "main")
    review.start()
    git(repo, "checkout", "-b", "same-commit")
    assert review.final_check()["changed"] is True


def test_final_check_detects_moved_refs(repo):
    from research_context.git_review import GitReview

    review = GitReview(repo, "main")
    snapshot = review.start()
    assert review.final_check() == {"changed": False, "error": None}
    (repo / "file.txt").write_text("new commit\n")
    git(repo, "commit", "-am", "new")
    assert review.final_check()["changed"] is True
    assert review.context() == snapshot


def test_snapshot_uses_bounded_status_output(repo, monkeypatch):
    import workshop.agent.environments as environments
    from research_context.git_review import GitReview

    original = environments._run
    commands = []

    def bounded(command, cwd, env, timeout):
        commands.append(command)
        return original(command, cwd, env, timeout)

    monkeypatch.setattr(environments, "_run", bounded)
    (repo / "dirty.txt").write_text("untracked")
    snapshot = GitReview(repo, "main").start()
    assert snapshot["dirty"] is True
    assert any("status" in command for command in commands)


def test_model_free_review_runs_selected_tools(repo, monkeypatch):
    import json
    import llm
    from types import SimpleNamespace
    from workshop.agent_config import build_agent

    class Response:
        def __init__(self, calls):
            self.calls = calls

        def text(self):
            return "" if self.calls else "review complete"

        def tool_calls(self):
            return self.calls

        def usage(self):
            return SimpleNamespace(input=0, output=0)

    class Conversation:
        def __init__(self):
            self.requests = []
            self.responses = []

        def prompt(self, prompt, **kwargs):
            self.requests.append(kwargs)
            calls = []
            if len(self.requests) == 1:
                calls.append(llm.ToolCall(
                    name="git_review_context", arguments={}, tool_call_id="1"
                ))
            response = Response(calls)
            self.responses.append(response)
            return response

    class Backend:
        def conversation(self):
            return Conversation()

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    config = {
        "agent": {"agent_class": "default"},
        "environment": {"cwd": str(repo)},
        "model": {"protocol": "native"},
        "tools": {"git_review_context": {}},
        "workshop": {"git": {"base_ref": "main"}},
    }
    agent = build_agent(config)
    result = agent.run("review")
    assert result["exit_status"] == "Submitted"
    assert result["git_review"]["refs"]["changed"] is False
    observation = (
        agent.model._conversation.requests[1]["tool_results"][0].output
    )
    assert json.loads(observation)["branch"] == "feature"
    assert {tool.name for tool in agent.model.native_tools} == {
        "git_review_context"
    }


def test_supervised_worker_captures_git_review(repo):
    import sys
    from workshop.agent.supervised import SupervisedAgent

    script = '''
from types import SimpleNamespace
import workshop.agent.models as models
from workshop.agent.live_worker import main
class Response:
    def text(self): return "done"
    def tool_calls(self): return []
    def usage(self): return SimpleNamespace(input=0, output=0)
class Conversation:
    def __init__(self): self.responses = []
    def prompt(self, *args, **kwargs):
        response = Response()
        self.responses.append(response)
        return response
class Backend:
    def conversation(self): return Conversation()
models.llm.get_model = lambda _: Backend()
main()
'''
    config = {
        "agent": {"agent_class": "default"},
        "environment": {"cwd": str(repo)},
        "model": {"protocol": "native"},
        "tools": {"git_review_context": {}},
        "workshop": {"git": {"base_ref": "main"}},
    }
    agent = SupervisedAgent(config, command=[sys.executable, "-c", script])
    result = agent.run("review")
    assert result["exit_status"] == "Submitted"
    assert result["git_review"]["context"]["branch"] == "feature"
    assert result["git_review"]["refs"]["changed"] is False


def test_unrelated_history_is_rejected(repo):
    from research_context.git_review import GitReview

    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "rm", "-rf", ".")
    (repo / "unrelated.txt").write_text("new history\n")
    git(repo, "add", "unrelated.txt")
    git(repo, "commit", "-m", "unrelated")
    with pytest.raises(ValueError, match="merge base"):
        GitReview(repo, "main").start()


def test_final_check_reports_deleted_base(repo):
    from research_context.git_review import GitReview

    review = GitReview(repo, "main")
    review.start()
    git(repo, "branch", "-D", "main")
    result = review.final_check()
    assert result["changed"] is None
    assert result["error"]


def test_snapshot_rejects_detached_and_missing_base(repo):
    from research_context.git_review import GitReview

    with pytest.raises(ValueError, match="base"):
        GitReview(repo, "does-not-exist").start()
    git(repo, "checkout", "--detach")
    with pytest.raises(ValueError, match="detached"):
        GitReview(repo, "main").start()
