import os

import pytest

from workshop.agent_benchmark.crun_export_probe import read_synthetic


def test_read_only_fixed_synthetic_file(tmp_path):
    (tmp_path / "artifact.txt").write_bytes(b"synthetic benchmark artifact\n")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert read_synthetic(fd) == b"synthetic benchmark artifact\n"
    finally:
        os.close(fd)


def test_reject_symlinks_hardlinks_and_unexpected_content(tmp_path):
    target = tmp_path / "target"
    target.write_text("secret")
    link = tmp_path / "artifact.txt"
    link.symlink_to(target)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises((ValueError, OSError)):
            read_synthetic(fd)
        link.unlink()
        os.link(target, link)
        with pytest.raises(ValueError):
            read_synthetic(fd)
        link.unlink()
        link.write_text("not the fixed content")
        with pytest.raises(ValueError):
            read_synthetic(fd)
    finally:
        os.close(fd)


def test_reject_large_file(tmp_path):
    (tmp_path / "artifact.txt").write_bytes(b"x" * 10000)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ValueError):
            read_synthetic(fd)
    finally:
        os.close(fd)
