"""Fixed synthetic export diagnostic, not an artifact collector."""

import os
import stat


SYNTHETIC_CONTENT = b"synthetic benchmark artifact\n"


def read_synthetic(directory_fd):
    """Read only the exact diagnostic file from an already-open directory.

    This deliberately does not implement general safe artifact traversal.
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise NotImplementedError("diagnostic requires no-follow support")
    fd = os.open(
        "artifact.txt",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory_fd,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > 4096
        ):
            raise ValueError("invalid synthetic file")
        data = os.read(fd, 4097)
        if data != SYNTHETIC_CONTENT:
            raise ValueError("unexpected synthetic content")
        return data
    finally:
        os.close(fd)
