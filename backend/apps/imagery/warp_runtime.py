"""Locate a Python interpreter that can run the rasterio warp subprocess.

The main runtime may carry a broken rasterio install (DLL conflicts are a
classic on Windows conda hosts), so the warp cannot blindly fall back to
sys.executable. Candidates are probed once per process with a cheap
`import rasterio` check; the first healthy one wins.

Set SATHUB_WARP_PYTHON to force a specific interpreter (e.g. a dedicated
venv with rasterio installed).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_cache: dict[str, str | None] = {"interpreter": None, "probed": False}

PROBE = "import rasterio  # noqa: S101"


def _probe(interpreter: Path) -> bool:
    try:
        result = subprocess.run(
            [str(interpreter), "-c", PROBE],
            capture_output=True,
            timeout=60,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def warp_interpreter() -> str | None:
    """Return a Python executable that can import rasterio, or None."""
    if _cache["probed"]:
        return _cache["interpreter"]  # type: ignore[return-value]

    candidates: list[Path] = []
    configured = os.environ.get("SATHUB_WARP_PYTHON") or getattr(sys.modules["django.conf"].settings, "TITILER_PYTHON", "")
    if configured:
        path = Path(str(configured))
        if path.is_file():
            candidates.append(path)
    current = Path(sys.executable)
    candidates.append(current)

    for candidate in candidates:
        if _probe(candidate):
            _cache.update(interpreter=str(candidate), probed=True)
            return str(candidate)

    _cache.update(interpreter=None, probed=True)
    return None


def run_warp_payload(script_path: Path, payload: dict, timeout: int = 300) -> dict | None:
    """Run the preview warper in the located interpreter.

    Returns the decoded JSON payload, or None when no interpreter can run
    rasterio or the warp itself failed.
    """
    interpreter = warp_interpreter()
    if interpreter is None or not script_path.is_file():
        return None
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    try:
        result = subprocess.run(
            [interpreter, str(script_path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
        decoded = json.loads(result.stdout or "{}")
        return decoded if isinstance(decoded, dict) else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
