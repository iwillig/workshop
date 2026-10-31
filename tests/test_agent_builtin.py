from workshop.agent.builtin_tools import BuiltinTools
from workshop.agent.environments import LocalEnvironment


def test_read_edit_and_shell(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one\ntwo\n")
    tools = BuiltinTools(LocalEnvironment(cwd=str(tmp_path)))
    assert (
        "two"
        in tools.execute({"tool": "read", "arguments": {"path": "a.txt", "offset": 2}})[
            "output"
        ]
    )
    assert (
        tools.execute(
            {
                "tool": "edit",
                "arguments": {"path": "a.txt", "old_text": "two", "new_text": "three"},
            }
        )["returncode"]
        == 0
    )
    assert path.read_text() == "one\nthree\n"
    assert (
        "ok"
        in tools.execute({"tool": "bash", "arguments": {"command": "echo ok"}})[
            "output"
        ]
    )


def test_read_edit_reject_escape_and_ambiguous_edits(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside").write_text("secret")
    (root / "link").symlink_to(tmp_path / "outside")
    (root / "a.txt").write_text("same same")
    tools = BuiltinTools(LocalEnvironment(cwd=str(root)))
    assert (
        tools.execute({"tool": "read", "arguments": {"path": "link"}})["returncode"]
        != 0
    )
    assert (
        tools.execute({"tool": "read", "arguments": {"path": "../outside"}})[
            "returncode"
        ]
        != 0
    )
    assert (
        tools.execute(
            {
                "tool": "edit",
                "arguments": {"path": "a.txt", "old_text": "same", "new_text": "x"},
            }
        )["returncode"]
        != 0
    )
    assert (root / "a.txt").read_text() == "same same"
