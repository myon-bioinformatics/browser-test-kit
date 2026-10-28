"""Select browser engines for the browser lanes with BTK_BROWSER_ENGINES (default: all engines)."""
import os

import pytest

OPTIONAL_ENGINES = ("firefox", "webkit")


def _selected_engines() -> set[str]:
    raw = os.environ.get("BTK_BROWSER_ENGINES", "chromium,firefox,webkit")
    return {name.strip() for name in raw.split(",") if name.strip()}


def pytest_collection_modifyitems(config, items):
    selected = _selected_engines()
    kept, dropped = [], []
    for item in items:
        params = getattr(getattr(item, "callspec", None), "params", {})
        engine = params.get("browser_name", params.get("browser"))
        if engine in OPTIONAL_ENGINES and engine not in selected:
            dropped.append(item)
        else:
            kept.append(item)
    if dropped:
        config.hook.pytest_deselected(items=dropped)
        items[:] = kept
