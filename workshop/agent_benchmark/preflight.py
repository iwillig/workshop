"""Read-only diagnostics; this module never authorizes execution."""

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum


class CheckState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class PreflightReport:
    checks: dict[str, CheckState]

    @property
    def ready(self) -> bool:
        """Always false until the sandbox and its security review exist."""
        return False


def _boolean_check(value, expected):
    if type(value) is not bool:
        return CheckState.UNVERIFIED
    return CheckState.PASS if value is expected else CheckState.FAIL


def preflight(*, run=None, platform=None) -> PreflightReport:
    """Inspect local Podman capabilities without starting a container.

    Results are diagnostic only: reported runtime settings do not prove
    enforcement. Never use this report as authorization to run untrusted code.
    """
    checks = {
        name: CheckState.UNVERIFIED
        for name in (
            "host_linux",
            "runtime_available",
            "runtime_local",
            "rootless",
            "seccomp_available",
            "cgroups_v2",
            "resource_controllers",
            "effective_sandbox",
            "broker",
            "artifacts",
            "trusted_scoring",
            "cleanup",
            "security_review",
        )
    }
    if platform is None:
        platform = sys.platform
    checks["host_linux"] = (
        CheckState.PASS if platform == "linux" else CheckState.FAIL
    )
    if platform != "linux":
        return PreflightReport(checks)
    if run is None:
        run = subprocess.run
    try:
        result = run(
            ["podman", "info", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            checks["runtime_available"] = CheckState.FAIL
            return PreflightReport(checks)
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(
            data.get("host"), dict
        ):
            checks["runtime_available"] = CheckState.FAIL
            return PreflightReport(checks)
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        checks["runtime_available"] = CheckState.FAIL
        return PreflightReport(checks)
    checks["runtime_available"] = CheckState.PASS
    host = data["host"]
    checks["runtime_local"] = _boolean_check(
        host.get("serviceIsRemote"), False
    )
    security = host.get("security")
    if isinstance(security, dict):
        checks["rootless"] = _boolean_check(security.get("rootless"), True)
        checks["seccomp_available"] = _boolean_check(
            security.get("seccompEnabled"), True
        )
    version = host.get("cgroupVersion")
    if isinstance(version, str):
        checks["cgroups_v2"] = (
            CheckState.PASS if version == "v2" else CheckState.FAIL
        )
    controllers = host.get("cgroupControllers")
    if isinstance(controllers, list) and all(
        isinstance(item, str) for item in controllers
    ):
        checks["resource_controllers"] = (
            CheckState.PASS
            if {"cpu", "memory", "pids"} <= set(controllers)
            else CheckState.FAIL
        )
    return PreflightReport(checks)
