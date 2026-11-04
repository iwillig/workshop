"""Bounded, read-only GitHub PR operations independent of Click and LLMs."""

import base64
import binascii
import json
import os
import re
from urllib.parse import quote

import httpx

MAX_RESPONSE_BYTES = 1_000_000
MAX_SOURCE_BYTES = 250_000
PAGE_SIZE = 5


def _repository(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise ValueError("repository must be OWNER/REPO")
    return f"/repos/{value}"


def _number(value):
    if type(value) is not int or value < 1:
        raise ValueError("PR number must be a positive integer")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", value
    ):
        raise ValueError("revision must be a 40-character commit SHA")
    return value.lower()


def _path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or any(x in {"", ".", ".."} for x in value.split("/"))
    ):
        raise ValueError("invalid repository path")
    return value


def _clip(value, limit):
    text = value if isinstance(value, str) else ""
    return text[:limit], len(text) > limit


DEFAULT_API_BASE = "https://api.github.com"


def _api_base():
    """Allow a loopback-only override for trusted synthetic fixtures."""
    override = os.environ.get("WORKSHOP_GITHUB_API_BASE", "").strip()
    if not override:
        return DEFAULT_API_BASE
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+", override):
        raise ValueError(
            "WORKSHOP_GITHUB_API_BASE must be a loopback http URL"
        )
    return override


class GitHubReviewService:
    """Read small PR pages and commit-pinned source from api.github.com."""

    def __init__(self, client=None):
        if client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            base_url = _api_base()
            is_fixture = base_url != DEFAULT_API_BASE
            token = os.environ.get("GITHUB_TOKEN", "").strip()
            if token and not is_fixture:
                headers["Authorization"] = f"Bearer {token}"
            options = {"trust_env": False} if is_fixture else {}
            client = httpx.Client(
                base_url=base_url,
                headers=headers,
                timeout=30,
                follow_redirects=False,
                **options,
            )
        self.client = client

    def close(self):
        self.client.close()

    def _get(self, path, params=None):
        with self.client.stream("GET", path, params=params) as response:
            response.raise_for_status()
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("GitHub response exceeds byte limit")
                chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid GitHub JSON response") from exc

    def get_pr(self, repository, number):
        repo = _repository(repository)
        number = _number(number)
        data = self._get(f"{repo}/pulls/{number}")
        if not isinstance(data, dict):
            raise ValueError("Invalid PR metadata")
        base = data.get("base") or {}
        head = data.get("head") or {}
        if not isinstance(base, dict) or not isinstance(head, dict):
            raise ValueError("Invalid PR revision metadata")
        title, title_cut = _clip(data.get("title"), 500)
        body, body_cut = _clip(data.get("body"), 3000)
        base_repo = base.get("repo")
        head_repo = head.get("repo")
        base_repo = base_repo if isinstance(base_repo, dict) else {}
        head_repo = head_repo if isinstance(head_repo, dict) else {}
        changed = data.get("changed_files")
        changed = changed if type(changed) is int and changed >= 0 else None
        return {
            "repository": repository,
            "number": number,
            "url": _clip(data.get("html_url"), 500)[0],
            "title": title,
            "description": body,
            "description_truncated": body_cut,
            "title_truncated": title_cut,
            "state": _clip(data.get("state"), 50)[0],
            "draft": data.get("draft") is True,
            "base_sha": _sha(base.get("sha")),
            "head_sha": _sha(head.get("sha")),
            "base_ref": _clip(base.get("ref"), 256)[0],
            "head_ref": _clip(head.get("ref"), 256)[0],
            "base_repository": _clip(base_repo.get("full_name"), 256)[0],
            "head_repository": _clip(head_repo.get("full_name"), 256)[0],
            "changed_files": changed,
        }

    def pr_files(self, repository, number, base_sha, head_sha, page=1):
        repo = _repository(repository)
        number = _number(number)
        base_sha, head_sha = _sha(base_sha), _sha(head_sha)
        if type(page) is not int or not 1 <= page <= 600:
            raise ValueError("page must be between 1 and 600")
        before = self.get_pr(repository, number)
        if (before["base_sha"], before["head_sha"]) != (base_sha, head_sha):
            raise ValueError("PR base or head changed")
        data = self._get(
            f"{repo}/pulls/{number}/files",
            {"per_page": PAGE_SIZE, "page": page},
        )
        after = self.get_pr(repository, number)
        if (after["base_sha"], after["head_sha"]) != (base_sha, head_sha):
            raise ValueError("PR base or head changed")
        if not isinstance(data, list) or len(data) > PAGE_SIZE:
            raise ValueError("Invalid PR file page")
        files = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Invalid PR file entry")
            path = _path(item.get("filename"))
            previous = item.get("previous_filename")
            if previous is not None:
                _path(previous)
            patch = item.get("patch")
            clipped, truncated = _clip(patch, 1000)
            files.append(
                {
                    "path": path,
                    "previous_path": previous,
                    "status": _clip(item.get("status"), 40)[0],
                    "patch": clipped if isinstance(patch, str) else None,
                    "patch_truncated": truncated,
                    "patch_available": isinstance(patch, str),
                }
            )
        count = before.get("changed_files")
        count_known = type(count) is int and count >= 0
        more = (
            page * PAGE_SIZE < count if count_known else len(data) == PAGE_SIZE
        )
        return {
            "repository": repository,
            "number": number,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "page": page,
            "files": files,
            "next_page": page + 1 if more and page < 600 else None,
            "complete": count_known
            and not more
            and all(
                f["patch_available"] and not f["patch_truncated"]
                for f in files
            ),
            "limitations": [
                "GitHub PR patches may be incomplete; "
                "comparison semantics are not independently verified.",
                "PR revision checks are not atomic.",
            ],
        }

    def read_file(self, repository, path, sha, offset=1, limit=100):
        repo = _repository(repository)
        path, sha = _path(path), _sha(sha)
        if (
            type(offset) is not int
            or offset < 1
            or type(limit) is not int
            or not 1 <= limit <= 200
        ):
            raise ValueError("invalid source line range")
        data = self._get(
            f"{repo}/contents/{quote(path, safe='/')}", {"ref": sha}
        )
        if (
            not isinstance(data, dict)
            or data.get("type") != "file"
            or data.get("encoding") != "base64"
            or not isinstance(data.get("content"), str)
        ):
            raise ValueError("source unavailable or not a file")
        content = "".join(data["content"].split())
        if len(content) > (MAX_SOURCE_BYTES + 2) // 3 * 4:
            raise ValueError("source exceeds byte limit")
        try:
            raw = base64.b64decode(content, validate=True)
            if len(raw) > MAX_SOURCE_BYTES or b"\0" in raw:
                raise ValueError("source is binary or exceeds byte limit")
            text = raw.decode("utf-8")
        except (UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("source is not valid UTF-8 text") from exc
        lines = text.splitlines(keepends=True)
        selected = "".join(lines[offset - 1 : offset - 1 + limit])
        clipped, truncated = _clip(selected, 5000)
        next_offset = (
            offset + limit if offset - 1 + limit < len(lines) else None
        )
        return {
            "repository": repository,
            "path": path,
            "sha": sha,
            "offset": offset,
            "content": clipped,
            "truncated": truncated,
            "next_offset": next_offset if not truncated else None,
            "complete": not truncated and next_offset is None,
            "limitations": [
                "GitHub Contents may dereference symlinks; "
                "file mode is not verified."
            ],
        }
