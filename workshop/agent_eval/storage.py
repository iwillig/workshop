"""Explicit, private, atomic JSON records in a trusted POSIX directory."""

import json
import os
import re
import secrets
import stat
from pathlib import Path


class PrivateStorage:
    """Store JSON records under a private root; keys are single filenames."""

    def __init__(self, root):
        if root is None or not os.fspath(root):
            raise ValueError("an explicit storage root is required")
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise NotImplementedError("private storage requires POSIX support")
        self.root = Path(root).absolute()
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        fd = self._open_root()
        os.close(fd)

    def _open_root(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise PermissionError("storage root must be owner-only")
        return fd

    @staticmethod
    def _validate_key(key):
        if not isinstance(key, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json", key
        ):
            raise ValueError("storage key must be a single JSON filename")

    def write_json(self, key, value):
        self._validate_key(key)
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        root = self._open_root()
        temporary = ".tmp-" + secrets.token_hex(16)
        created = False
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
            created = True
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, key, src_dir_fd=root, dst_dir_fd=root)
            created = False
            os.fsync(root)
        finally:
            if created:
                os.unlink(temporary, dir_fd=root)
            os.close(root)

    def read_json(self, key):
        self._validate_key(key)
        root = self._open_root()
        try:
            fd = os.open(
                key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root
            )
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077
                ):
                    raise PermissionError(
                        "record must be an owner-only regular file"
                    )
                with os.fdopen(fd, "r", encoding="utf-8") as stream:
                    fd = -1
                    return json.load(stream)
            finally:
                if fd != -1:
                    os.close(fd)
        finally:
            os.close(root)
