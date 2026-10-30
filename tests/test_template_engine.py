import json
import tomllib

from click.testing import CliRunner

from workshop.cli import cli


def test_builtin_template_creates_project(tmp_path):
    result = CliRunner().invoke(
        cli,
        [
            "template-engine",
            "create",
            "python-project",
            "--no-input",
            "--value",
            "project_name=My Project",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    project = tmp_path / "my_project"
    assert "My Project" in (project / "README.md").read_text()
    assert (
        tomllib.loads((project / "pyproject.toml").read_text())["project"]["name"]
        == "my_project"
    )


def test_local_template_hooks_do_not_run(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "cookiecutter.json").write_text(json.dumps({"name": "example"}))
    directory = template / "{{cookiecutter.name}}"
    directory.mkdir()
    (directory / "hello.txt").write_text("Hello {{ cookiecutter.name }}")
    hooks = template / "hooks"
    hooks.mkdir()
    (hooks / "post_gen_project.py").write_text("raise Exception('hook ran')")
    result = CliRunner().invoke(
        cli,
        [
            "template-engine",
            "create",
            str(template),
            "--no-input",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "example" / "hello.txt").read_text() == "Hello example"


def test_duplicate_project_is_not_overwritten(tmp_path):
    args = [
        "template-engine",
        "create",
        "python-project",
        "--no-input",
        "--output-dir",
        str(tmp_path),
    ]
    runner = CliRunner()
    assert runner.invoke(cli, args).exit_code == 0
    result = runner.invoke(cli, args)
    assert result.exit_code != 0
    assert (tmp_path / "example_project" / "README.md").exists()


def test_invalid_template_and_value(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["template-engine", "create", "https://example.com/template"]
    )
    assert result.exit_code != 0
    assert "local directory" in result.output
    result = runner.invoke(
        cli, ["template-engine", "create", "python-project", "--value", "invalid"]
    )
    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output


def test_list_templates():
    result = CliRunner().invoke(cli, ["template-engine", "list"])
    assert result.exit_code == 0
    assert "python-project" in result.output
