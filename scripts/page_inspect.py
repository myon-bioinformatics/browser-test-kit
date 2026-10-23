"""Survey a page and rank locators with small, paged JSON operations.

Offline commands run under ``python -S``. ``survey`` is the only command that
imports Playwright. Scores follow the longest-common-substring ratio: the
length of the longest shared slice divided by the shorter string, using simple
Unicode lowercasing and UTF-16 code units so the Node twin agrees.

    python scripts/page_inspect.py survey fixtures/page_inspect.html --browser chromium --json --out survey.json
    python -S scripts/page_inspect.py count survey.json --role button
    python -S scripts/page_inspect.py locate survey.json --query "Save draft" --unique --json
    python -S scripts/page_inspect.py describe survey.json --target id:save-draft

Exit codes: 0 success; 1 no match or a non-unique top score; 2 usage, a bad
snapshot, or a launch, navigate, inspect, or cleanup failure.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import re
import sys
import urllib.parse
from pathlib import Path

SCHEMA_INSPECT = "btk-page-inspect/1"
SCHEMA_SURVEY = "btk-page-survey/1"
HARD_CAP = 500
SURVEY_LIMIT_DEFAULT = 50
SURVEY_LIMIT_MAX = 200
PAGE_LIMIT_DEFAULT = 20
PAGE_LIMIT_MAX = 100
CONTEXT_DEFAULT = 1
CONTEXT_MAX = 5
SUGGESTIONS = 3
THRESHOLD_DEFAULT = 1.0
SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
PROFILES = {"desktop": None, "iphone": "iPhone 13", "pixel": "Pixel 7"}
DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
_ROLE_ADDRESS = re.compile(r"^([^/]*)/([^#]*)#(\d+)$")
_ROLE_EQ = re.compile(r'^role=([A-Za-z0-9_-]+)\[name="([^"]*)"\](?:#(\d+))?$')
_GET_BY_ROLE = re.compile(
    r"""getByRole\(\s*['"]([A-Za-z0-9_-]+)['"]\s*,\s*\{\s*name\s*:\s*['"]([^'"]*)['"]\s*\}\s*\)$"""
)
_QUOTED_ROLE = re.compile(r'^([A-Za-z0-9_-]+)\s+"([^"]*)"$')
_HASH_ID = re.compile(r"^#([A-Za-z_][A-Za-z0-9_-]*)$")
_TESTID_ATTR = re.compile(r'^\[data-testid="([^"]+)"\]$')
_EQ_ID = re.compile(r"^(id|testid)=([A-Za-z_][A-Za-z0-9_-]*)$")


class InspectError(Exception):
    def __init__(self, error: str, hint: str, *, stage: str = "input", suggestions: list | None = None, code: int = 2):
        super().__init__(error)
        self.error = error
        self.hint = hint
        self.stage = stage
        self.suggestions = suggestions or []
        self.code = code


def utf16_units(text: str) -> tuple[int, ...]:
    encoded = text.encode("utf-16-le")
    return tuple(encoded[index] + (encoded[index + 1] << 8) for index in range(0, len(encoded), 2))


def unit_len(text: str) -> int:
    return len(utf16_units(text))


def lcs_length(left: str, right: str) -> int:
    """Longest contiguous shared slice, after simple lowercasing, in UTF-16 units."""
    first = utf16_units(left.lower())
    second = utf16_units(right.lower())
    if not first or not second:
        return 0
    previous = [0] * (len(second) + 1)
    best = 0
    for unit in first:
        current = [0] * (len(second) + 1)
        for index, other in enumerate(second, 1):
            if unit == other:
                current[index] = previous[index - 1] + 1
                if current[index] > best:
                    best = current[index]
        previous = current
    return best


def round6(value: float) -> float:
    return math.floor(value * 1000000 + 0.5) / 1000000


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    first, second = left.lower(), right.lower()
    return round6(lcs_length(first, second) / min(unit_len(first), unit_len(second)))


def clip(value: str, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def os_name() -> str:
    return {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system())


def collect_source() -> str:
    candidates = [Path(__file__).with_name("page_inspect_collect.js")]
    candidates.append(Path(sys.prefix) / "share/browser-test-kit/page_inspect_collect.js")
    try:
        import site
        candidates.append(Path(site.getuserbase()) / "share/browser-test-kit/page_inspect_collect.js")
    except Exception:
        pass
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise InspectError(
        "page collect script is not installed",
        "run survey from a checkout, or reinstall the package including its shared files",
        stage="launch",
    )


def _require_str(item: dict, key: str) -> str:
    value = item.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InspectError(f"{key} must be a string", "the survey payload was modified; run survey again", stage="inspect")
    return value


def _require_bool(item: dict, key: str, default: bool | None = None) -> bool:
    if key not in item and default is not None:
        return default
    value = item.get(key)
    if not isinstance(value, bool):
        raise InspectError(f"{key} must be a boolean", "the survey payload was modified; run survey again", stage="inspect")
    return value


def _box(item: dict) -> dict:
    raw = item.get("box")
    if not isinstance(raw, dict):
        raise InspectError("box must be an object", "the survey payload was modified; run survey again", stage="inspect")
    box = {}
    for key in ("x", "y", "width", "height"):
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise InspectError(f"box.{key} must be a finite number", "the survey payload was modified; run survey again", stage="inspect")
        box[key] = int(math.floor(float(value)))
    return box


def encode_address(value: str) -> str:
    """Percent-encode like encodeURIComponent, so the Node twin builds the same address."""
    return urllib.parse.quote(value, safe="!'()*")


def _role_address(role: str, name: str, nth: int) -> str:
    return f"role:{encode_address(role)}/{encode_address(name)}#{nth}"


def _locator(kind: str, selector: str, unique: bool, nth: int | None) -> dict:
    return {"kind": kind, "selector": selector, "unique": unique, "nth": nth}


def normalize_elements(raw: dict, *, start: int = 0, limit: int = SURVEY_LIMIT_DEFAULT) -> dict:
    """Turn a collect-script payload into addressed elements and one page of them."""
    if not isinstance(raw, dict) or not isinstance(raw.get("elements"), list):
        raise InspectError("survey payload has no elements list", "run survey again", stage="inspect")
    _check_page(start, limit, SURVEY_LIMIT_MAX)
    prepared = []
    counts: dict[tuple[str, str], int] = {}
    nths = []
    for item in raw["elements"]:
        if not isinstance(item, dict):
            raise InspectError("survey element must be an object", "run survey again", stage="inspect")
        role = clip(_require_str(item, "role"), 40) or "generic"
        name = clip(_require_str(item, "name"))
        key = (role, name)
        nths.append(counts.get(key, 0))
        counts[key] = counts.get(key, 0) + 1
        prepared.append((item, role, name))
    built = []
    for index, ((item, role, name), nth) in enumerate(zip(prepared, nths)):
        element_id = clip(_require_str(item, "id"), 200)
        testid = clip(_require_str(item, "testid"), 200)
        css = _require_str(item, "css")
        id_unique = _require_bool(item, "id_unique", False) and bool(SAFE.fullmatch(element_id))
        testid_unique = _require_bool(item, "testid_unique", False) and bool(SAFE.fullmatch(testid))
        css_unique = _require_bool(item, "css_unique", False) and bool(css)
        locators = []
        if id_unique:
            locators.append(_locator("id", "#" + element_id, True, None))
        if testid_unique:
            locators.append(_locator("testid", f'[data-testid="{testid}"]', True, None))
        role_safe = role not in {"", "generic"} and name and not any(char in name for char in '"\\]\n')
        if role_safe:
            locators.append(_locator("role", f'role={role}[name="{name}"]', counts[(role, name)] == 1, nth))
        if css:
            locators.append(_locator("css", css, css_unique, None))
        if id_unique:
            address = f"id:{element_id}"
        elif testid_unique:
            address = f"testid:{testid}"
        elif role_safe:
            address = _role_address(role, name, nth)
        elif css:
            address = "css:" + css
        else:
            address = f"h:{index}"
        built.append({
            "handle": f"h:{index}",
            "index": index,
            "address": address,
            "tag": clip(_require_str(item, "tag"), 40),
            "role": role,
            "name": name,
            "text": clip(_require_str(item, "text")),
            "id": element_id,
            "testid": testid,
            "href": _require_str(item, "href")[:500],
            "visible": _require_bool(item, "visible"),
            "enabled": _require_bool(item, "enabled"),
            "in_viewport": _require_bool(item, "in_viewport"),
            "obscured": _require_bool(item, "obscured"),
            "box": _box(item),
            "parent_tag": clip(_require_str(item, "parent_tag"), 40),
            "locators": locators,
        })
    reported = raw.get("total", len(built))
    if isinstance(reported, bool) or not isinstance(reported, int) or reported < len(built):
        reported = len(built)
    page = [element for element in built if start <= element["index"] < start + limit]
    truncated = bool(raw.get("truncated")) or len(built) < reported or start + len(page) < len(built) or start + len(page) < reported
    return {"elements": page, "total": reported, "truncated": truncated, "start": start, "limit": limit, "collected": len(built)}


def _check_page(start: int, limit: int, limit_max: int) -> None:
    if type(start) is not int or start < 0 or start > 100000:
        raise InspectError("start must be an integer from 0 to 100000", "pass --start as a whole number")
    if type(limit) is not int or limit < 1 or limit > limit_max:
        raise InspectError(f"limit must be an integer from 1 to {limit_max}", "lower --limit and page with --start")


def _check_threshold(threshold: float) -> None:
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)):
        raise InspectError("threshold must be a number from 0 to 1", "pass --threshold 1 for containment, or a lower score")
    if not 0 <= float(threshold) <= 1:
        raise InspectError("threshold must be a number from 0 to 1", "pass --threshold 1 for containment, or a lower score")


def field_score(element: dict, query: str) -> tuple[float, str | None]:
    best = 0.0
    matched = None
    for key in ("name", "text", "id", "testid", "role"):
        value = element.get(key) or ""
        if not value:
            continue
        score = similarity(query, value)
        if score > best:
            best = score
            matched = key
    return best, matched


def _role_ok(element: dict, role: str) -> bool:
    return not role or str(element.get("role") or "").lower() == role.lower()


def suggest(elements: list, query: str, limit: int = SUGGESTIONS) -> list:
    if not query:
        return []
    ranked = []
    for element in elements:
        score, _matched = field_score(element, query)
        if score > 0:
            ranked.append((score, element))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("index", 0)))
    return [{
        "address": element["address"], "handle": element["handle"], "name": element.get("name") or "",
        "role": element.get("role") or "", "score": score,
    } for score, element in ranked[:limit]]


def _view(element: dict) -> dict:
    item = dict(element)
    item.setdefault("role", "")
    item.setdefault("name", "")
    item.setdefault("text", "")
    item.setdefault("id", "")
    item.setdefault("testid", "")
    if type(item.get("index")) is not int:
        item["index"] = 0
    return item


def locate(elements: list, *, query: str = "", role: str = "", threshold: float = THRESHOLD_DEFAULT,
           start: int = 0, limit: int = PAGE_LIMIT_DEFAULT, unique: bool = False) -> dict:
    _check_page(start, limit, PAGE_LIMIT_MAX)
    _check_threshold(threshold)
    chosen = [_view(element) for element in elements if _role_ok(element, role)]
    if query:
        scored = []
        for element in chosen:
            score, matched = field_score(element, query)
            if score + 1e-9 >= float(threshold):
                item = dict(element)
                item["score"] = score
                item["matched"] = matched
                scored.append(item)
        query_lower = query.lower()
        scored.sort(key=lambda element: (
            -element["score"],
            0 if (element.get("name") or "").lower() == query_lower else 1,
            unit_len(element.get("name") or ""),
            element["index"],
        ))
    else:
        scored = []
        for element in chosen:
            item = dict(element)
            item["score"] = None
            item["matched"] = None
            scored.append(item)
    total = len(scored)
    page = scored[start:start + limit]
    next_start = start + len(page)
    if next_start >= total:
        next_start = None
    payload = {
        "schema": SCHEMA_INSPECT,
        "ok": True,
        "operation": "locate",
        "pagination": {"start": start, "limit": limit, "returned": len(page), "total": total, "next_start": next_start},
        "items": page,
        "hint": _locate_hint(query, unique, total, next_start),
    }
    if query and total == 0:
        payload.update({
            "ok": False,
            "stage": "input",
            "error": "no element matches",
            "hint": "lower --threshold, or reuse a suggest address. count lists role totals without element bodies",
            "suggestions": suggest(chosen if role else elements, query),
        })
        return payload
    if unique and query and total:
        top = scored[0]["score"]
        tied = [element for element in scored if element["score"] == top]
        if len(tied) > 1:
            shown = tied[:limit]
            payload.update({
                "ok": False,
                "stage": "input",
                "error": "more than one element shares the top score",
                "hint": "pass one address to describe; do not guess",
                "items": shown,
                "suggestions": suggest_from(tied),
            })
            payload["pagination"] = {
                "start": 0, "limit": limit, "returned": len(shown), "total": len(tied), "next_start": None,
            }
            return payload
        payload["items"] = scored[:1]
        payload["pagination"] = {"start": 0, "limit": limit, "returned": 1, "total": 1, "next_start": None}
        payload["hint"] = "unique top score; lower scores were omitted. Omit --unique to see the whole page"
    return payload


def suggest_from(elements: list) -> list:
    return [{
        "address": element["address"], "handle": element["handle"], "name": element.get("name") or "",
        "role": element.get("role") or "", "score": element.get("score"),
    } for element in elements[:SUGGESTIONS]]


def _locate_hint(query: str, unique: bool, total: int, next_start: int | None) -> str:
    if not query:
        extra = f" Pass --start {next_start} for the next page." if next_start is not None else ""
        return "pass --query to rank by longest-common-substring similarity." + extra
    if next_start is not None:
        return f"showing a page of {total}. Pass --start {next_start} for the next page, or count for totals only"
    return f"{total} match(es). describe one address to read a single control"


def count_elements(elements: list, *, query: str = "", role: str = "", threshold: float = THRESHOLD_DEFAULT) -> dict:
    _check_threshold(threshold)
    chosen = [_view(element) for element in elements if _role_ok(element, role)]
    if query:
        matched = []
        for element in chosen:
            score, _field = field_score(element, query)
            if score + 1e-9 >= float(threshold):
                matched.append(element)
        chosen = matched
    by_role: dict[str, int] = {}
    visible = enabled = 0
    for element in chosen:
        key = element.get("role") or ""
        by_role[key] = by_role.get(key, 0) + 1
        visible += 1 if element.get("visible") else 0
        enabled += 1 if element.get("enabled") else 0
    return {
        "schema": SCHEMA_INSPECT,
        "ok": True,
        "operation": "count",
        "total": len(chosen),
        "visible": visible,
        "enabled": enabled,
        "by_role": {key: by_role[key] for key in sorted(by_role)},
        "hint": "locate --start 0 --limit 20 returns one page of controls; count does not",
    }


def decode_address(value: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise InspectError("role address has a bad percent escape", "copy the address from survey or locate")
    return urllib.parse.unquote(value)


def _split_role_address(value: str) -> tuple[str, str, int]:
    match = _ROLE_ADDRESS.fullmatch(value)
    if not match:
        raise InspectError("role address must look like role:button/Save%20draft#0", "copy an address from locate or survey")
    role, name, nth = match.groups()
    return decode_address(role), decode_address(name), int(nth)


def stored_nth(elements: list, element: dict) -> int:
    for locator in element.get("locators") or []:
        if locator.get("kind") == "role" and type(locator.get("nth")) is int:
            return locator["nth"]
    return _role_nth(elements, element)


def _by_role_name(elements: list, role: str, name: str, nth: int | None) -> list[tuple[dict, str]]:
    found = []
    for element in elements:
        if (element.get("role") or "").lower() == role.lower() and (element.get("name") or "") == name:
            if nth is None or stored_nth(elements, element) == nth:
                found.append((element, "role"))
    return found


def _role_nth(elements: list, element: dict) -> int:
    nth = 0
    for other in elements:
        if other is element or other.get("handle") == element.get("handle"):
            return nth
        if (other.get("role"), other.get("name")) == (element.get("role"), element.get("name")):
            nth += 1
    return nth


def resolve_target(elements: list, target: str) -> dict:
    text = (target or "").strip()
    if not text:
        raise InspectError("target is empty", "pass an address from locate, such as id:save-draft")
    if re.fullmatch(r"0x[0-9A-Fa-f]+", text):
        raise InspectError(
            "memory addresses are not element addresses",
            "use id:, testid:, role:, css:, or a snapshot h:N handle",
        )
    views = [_view(element) for element in elements]
    kind, matches = _match_target(views, text)
    if len(matches) == 1:
        return {"ok": True, "element": matches[0], "resolved_as": kind}
    if len(matches) > 1:
        return {
            "schema": SCHEMA_INSPECT, "ok": False, "operation": "describe", "stage": "input",
            "error": "target matches more than one element",
            "hint": "pass one full address, including the role nth",
            "suggestions": [{
                "address": element["address"], "handle": element["handle"], "name": element.get("name") or "",
                "role": element.get("role") or "", "score": None,
            } for element in matches[:SUGGESTIONS]],
        }
    folded = _casefold_name(views, text) if kind == "bare" else []
    if len(folded) == 1:
        return {"ok": True, "element": folded[0], "resolved_as": "name-casefold"}
    return {
        "schema": SCHEMA_INSPECT, "ok": False, "operation": "describe", "stage": "input",
        "error": "target is not in this snapshot",
        "hint": "h:N is valid only in the snapshot that minted it; reuse an address or run survey again",
        "suggestions": suggest(views, text),
    }


def _casefold_name(elements: list, text: str) -> list:
    lowered = text.lower()
    return [element for element in elements if (element.get("name") or "").lower() == lowered or (element.get("id") or "").lower() == lowered]


def _match_target(elements: list, text: str) -> tuple[str, list]:
    if text.startswith("h:"):
        return "handle", [element for element in elements if element.get("handle") == text]
    if text.startswith("id:"):
        return "id", [element for element in elements if element.get("id") == text[3:]]
    if text.startswith("testid:"):
        return "testid", [element for element in elements if element.get("testid") == text[7:]]
    if text.startswith("role:"):
        role, name, nth = _split_role_address(text[5:])
        return "role", [element for element, _kind in _by_role_name(elements, role, name, nth)]
    if text.startswith("css:"):
        selector = text[4:]
        return "css", [element for element in elements if element.get("address") == text or _has_selector(element, selector)]
    hash_id = _HASH_ID.fullmatch(text)
    if hash_id:
        return "id", [element for element in elements if element.get("id") == hash_id.group(1)]
    testid = _TESTID_ATTR.fullmatch(text)
    if testid:
        return "testid", [element for element in elements if element.get("testid") == testid.group(1)]
    role_eq = _ROLE_EQ.fullmatch(text)
    if role_eq:
        role, name, nth = role_eq.groups()
        return "role", [element for element, _kind in _by_role_name(elements, role, name, int(nth) if nth is not None else None)]
    getter = _GET_BY_ROLE.fullmatch(text)
    if getter:
        return "role", [element for element, _kind in _by_role_name(elements, getter.group(1), getter.group(2), None)]
    quoted = _QUOTED_ROLE.fullmatch(text)
    if quoted:
        return "role", [element for element, _kind in _by_role_name(elements, quoted.group(1), quoted.group(2), None)]
    equals = _EQ_ID.fullmatch(text)
    if equals:
        key = "id" if equals.group(1) == "id" else "testid"
        return key, [element for element in elements if element.get(key) == equals.group(2)]
    exact = [element for element in elements if element.get("id") == text]
    if exact:
        return "id", exact
    exact = [element for element in elements if element.get("testid") == text]
    if exact:
        return "testid", exact
    exact = [element for element in elements if element.get("address") == text]
    if exact:
        return "address", exact
    return "bare", [element for element in elements if element.get("name") == text]


def _has_selector(element: dict, selector: str) -> bool:
    return any(locator.get("selector") == selector for locator in element.get("locators") or [])


def element_line(element: dict, *, marker: bool = False) -> str:
    score = element.get("score")
    score_text = "" if not isinstance(score, (int, float)) or isinstance(score, bool) else f" score={score:.6f}"
    mark = "* " if marker else ""
    name = element.get("name") or ""
    return f"{mark}{element.get('handle')} {element.get('role')} \"{name}\" {element.get('address')}{score_text}"


def describe_element(elements: list, target: str, *, context: int = CONTEXT_DEFAULT) -> dict:
    if type(context) is not int or not 0 <= context <= CONTEXT_MAX:
        raise InspectError(f"context must be an integer from 0 to {CONTEXT_MAX}", "pass --context 1 for one neighbor on each side")
    resolved = resolve_target(elements, target)
    if not resolved["ok"]:
        resolved["operation"] = "describe"
        return resolved
    element = resolved["element"]
    position = next(index for index, item in enumerate(elements) if item.get("handle") == element.get("handle"))
    lines = [
        element_line(elements[index], marker=index == position)
        for index in range(max(0, position - context), min(len(elements), position + context + 1))
    ]
    return {
        "schema": SCHEMA_INSPECT,
        "ok": True,
        "operation": "describe",
        "resolved_as": resolved["resolved_as"],
        "item": element,
        "context": lines,
        "hint": (
            f"resolved as {resolved['resolved_as']}. Neighbors are adjacent controls in this snapshot, "
            f"not DOM siblings. Reuse {element.get('address')}"
        ),
    }


def operations() -> dict:
    items = [
        {"name": "survey", "needs": "playwright", "summary": "Collect visible controls from one page into a snapshot",
         "limit_default": SURVEY_LIMIT_DEFAULT, "limit_max": SURVEY_LIMIT_MAX},
        {"name": "count", "needs": "snapshot", "summary": "Count matches and roles without element bodies",
         "limit_default": None, "limit_max": None},
        {"name": "locate", "needs": "snapshot", "summary": "Rank controls by longest-common-substring similarity and page them",
         "limit_default": PAGE_LIMIT_DEFAULT, "limit_max": PAGE_LIMIT_MAX},
        {"name": "describe", "needs": "snapshot", "summary": "Return one control, its locators, and a few neighbor lines",
         "limit_default": CONTEXT_DEFAULT, "limit_max": CONTEXT_MAX},
        {"name": "operations", "needs": "none", "summary": "List these commands",
         "limit_default": None, "limit_max": None},
    ]
    return {
        "schema": SCHEMA_INSPECT, "ok": True, "operation": "operations", "items": items,
        "hint": "count before locate on a large snapshot; describe one address instead of printing every control",
    }


def context_options(devices: dict, browser_name: str, profile: str, headed: bool) -> dict:
    """Playwright Python context kwargs. Firefox rejects is_mobile on phone descriptors."""
    device = PROFILES[profile]
    if device:
        args = dict(devices[device])
    elif headed:
        args = {"no_viewport": True}
    else:
        args = {"viewport": dict(DESKTOP_VIEWPORT)}
    args.pop("default_browser_type", None)
    if browser_name == "firefox":
        args.pop("is_mobile", None)
    return args


def target_url(target: str) -> str:
    if "://" in target:
        parts = urllib.parse.urlsplit(target)
        if parts.username or parts.password:
            raise InspectError("URL must not include credentials", "pass a file path or an http(s) URL without a user or password")
        if parts.scheme not in {"http", "https", "file"}:
            raise InspectError("URL scheme must be http, https, or file", "pass a local fixture path for core checks")
        return target
    path = Path(target)
    if not path.is_file():
        raise InspectError(f"page not found: {target}", "pass an existing HTML file or an http(s) or file URL")
    return path.resolve().as_uri()


def assemble_survey(raw: dict, *, environment: dict, url: str, start: int, limit: int) -> dict:
    normalized = normalize_elements(raw, start=start, limit=limit)
    hints = []
    if raw.get("child_frames"):
        hints.append("child frames were counted and not surveyed")
    if raw.get("shadow_roots") is True:
        hints.append("open shadow roots were detected and not entered")
    if raw.get("shadow_scan") == "partial":
        hints.append("the shadow scan stopped at 2000 elements")
    if normalized["truncated"]:
        hints.append("this snapshot is a page of the survey; raise --limit or pass --role")
    hints.append("h:N is valid only in this snapshot; reuse address with describe and locate")
    child_frames = raw.get("child_frames") or 0
    if isinstance(child_frames, bool) or not isinstance(child_frames, int):
        raise InspectError("child_frames must be an integer", "run survey again", stage="inspect")
    return {
        "schema": SCHEMA_SURVEY,
        "ok": True,
        "url": url,
        "title": clip(str(raw.get("title") or ""), 200),
        "environment": environment,
        "child_frames": child_frames,
        "shadow_roots": raw.get("shadow_roots"),
        "shadow_scan": raw.get("shadow_scan") or "complete",
        "truncated": normalized["truncated"],
        "total": normalized["total"],
        "start": start,
        "limit": limit,
        "hint": ". ".join(hints),
        "elements": normalized["elements"],
    }


def _close_browser(browser):
    if browser is None:
        return None
    try:
        browser.close()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def survey_page(*, url: str, browser_name: str, profile: str, headed: bool, channel: str | None,
                include_hidden: bool, role: str, start: int, limit: int) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise InspectError(
            "Playwright is not available in this interpreter",
            "survey needs the browser extra; count, locate, describe, and operations run under python -S on a saved snapshot",
            stage="launch",
        ) from exc
    browser = None
    failure: InspectError | None = None
    result = None
    try:
        with sync_playwright() as playwright:
            try:
                launcher = getattr(playwright, browser_name)
                kwargs = {"headless": not headed}
                if channel:
                    kwargs["channel"] = channel
                browser = launcher.launch(**kwargs)
            except Exception as exc:
                raise InspectError(
                    f"{type(exc).__name__}: {exc}",
                    "install the browser that matches this Playwright build. Headless survey uses the shell build; --headed needs the full browser",
                    stage="launch",
                ) from exc
            try:
                options = context_options(playwright.devices, browser_name, profile, headed)
                context = browser.new_context(**options)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.set_default_navigation_timeout(30000)
                try:
                    page.goto(url, wait_until="load", timeout=30000)
                except Exception as exc:
                    raise InspectError(
                        f"{type(exc).__name__}: {exc}",
                        "check the URL and that the page finishes loading. Core checks should use a local fixture",
                        stage="navigate",
                    ) from exc
                try:
                    raw = page.evaluate(collect_source(), {
                        "includeHidden": include_hidden, "role": role, "hardCap": HARD_CAP,
                    })
                except Exception as exc:
                    raise InspectError(
                        f"{type(exc).__name__}: {exc}",
                        "the page script failed in this engine; the snapshot was not written",
                        stage="inspect",
                    ) from exc
                viewport = page.viewport_size or {}
                environment = {
                    "os": os_name(),
                    "browser": browser_name,
                    "version": browser.version,
                    "channel": channel,
                    "headless": not headed,
                    "profile": profile,
                    "viewport": {"width": viewport.get("width"), "height": viewport.get("height")},
                }
                result = assemble_survey(raw, environment=environment, url=page.url, start=start, limit=limit)
            except InspectError as exc:
                failure = exc
            close_note = _close_browser(browser)
            browser = None
            if failure is not None:
                if close_note:
                    failure.hint = failure.hint + f" Browser close also failed: {close_note}"
                raise failure
            if close_note:
                raise InspectError("browser close failed", close_note, stage="cleanup")
            return result
    except InspectError:
        raise


def read_snapshot(path: str) -> dict:
    file = Path(path)
    if not file.is_file():
        raise InspectError(f"snapshot not found: {path}", "run survey --out this path first")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InspectError("snapshot is not JSON", "run survey again and pass that file") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_SURVEY:
        raise InspectError("snapshot schema is not btk-page-survey/1", "pass a file written by survey, not a locate result")
    elements = data.get("elements")
    if not isinstance(elements, list):
        raise InspectError("snapshot has no elements list", "run survey again")
    for element in elements:
        if not isinstance(element, dict) or not isinstance(element.get("address"), str) or not isinstance(element.get("handle"), str):
            raise InspectError("snapshot element is missing address or handle", "run survey again")
    return data


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def error_envelope(operation: str, exc: InspectError) -> dict:
    payload = {
        "schema": SCHEMA_INSPECT, "ok": False, "operation": operation, "stage": exc.stage,
        "error": exc.error, "hint": exc.hint,
    }
    if exc.suggestions:
        payload["suggestions"] = exc.suggestions
    return payload


def error_text(payload: dict) -> str:
    lines = [f"stage: {payload.get('stage', 'input')}", f"error: {payload.get('error')}", f"hint: {payload.get('hint')}"]
    for item in payload.get("suggestions") or []:
        score = item.get("score")
        score_text = "" if not isinstance(score, (int, float)) or isinstance(score, bool) else f" {score:.6f}"
        lines.append(f"suggest: {item.get('address')}{score_text} {item.get('name')}")
    return "\n".join(lines) + "\n"


def survey_text(payload: dict) -> str:
    env = payload["environment"]
    mode = "headless" if env.get("headless") else "headed"
    lines = [
        f"btk-page-survey/1 {env.get('os')} {env.get('browser')} {env.get('profile')} {mode} "
        f"elements={payload.get('total')} showing={len(payload.get('elements') or [])}"
    ]
    lines.extend(element_line(element) for element in payload.get("elements") or [])
    lines.append(f"hint: {payload.get('hint')}")
    return "\n".join(lines) + "\n"


def locate_text(payload: dict) -> str:
    if not payload.get("ok"):
        return error_text(payload)
    lines = [element_line(element) for element in payload.get("items") or []]
    page = payload["pagination"]
    lines.append(f"returned {page['returned']} of {page['total']}; start {page['start']}")
    lines.append(f"hint: {payload.get('hint')}")
    return "\n".join(lines) + "\n"


def count_text(payload: dict) -> str:
    lines = [f"total={payload['total']} visible={payload['visible']} enabled={payload['enabled']}"]
    for role, count in payload["by_role"].items():
        lines.append(f"role {role}={count}")
    lines.append(f"hint: {payload['hint']}")
    return "\n".join(lines) + "\n"


def describe_text(payload: dict) -> str:
    if not payload.get("ok"):
        return error_text(payload)
    lines = [f"resolved_as={payload['resolved_as']}", *payload["context"], f"hint: {payload['hint']}"]
    return "\n".join(lines) + "\n"


def operations_text(payload: dict) -> str:
    lines = [f"{item['name']}: {item['summary']}" for item in payload["items"]]
    lines.append(f"hint: {payload['hint']}")
    return "\n".join(lines) + "\n"


def _bounded(maximum: int):
    def parse(text: str) -> int:
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", text):
            raise argparse.ArgumentTypeError("must be a whole number")
        value = int(text)
        if value > maximum:
            raise argparse.ArgumentTypeError(f"must be at most {maximum}")
        return value
    return parse


def _threshold(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise argparse.ArgumentTypeError("must be from 0 to 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument("--json", action="store_true", help="write the JSON document to stdout")
    common.add_argument("--out", help="write the JSON document to this path; the parent directory must exist")
    parser = argparse.ArgumentParser(prog="page_inspect.py", description=__doc__.split("\n\n")[0], allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    survey = sub.add_parser("survey", parents=[common], help="collect controls from a page", allow_abbrev=False)
    survey.add_argument("target", help="HTML file, or an http(s) or file URL without credentials")
    survey.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    survey.add_argument("--profile", choices=tuple(PROFILES), default="desktop")
    survey.add_argument("--channel", help="branded browser channel, for example chrome")
    survey.add_argument("--headed", action="store_true", help="launch the full browser instead of headless")
    survey.add_argument("--include-hidden", action="store_true", help="keep controls that are not visible")
    survey.add_argument("--role", default="", help="only this role")
    survey.add_argument("--start", type=_bounded(100000), default=0)
    survey.add_argument("--limit", type=_bounded(SURVEY_LIMIT_MAX), default=SURVEY_LIMIT_DEFAULT)
    locate_parser = sub.add_parser("locate", parents=[common], help="rank controls in a snapshot", allow_abbrev=False)
    locate_parser.add_argument("snapshot")
    locate_parser.add_argument("--query", default="")
    locate_parser.add_argument("--role", default="")
    locate_parser.add_argument("--threshold", type=_threshold, default=THRESHOLD_DEFAULT)
    locate_parser.add_argument("--start", type=_bounded(100000), default=0)
    locate_parser.add_argument("--limit", type=_bounded(PAGE_LIMIT_MAX), default=PAGE_LIMIT_DEFAULT)
    locate_parser.add_argument("--unique", action="store_true", help="fail when the top score is shared")
    count_parser = sub.add_parser("count", parents=[common], help="count controls without listing them", allow_abbrev=False)
    count_parser.add_argument("snapshot")
    count_parser.add_argument("--query", default="")
    count_parser.add_argument("--role", default="")
    count_parser.add_argument("--threshold", type=_threshold, default=THRESHOLD_DEFAULT)
    describe_parser = sub.add_parser("describe", parents=[common], help="one control and neighbor lines", allow_abbrev=False)
    describe_parser.add_argument("snapshot")
    describe_parser.add_argument("--target", required=True)
    describe_parser.add_argument("--context", type=_bounded(CONTEXT_MAX), default=CONTEXT_DEFAULT)
    sub.add_parser("operations", parents=[common], help="list commands", allow_abbrev=False)
    return parser


def dispatch(args: argparse.Namespace) -> tuple[dict, str, int]:
    if args.command == "operations":
        payload = operations()
        return payload, operations_text(payload), 0
    if args.command == "survey":
        if args.limit < 1:
            raise InspectError("limit must be at least 1", f"use 1..{SURVEY_LIMIT_MAX}")
        payload = survey_page(
            url=target_url(args.target), browser_name=args.browser, profile=args.profile, headed=args.headed,
            channel=args.channel or None, include_hidden=args.include_hidden, role=args.role,
            start=args.start, limit=args.limit,
        )
        return payload, survey_text(payload), 0
    snapshot = read_snapshot(args.snapshot)
    elements = snapshot["elements"]
    if args.command == "count":
        payload = count_elements(elements, query=args.query, role=args.role, threshold=args.threshold)
        return payload, count_text(payload), 0
    if args.command == "locate":
        if args.limit < 1:
            raise InspectError("limit must be at least 1", f"use 1..{PAGE_LIMIT_MAX}")
        payload = locate(
            elements, query=args.query, role=args.role, threshold=args.threshold,
            start=args.start, limit=args.limit, unique=args.unique,
        )
        return payload, locate_text(payload), 0 if payload["ok"] else 1
    if args.context < 0:
        raise InspectError("context must be at least 0", f"use 0..{CONTEXT_MAX}")
    payload = describe_element(elements, args.target, context=args.context)
    return payload, describe_text(payload), 0 if payload["ok"] else 1


def emit(payload: dict, text: str, code: int, args: argparse.Namespace) -> int:
    raw = dumps(payload)
    if args.out:
        path = Path(args.out)
        if not path.parent.exists():
            sys.stderr.write(f"error: directory does not exist: {path.parent}\nhint: create the directory before --out\n")
            return 2
        try:
            path.write_text(raw, encoding="utf-8", newline="\n")
        except OSError as exc:
            sys.stderr.write(f"error: cannot write {path}: {exc}\nhint: choose a writable file path\n")
            return 2
    if args.json or not payload.get("ok", True):
        if args.json:
            sys.stdout.write(raw)
        else:
            sys.stderr.write(text)
    else:
        sys.stdout.write(text)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code is None else int(code)
    try:
        payload, text, code = dispatch(args)
    except InspectError as exc:
        payload = error_envelope(args.command, exc)
        return emit(payload, error_text(payload), exc.code, args)
    return emit(payload, text, code, args)


if __name__ == "__main__":
    raise SystemExit(main())
