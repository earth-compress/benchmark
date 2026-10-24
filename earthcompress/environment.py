"""Machine and timing metadata written with benchmark results."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__

ENVIRONMENT_FILENAME = "environment.json"


def _sysctl(name: str) -> str | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", name],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _proc_field(path: str, prefix: str) -> str | None:
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith(prefix):
            _, _, value = line.partition(":")
            value = value.strip()
            if value:
                return value
    return None


def _cpu_model() -> str:
    system = platform.system()
    if system == "Darwin":
        model = _sysctl("machdep.cpu.brand_string")
    elif system == "Linux":
        model = _proc_field("/proc/cpuinfo", "model name")
    else:
        model = None
    return model or platform.processor() or platform.machine() or "unknown"


def _memory_bytes() -> int | None:
    system = platform.system()
    if system == "Darwin":
        value = _sysctl("hw.memsize")
        if value and value.isdigit():
            return int(value)
    elif system == "Linux":
        value = _proc_field("/proc/meminfo", "MemTotal")
        if value and value.split()[0].isdigit():
            return int(value.split()[0]) * 1024
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None


def describe_environment(
    *,
    rounds: int,
    min_seconds: float,
    threads: int = 1,
) -> dict[str, Any]:
    """Describe the machine and the timing settings of the current run."""
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "earthcompress_version": __version__,
        "cpu": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "threads": threads,
        "rounds": rounds,
        "min_seconds": min_seconds,
    }


def write_environment(corpus: Path, environment: dict[str, Any]) -> Path:
    """Write ``environment.json`` next to the results of ``corpus``."""
    path = corpus / ENVIRONMENT_FILENAME
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(f"{json.dumps(environment, indent=2)}\n")
    temporary.replace(path)
    return path
