"""Built-in native tools for workspace files and command execution."""

import os
from pathlib import Path

import llm

from workshop.agent.environments import LocalEnvironment


class BuiltinTools:
    def __init__(self, environment):
        self.environment = environment
        self.tools = [
            llm.Tool(
                name="read",
                description=(
                    "Read a UTF-8 file in the workspace with optional "
                    "line range."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 1},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            llm.Tool(
                name="edit",
                description=(
                    "Replace one exact, unique text match in a workspace file."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_text": {"type": "string", "minLength": 1},
                        "new_text": {"type": "string"},
                    },
                    "required": ["path", "old_text", "new_text"],
                    "additionalProperties": False,
                },
            ),
            llm.Tool(
                name="bash",
                description=(
                    "Run a shell command in the execution environment."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
        ]
        if not isinstance(environment, LocalEnvironment):
            self.tools = [tool for tool in self.tools if tool.name == "bash"]

    def _path(self, value):
        if not isinstance(self.environment, LocalEnvironment):
            raise ValueError(
                "read and edit currently require the local environment"
            )
        root = Path(self.environment.config.cwd or os.getcwd()).resolve(
            strict=True
        )
        path = (root / value).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("Path is outside the workspace")
        if not path.is_file():
            raise ValueError("Path must be a file")
        return path

    def execute(self, action):
        name = action.get("tool")
        args = action.get("arguments", {})
        try:
            if not isinstance(args, dict):
                raise ValueError("Arguments must be an object")
            if name == "bash":
                if set(args) != {"command"} or not isinstance(
                    args["command"], str
                ):
                    raise ValueError("bash requires a command string")
                return self.environment.execute({"command": args["command"]})
            if name == "read":
                if set(args) - {"path", "offset", "limit"} or not isinstance(
                    args.get("path"), str
                ):
                    raise ValueError(
                        "read requires a path and optional offset and limit"
                    )
                offset = args.get("offset", 1)
                limit = args.get("limit", 2000)
                if (
                    type(offset) is not int
                    or type(limit) is not int
                    or offset < 1
                    or limit < 1
                ):
                    raise ValueError(
                        "offset and limit must be positive integers"
                    )
                parts = []
                size = 0
                line = 1
                truncated = False
                with self._path(args["path"]).open(encoding="utf-8") as file:
                    while line < offset + limit:
                        chunk = file.readline(8192)
                        if not chunk:
                            break
                        if line >= offset:
                            remaining = 50001 - size
                            parts.append(chunk[:remaining])
                            size += min(len(chunk), remaining)
                            if size > 50000:
                                truncated = True
                                break
                        if chunk.endswith("\n"):
                            line += 1
                output = "\n".join("".join(parts)[:50000].splitlines())
                if truncated:
                    output += "\n[output truncated]"
            elif name == "edit":
                if (
                    set(args) != {"path", "old_text", "new_text"}
                    or not all(isinstance(args[k], str) for k in args)
                    or not args["old_text"]
                ):
                    raise ValueError(
                        "edit requires path, nonempty old_text, "
                        "and new_text strings"
                    )
                path = self._path(args["path"])
                with path.open("r", encoding="utf-8", newline="") as file:
                    text = file.read()
                if text.count(args["old_text"]) != 1:
                    raise ValueError("old_text must match exactly once")
                with path.open("w", encoding="utf-8", newline="") as file:
                    file.write(
                        text.replace(args["old_text"], args["new_text"], 1)
                    )
                output = "Edit applied."
            else:
                raise ValueError(f"Unknown built-in tool: {name}")
            return {"output": output, "returncode": 0, "exception_info": ""}
        except (OSError, UnicodeError, ValueError) as exc:
            return {
                "output": f"{type(exc).__name__}: {exc}",
                "returncode": 1,
                "exception_info": "",
            }
