"""Small, testable reader for the published PDMP data.json used by the watchdog."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def read_json_object(url, *, opener=None, sleep_fn=None, attempts=3, timeout=30):
    """Fetch and validate a JSON object, retrying transient/empty/invalid responses."""
    open_url = opener or urllib.request.urlopen
    pause = sleep_fn or time.sleep
    last_error = None

    for attempt in range(1, max(1, int(attempts)) + 1):
        request_url = str(url) + ("&" if "?" in str(url) else "?") + "watchdog=" + str(time.time_ns())
        request = urllib.request.Request(
            request_url,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
                "User-Agent": "pdmp-scan-watchdog",
            },
        )
        try:
            with open_url(request, timeout=timeout) as response:
                raw = response.read()
                status = getattr(response, "status", "unknown")
                content_type = response.headers.get("Content-Type", "unknown")
            if not raw or not raw.strip():
                raise ValueError(
                    f"raw data.json response was empty (HTTP {status}, Content-Type {content_type})"
                )
            candidate = json.loads(raw.decode("utf-8"))
            if not isinstance(candidate, dict):
                raise ValueError("data.json root must be a JSON object")
            return candidate, len(raw)
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
            if attempt < max(1, int(attempts)):
                pause(5)

    raise RuntimeError(
        f"Could not read valid data.json after {max(1, int(attempts))} attempts; {last_error}"
    )
