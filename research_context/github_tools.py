"""Native llm adapters for bounded read-only GitHub operations."""

import json

import httpx
import llm

from research_context.github_review import GitHubReviewService

REPOSITORY = {"type": "string", "description": "GitHub OWNER/REPO"}
NUMBER = {"type": "integer", "minimum": 1}
SHA = {
    "type": "string",
    "description": "Full immutable 40-character commit SHA",
}
SPECS = {
    "github_get_pr": (
        "Get PR metadata and current base/head commit SHAs.",
        {"repository": REPOSITORY, "number": NUMBER},
        ["repository", "number"],
        "get_pr",
    ),
    "github_pr_files": (
        "Get one bounded PR file page, checking expected base and head SHAs.",
        {
            "repository": REPOSITORY,
            "number": NUMBER,
            "base_sha": SHA,
            "head_sha": SHA,
            "page": {"type": "integer", "minimum": 1, "maximum": 600},
        },
        ["repository", "number", "base_sha", "head_sha"],
        "pr_files",
    ),
    "github_read_file": (
        "Read bounded source at a commit SHA; no code executes.",
        {
            "repository": REPOSITORY,
            "path": {"type": "string"},
            "sha": SHA,
            "offset": {"type": "integer", "minimum": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        ["repository", "path", "sha"],
        "read_file",
    ),
}


class GitHubTools:
    def __init__(self, selected=()):
        self.tools = []
        for name, (description, properties, required, _) in SPECS.items():
            if name in selected:
                self.tools.append(
                    llm.Tool(
                        name=name,
                        description=description,
                        input_schema={
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    )
                )

    def execute(self, action):
        name = action.get("tool")
        args = action.get("arguments")
        allowed = {tool.name for tool in self.tools}
        try:
            if name not in allowed or not isinstance(args, dict):
                raise ValueError("unknown tool or invalid arguments")
            _, properties, required, method = SPECS[name]
            if set(args) - set(properties) or not set(required) <= set(args):
                raise ValueError("invalid tool arguments")
            service = GitHubReviewService()
            try:
                result = getattr(service, method)(**args)
            finally:
                service.close()
            output = json.dumps(result, ensure_ascii=False)
            if len(output) > 40000:
                raise ValueError("tool result exceeds output limit")
            return {"output": output, "returncode": 0, "exception_info": ""}
        except httpx.HTTPStatusError as exc:
            message = (
                f"GitHub request failed (HTTP {exc.response.status_code})"
            )
        except httpx.RequestError:
            message = "GitHub connection failed"
        except ValueError as exc:
            message = str(exc)
        except TypeError:
            message = "Invalid tool arguments"
        return {
            "output": json.dumps({"error": message, "complete": False}),
            "returncode": 1,
            "exception_info": "",
        }
