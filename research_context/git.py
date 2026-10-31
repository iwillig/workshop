"""Read local Git repository state for research and review."""

import json

import click
from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo


def open_repo(path):
    try:
        repo = Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise click.ClickException(f"Not a Git repository: {path}") from exc
    if repo.bare:
        repo.close()
        raise click.ClickException("Bare repositories are not supported.")
    return repo


def output(value):
    click.echo(json.dumps(value, indent=2))


@click.group(name="git")
def git_commands():
    """Review a local Git repository without modifying it."""


def repository_option(function):
    return click.option(
        "--repo",
        "path",
        type=click.Path(file_okay=False),
        default=".",
        show_default=True,
        help="Repository directory or a directory within it.",
    )(function)


@git_commands.command("status")
@repository_option
def status(path):
    """Show branch and working-tree changes as JSON."""
    try:
        with open_repo(path) as repo:
            raw = repo.git.status("--porcelain=v1", "-z", "--untracked-files=all")
            parts = raw.split("\0") if raw else []
            changes = []
            i = 0
            while i < len(parts) and parts[i]:
                entry = parts[i]
                change = {"index": entry[0], "worktree": entry[1], "path": entry[3:]}
                i += 1
                if "R" in entry[:2] or "C" in entry[:2]:
                    change["original_path"] = parts[i]
                    i += 1
                changes.append(change)
            branch = None if repo.head.is_detached else repo.active_branch.name
            output(
                {"root": repo.working_tree_dir, "branch": branch, "changes": changes}
            )
    except GitCommandError as exc:
        raise click.ClickException(f"Git status failed: {exc.stderr.strip()}") from exc


@git_commands.command("diff")
@repository_option
@click.option(
    "--staged", is_flag=True, help="Show staged rather than unstaged changes."
)
def diff(path, staged):
    """Show a staged or unstaged patch as JSON; untracked files are excluded."""
    try:
        with open_repo(path) as repo:
            args = ["--no-ext-diff", "--no-textconv"]
            if staged:
                args.append("--cached")
            args.append("--")
            output({"staged": staged, "patch": repo.git.diff(*args)})
    except GitCommandError as exc:
        raise click.ClickException(f"Git diff failed: {exc.stderr.strip()}") from exc


@git_commands.command("log")
@repository_option
@click.option("--limit", type=click.IntRange(min=1), default=10, show_default=True)
def log(path, limit):
    """Show recent commits reachable from HEAD as JSON."""
    try:
        with open_repo(path) as repo:
            if not repo.head.is_valid():
                output([])
                return
            output(
                [
                    {
                        "id": commit.hexsha,
                        "author": commit.author.name,
                        "authored_at": commit.authored_datetime.isoformat(),
                        "message": commit.message.rstrip(),
                    }
                    for commit in repo.iter_commits("HEAD", max_count=limit)
                ]
            )
    except GitCommandError as exc:
        raise click.ClickException(f"Git log failed: {exc.stderr.strip()}") from exc
