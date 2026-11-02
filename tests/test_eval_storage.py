import os

import pytest

from workshop.agent_eval.storage import PrivateStorage


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX dirfd support")
def test_private_storage_round_trip_and_permissions(tmp_path):
    storage = PrivateStorage(tmp_path / "private")
    storage.write_json("run-1.json", {"outcome": "pending_human_review"})
    assert storage.read_json("run-1.json") == {
        "outcome": "pending_human_review"
    }
    assert storage.root.stat().st_mode & 0o777 == 0o700
    assert (storage.root / "run-1.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "key", ["", "../outside.json", "/tmp/a.json", "sub/x.json", ".", "x.txt"]
)
def test_storage_rejects_unsafe_keys(tmp_path, key):
    storage = PrivateStorage(tmp_path / "private")
    with pytest.raises(ValueError):
        storage.write_json(key, {"x": 1})


def test_storage_requires_explicit_root():
    with pytest.raises((TypeError, ValueError)):
        PrivateStorage(None)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX permissions")
def test_storage_rejects_insecure_directory_and_symlinks(tmp_path):
    insecure = tmp_path / "public"
    insecure.mkdir(mode=0o755)
    insecure.chmod(0o755)
    with pytest.raises(PermissionError):
        PrivateStorage(insecure)
    storage = PrivateStorage(tmp_path / "private")
    secret = tmp_path / "secret"
    secret.write_text("unchanged")
    (storage.root / "link.json").symlink_to(secret)
    with pytest.raises((ValueError, OSError)):
        storage.read_json("link.json")
    storage.write_json("link.json", {"safe": True})
    assert secret.read_text() == "unchanged"


def test_storage_rejects_symlink_root(tmp_path):
    target = tmp_path / "private"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        PrivateStorage(link)


def test_non_json_data_does_not_replace_record(tmp_path):
    storage = PrivateStorage(tmp_path / "private")
    storage.write_json("run.json", {"version": 1})
    with pytest.raises(ValueError):
        storage.write_json("run.json", {"cost": float("nan")})
    assert storage.read_json("run.json") == {"version": 1}


def test_failed_write_does_not_replace_existing_record(tmp_path, monkeypatch):
    storage = PrivateStorage(tmp_path / "private")
    storage.write_json("run.json", {"version": 1})

    def fail(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("workshop.agent_eval.storage.os.replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        storage.write_json("run.json", {"version": 2})
    assert storage.read_json("run.json") == {"version": 1}
    assert sorted(p.name for p in storage.root.iterdir()) == ["run.json"]
