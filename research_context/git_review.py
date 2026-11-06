"""Read-only, pinned local Git review context for trusted repositories."""

import subprocess
from pathlib import Path


class GitReview:
    """Capture the commits for one review; Git configuration is trusted."""

    def __init__(self, directory, base_ref):
        self.directory = Path(directory).resolve()
        if not isinstance(base_ref, str) or not base_ref.strip():
            raise ValueError("A nonempty base ref is required")
        if base_ref.startswith("-") or any(c in base_ref for c in "\n\r\0"):
            raise ValueError("Invalid base ref")
        self.base_ref = base_ref
        self.snapshot = None

    def _git(self, *args):
        try:
            result = subprocess.run(
                ["git", "-C", str(self.directory), *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Git operation failed") from exc
        return result.stdout.decode("utf-8", errors="replace").strip()

    def start(self):
        self.snapshot = None
        try:
            if self._git("rev-parse", "--is-bare-repository") != "false":
                raise ValueError("Bare repositories are not supported")
            root = self._git("rev-parse", "--show-toplevel")
            self.directory = Path(root)
            branch = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
        except ValueError as exc:
            raise ValueError(
                "Not a working repository or HEAD is detached"
            ) from exc
        try:
            head = self._git("rev-parse", "--verify", "HEAD^{commit}")
            base = self._git(
                "rev-parse", "--verify", "--end-of-options",
                self.base_ref + "^{commit}",
            )
        except ValueError as exc:
            raise ValueError("Unable to resolve HEAD or base ref") from exc
        try:
            bases = self._git("merge-base", "--all", base, head).splitlines()
        except ValueError as exc:
            raise ValueError("No merge base found") from exc
        if len(bases) != 1:
            raise ValueError("Expected one merge base")
        from workshop.agent.environments import _run

        try:
            status = _run(
                [
                    "git", "-C", str(self.directory), "status",
                    "--porcelain=v1", "--untracked-files=normal",
                ],
                None, None, 30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Unable to check working-tree status") from exc
        if status.returncode:
            raise ValueError("Unable to check working-tree status")
        dirty = bool(status.stdout)
        self.snapshot = {
            "root": root,
            "branch": branch,
            "base": base,
            "merge_base": bases[0],
            "head": head,
            "dirty": dirty,
        }
        return dict(self.snapshot)

    def context(self):
        if self.snapshot is None:
            raise ValueError("Review has not started")
        return dict(self.snapshot)

    def changed_files(self, offset=0, limit=50):
        """List a page of changed files in the pinned comparison."""
        import threading

        snapshot = self.context()
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        command = [
            "git", "-C", str(self.directory), "diff", "--no-ext-diff",
            "--no-textconv", "--name-status", "-z", "--find-renames",
            snapshot["merge_base"], snapshot["head"], "--",
        ]
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", start_new_session=True,
            )
        except OSError as exc:
            raise ValueError("Git changed-file inventory failed") from exc
        files = []
        count = 0
        problems = []

        def drain():
            nonlocal count
            buffer = ""
            tokens = []
            while chunk := process.stdout.read(8192):
                if problems:
                    continue
                buffer += chunk
                parts = buffer.split("\0")
                buffer = parts.pop()
                tokens.extend(parts)
                while tokens:
                    status = tokens[0]
                    if not status or status[0] not in "ACDMRTUXB":
                        problems.append("Invalid Git inventory output")
                        break
                    needed = 3 if status[0] in "RC" else 2
                    if len(tokens) < needed:
                        break
                    if offset <= count < offset + limit:
                        item = {
                            "status": status[0], "path": tokens[needed - 1]
                        }
                        if needed == 3:
                            item["previous_path"] = tokens[1]
                        files.append(item)
                    count += 1
                    del tokens[:needed]
                if len(buffer) > 50000:
                    problems.append("Git inventory record exceeds size limit")
            if (buffer or tokens) and not problems:
                problems.append("Incomplete Git inventory output")

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            import os
            import signal

            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            reader.join(timeout=1)
            raise ValueError("Git inventory timed out") from exc
        reader.join(timeout=1)
        if reader.is_alive() or process.returncode or problems:
            raise ValueError(
                problems[0] if problems else "Git inventory failed"
            )
        end = offset + len(files)
        more = end < count
        return {
            "files": files,
            "complete": not more,
            "next_offset": end if more else None,
            "truncated": False,
        }

    def diff(self, offset=0, limit=20000, path=None):
        """Return a bounded page of the pinned patch, by character offset."""
        import threading

        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        if type(limit) is not int or not 1 <= limit <= 20000:
            raise ValueError("limit must be between 1 and 20000")
        snapshot = self.context()
        if path is not None:
            self._validate_path(path)
        command = [
            "git", "-C", str(self.directory), "diff", "--no-ext-diff",
            "--no-textconv", "--no-color", snapshot["merge_base"],
            snapshot["head"], "--",
        ]
        if path is not None:
            command.append(":(literal)" + path)
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", start_new_session=True,
            )
        except OSError as exc:
            raise ValueError("Git diff failed") from exc
        pieces = []
        total = 0

        def drain():
            nonlocal total
            while chunk := process.stdout.read(8192):
                start = max(0, offset - total)
                end = min(len(chunk), offset + limit - total)
                if start < end:
                    pieces.append(chunk[start:end])
                total += len(chunk)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            import os
            import signal

            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            reader.join(timeout=1)
            raise ValueError("Git diff timed out") from exc
        reader.join(timeout=1)
        if reader.is_alive() or process.returncode:
            raise ValueError("Git diff failed or output was incomplete")
        patch = "".join(pieces)
        end = min(offset + len(patch), total)
        return {
            "base": snapshot["merge_base"],
            "head": snapshot["head"],
            "patch": patch,
            "complete": end >= total,
            "next_offset": end if end < total else None,
        }

    def search(self, query, offset=0, limit=100, path=None):
        """Search tracked text at the pinned HEAD for a literal string."""
        import re
        import threading

        snapshot = self.context()
        if (
            not isinstance(query, str)
            or not query
            or len(query) > 256
            or any(char in query for char in "\0\r\n")
        ):
            raise ValueError("Search requires a single nonempty literal")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be nonnegative")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if path is not None:
            self._validate_path(path)
        command = [
            "git", "-C", str(self.directory), "grep", "--no-color", "-I",
            "-n", "-z", "-F", "-e", query, snapshot["head"], "--",
        ]
        if path is not None:
            command.append(":(literal)" + path)
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", start_new_session=True,
            )
        except OSError as exc:
            raise ValueError("Git search failed") from exc
        matches = []
        count = 0
        size = 0
        page_full = False
        problems = []
        pattern = re.compile(r"([^\0]+)\0(\d+)\0([^\n]*)\n")
        prefix = snapshot["head"] + ":"

        def drain():
            nonlocal count, size, page_full
            buffer = ""
            while chunk := process.stdout.read(8192):
                if problems:
                    continue
                buffer += chunk
                while match := pattern.match(buffer):
                    if not match[1].startswith(prefix):
                        problems.append("Invalid Git search output")
                        break
                    if offset <= count < offset + limit:
                        item_size = len(match[1]) + len(match[3])
                        if not page_full and size + item_size <= 20000:
                            matches.append({
                                "path": match[1][len(prefix):],
                                "line": int(match[2]), "text": match[3],
                            })
                            size += item_size
                        else:
                            page_full = True
                    count += 1
                    buffer = buffer[match.end():]
                if len(buffer) > 50000:
                    problems.append("Git search record exceeds size limit")
            if buffer and not problems:
                problems.append("Incomplete Git search output")

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired as exc:
            import os
            import signal

            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            reader.join(timeout=1)
            raise ValueError("Git search timed out") from exc
        reader.join(timeout=1)
        if reader.is_alive() or process.returncode not in (0, 1) or problems:
            raise ValueError(problems[0] if problems else "Git search failed")
        if count > offset and not matches:
            raise ValueError("Search match exceeds output limit")
        end = offset + len(matches)
        more = end < count
        return {
            "matches": matches,
            "complete": not more,
            "next_offset": end if more else None,
            "truncated": False,
            "binary_files_omitted": True,
        }

    @staticmethod
    def _validate_path(path):
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\0" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
        ):
            raise ValueError("Invalid repository path")

    def read_file(self, commit, path, offset=1, limit=100):
        snapshot = self.context()
        if commit not in (snapshot["head"], snapshot["merge_base"]):
            raise ValueError("Commit must be a pinned review revision")
        self._validate_path(path)
        if type(offset) is not int or offset < 1:
            raise ValueError("offset must be positive")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        entry = self._git(
            "ls-tree", "-z", commit, "--", ":(literal)" + path
        )
        try:
            metadata, found_path = entry.rstrip("\0").split("\t", 1)
            mode, kind, object_id = metadata.split(" ")
        except ValueError as exc:
            raise ValueError("File not found at revision") from exc
        if found_path != path or mode not in ("100644", "100755"):
            raise ValueError("File is not a regular tracked file")
        if kind != "blob" or int(
            self._git("cat-file", "-s", object_id)
        ) > 1048576:
            raise ValueError("File is unsupported or exceeds size limit")
        # Preserve whitespace by reading the blob without the text wrapper.
        try:
            result = subprocess.run(
                [
                    "git", "-C", str(self.directory), "cat-file", "blob",
                    object_id,
                ],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=30, check=True,
            )
            text = result.stdout.decode("utf-8")
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise ValueError("Cannot read UTF-8 file") from exc
        if "\0" in text:
            raise ValueError("Binary files are not supported")
        lines = text.splitlines()
        selected = []
        size = 0
        index = offset - 1
        while index < len(lines) and len(selected) < limit:
            line = lines[index]
            if len(line) > 20000:
                raise ValueError("Line exceeds output limit")
            if size + len(line) > 20000:
                break
            selected.append({"line": index + 1, "text": line})
            size += len(line)
            index += 1
        return {
            "lines": selected,
            "complete": index >= len(lines),
            "next_offset": index + 1 if index < len(lines) else None,
        }

    def final_check(self):
        snapshot = self.context()
        try:
            head = self._git("rev-parse", "--verify", "HEAD^{commit}")
            branch = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
            base = self._git(
                "rev-parse", "--verify", "--end-of-options",
                self.base_ref + "^{commit}",
            )
        except ValueError:
            return {"changed": None, "error": "Unable to recheck refs"}
        return {
            "changed": (
                head != snapshot["head"] or base != snapshot["base"]
                or branch != snapshot["branch"]
            ),
            "error": None,
        }
