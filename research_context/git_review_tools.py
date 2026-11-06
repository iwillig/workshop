"""Opt-in native tools for a pinned local Git review."""

import json

import llm

from research_context.git_review import GitReview


SPECS = {
    "git_review_context": ("Get the captured review context.", {}, []),
    "git_review_diff": (
        "Get the pinned patch or a page of changed files.",
        {
            "inventory": {"type": "boolean"},
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20000},
        },
        [],
    ),
    "git_read_file": (
        "Read bounded lines of a regular file at a captured revision.",
        {
            "commit": {"type": "string"},
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        ["commit", "path"],
    ),
    "git_search": (
        "Search the captured HEAD for literal text.",
        {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        ["query"],
    ),
}


class GitReviewTools:
    def __init__(self, directory, base_ref, selected=None):
        self.review = GitReview(directory, base_ref)
        self.selected = set(SPECS) if selected is None else set(selected)
        self.tools = [
            llm.Tool(
                name=name,
                description=description,
                input_schema={
                    "type": "object", "properties": properties,
                    "required": required, "additionalProperties": False,
                },
            )
            for name, (description, properties, required) in SPECS.items()
            if name in self.selected
        ]
        self.coverage = []
        self.inventory_pages = {}
        self.file_reads = set()

    def start_run(self):
        self.coverage = []
        self.inventory_pages = {}
        self.file_reads = set()
        return self.review.start()

    def coverage_summary(self):
        files = set()
        offset = 0
        complete = False
        while offset in self.inventory_pages:
            page = self.inventory_pages[offset]
            files.update(item["path"] for item in page["files"])
            if page["complete"]:
                complete = True
                break
            next_offset = page.get("next_offset")
            if next_offset is None or next_offset <= offset:
                break
            offset = next_offset
        return {
            "inventory_complete": complete,
            "file_reads": sorted(self.file_reads),
            "unrequested_files": sorted(files - self.file_reads),
            "note": "Returned content does not prove model comprehension.",
            "calls": list(self.coverage),
        }

    def finish_run(self):
        return self.review.final_check()

    def execute(self, action):
        name = action.get("tool")
        args = action.get("arguments")
        try:
            if name not in self.selected or name not in SPECS:
                raise ValueError("Unknown tool")
            if not isinstance(args, dict):
                raise ValueError("Arguments must be an object")
            _, properties, required = SPECS[name]
            if set(args) - set(properties) or not set(required) <= set(args):
                raise ValueError("Invalid tool arguments")
            if name == "git_review_context":
                result = self.review.context()
            elif name == "git_review_diff":
                options = dict(args)
                inventory = options.pop("inventory", False)
                if type(inventory) is not bool:
                    raise ValueError("inventory must be a boolean")
                if inventory:
                    result = self.review.changed_files(**options)
                else:
                    result = self.review.diff(**options)
                    # JSON escaping can make a bounded patch much larger.
                    while len(json.dumps(result, ensure_ascii=False)) > 40000:
                        patch = result["patch"]
                        if len(patch) < 2:
                            raise ValueError("Diff output exceeds size limit")
                        result["patch"] = patch[:len(patch) // 2]
                        result["complete"] = False
                        result["next_offset"] = (
                            options.get("offset", 0) + len(result["patch"])
                        )
            elif name == "git_read_file":
                result = self.review.read_file(**args)
            else:
                result = self.review.search(**args)
            output = json.dumps(result, ensure_ascii=False)
            if len(output) > 40000:
                raise ValueError("Tool output exceeds size limit")
            if name == "git_review_diff" and args.get("inventory", False):
                self.inventory_pages[args.get("offset", 0)] = result
            if name == "git_read_file":
                self.file_reads.add(args["path"])
            self.coverage.append(
                {"tool": name, "complete": result.get("complete")}
            )
            return {
                "output": output, "returncode": 0,
                "exception_info": "",
            }
        except (ValueError, TypeError, OSError) as exc:
            self.coverage.append({"tool": name, "error": True})
            return {
                "output": json.dumps({"error": str(exc), "complete": False}),
                "returncode": 1, "exception_info": "",
            }
