#!/usr/bin/env python3
"""btk: browser-test-kit's stdlib-only operations in one file.

Commands:
  fetch     fetch one archive from an allowed host, verify its integrity, and extract only named members
  plan      recommend the lightest ``playwright install`` for each workflow job of a checkout
  observe, act, locate, count, describe, compare, operations
            loopback page inspection (see ``btk.py observe --help``)

Stdlib only. Run as ``python -S scripts/btk.py <command> ...``. This one file is the unit to copy when the
kit is vendored: nothing else in scripts/ is needed for these commands.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import math
import os
import platform
import re
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

# ---- fetch -----------------------------------------------------------------------------

ALLOWED_HOSTS = {"registry.npmjs.org", "nodejs.org", "codeload.github.com"}
MAX_BYTES = 200 * 1024 * 1024


class FetchError(Exception):
    pass


def parse_integrity(text: str) -> tuple[str, bytes]:
    """Accept SRI (sha512-BASE64, sha256-BASE64) or a bare 64-character sha256 hex digest."""
    if text.startswith(("sha512-", "sha256-")):
        algorithm, _, encoded = text.partition("-")
        try:
            return algorithm, base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FetchError("integrity is not valid base64") from exc
    if len(text) == 64:
        try:
            return "sha256", bytes.fromhex(text)
        except ValueError as exc:
            raise FetchError("integrity is not a sha256 hex digest") from exc
    raise FetchError("integrity must be sha512-BASE64, sha256-BASE64, or a sha256 hex digest")


def check_member_name(name: str) -> str:
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts:
        raise FetchError(f"member name is not a plain relative path: {name}")
    return name


def read_archive(source: str) -> bytes:
    parts = urllib.parse.urlsplit(source)
    if parts.scheme == "https":
        if parts.hostname not in ALLOWED_HOSTS:
            raise FetchError(f"host is not allowed: {parts.hostname}")
        with urllib.request.urlopen(source, timeout=60) as response:
            data = response.read(MAX_BYTES + 1)
    elif parts.scheme == "" and os.path.isfile(source):
        # A local file path is accepted for tests and for archives already on disk.
        data = Path(source).read_bytes()
    else:
        raise FetchError("source must be an https URL on an allowed host, or a local file")
    if len(data) > MAX_BYTES:
        raise FetchError("archive is larger than the 200 MiB limit")
    return data


def fetch_members(source: str, integrity: str, members: list[str], dest: str) -> dict:
    algorithm, expected = parse_integrity(integrity)
    if not members:
        raise FetchError("name at least one member to extract")
    names = [check_member_name(name) for name in members]
    blob = read_archive(source)
    digest = hashlib.new(algorithm, blob).digest()
    if digest != expected:
        raise FetchError("archive does not match the expected integrity; nothing was extracted")
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as archive:
        for name in names:
            try:
                member = archive.getmember(name)
            except KeyError as exc:
                raise FetchError(f"member not found in archive: {name}") from exc
            if not member.isfile():
                raise FetchError(f"member is not a regular file: {name}")
            out = target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source_file:
                out.write_bytes(source_file.read())
            if member.mode & 0o111:
                out.chmod(0o755)
            written.append(str(out))
    return {"ok": True, "algorithm": algorithm, "files": written}


def load_part(lock_path: str, name: str) -> dict:
    """One part from parts.lock.json: its source, integrity, and the archive member it needs."""
    try:
        lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FetchError(f"cannot read lock file: {lock_path}") from exc
    if lock.get("schema") != "btk-parts-lock/1":
        raise FetchError("lock file schema is not btk-parts-lock/1")
    part = (lock.get("parts") or {}).get(name)
    if not isinstance(part, dict):
        raise FetchError(f"no part named {name} in the lock file")
    if not part.get("integrity") or not part.get("source") or not part.get("member"):
        raise FetchError(f"part {name} cannot be fetched: it has no source, integrity, or member")
    return part


def fetch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btk.py fetch", description="Fetch one archive member; integrity is checked before extraction.")
    parser.add_argument("source", nargs="?", help="https URL on an allowed host, or a local archive path")
    parser.add_argument("--integrity", help="sha512-BASE64 or sha256-BASE64 from the registry")
    parser.add_argument("--member", action="append", default=[], help="path inside the archive (repeatable)")
    parser.add_argument("--lock", help="parts.lock.json; use with --part instead of source, integrity, and member")
    parser.add_argument("--part", help="part name in the lock file, for example node")
    parser.add_argument("--dest", required=True, help="directory to extract into")
    return parser


def resolve(args) -> tuple[str, str, list[str]]:
    if args.lock or args.part:
        if not (args.lock and args.part):
            raise FetchError("--lock and --part go together")
        part = load_part(args.lock, args.part)
        return part["source"], part["integrity"], [part["member"]]
    if not (args.source and args.integrity and args.member):
        raise FetchError("give source, --integrity, and --member, or use --lock with --part")
    return args.source, args.integrity, args.member


def fetch_cli(argv: list[str] | None = None) -> int:
    args = fetch_parser().parse_args(argv)
    try:
        source, integrity, members = resolve(args)
        payload = fetch_members(source, integrity, members, args.dest)
    except (FetchError, OSError, tarfile.TarError) as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


# ---- plan ------------------------------------------------------------------------------

INSTALL = re.compile(r"playwright(?:@[\w.]+)?\s+install(?![\w-])([^\n]*)")
CONFIG_NAMES = re.compile(r"^playwright\.config\.(?:ts|js|mjs|cjs)$")
DEVICES = {"Desktop Chrome": "chromium", "Pixel": "chromium", "Galaxy": "chromium", "Desktop Edge": "chromium",
           "Desktop Firefox": "firefox", "Desktop Safari": "webkit", "iPhone": "webkit", "iPad": "webkit"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist"}


def walk(root):
    for directory, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield os.path.join(directory, name)


def read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return ""


def config_facts(root):
    """Union over Playwright configs: engines used and whether the full build is required."""
    engines, full_reasons = set(), []
    for path in walk(root):
        if not CONFIG_NAMES.match(os.path.basename(path)):
            continue
        text = read(path)
        rel = os.path.relpath(path, root)
        engines |= set(re.findall(r"browserName\s*:\s*['\"](chromium|firefox|webkit)['\"]", text))
        engines |= set(re.findall(r"name\s*:\s*['\"](?:[\w-]*-)?(chromium|firefox|webkit)['\"]", text))
        for device, engine in DEVICES.items():
            if re.search(r"devices\[\s*['\"]" + re.escape(device), text):
                engines.add(engine)
        if re.search(r"channel\s*:\s*['\"]chromium['\"]", text):
            full_reasons.append(f"{rel} uses channel 'chromium'")
        if re.search(r"headless\s*:\s*false", text):
            full_reasons.append(f"{rel} sets headless: false")
    return engines, full_reasons


def jobs(text):
    """Split a workflow into (job name, start line, lines) by indentation under ``jobs:``."""
    lines = text.splitlines()
    out, current, start, inside = [], None, 0, False
    for number, line in enumerate(lines, 1):
        if re.match(r"^jobs\s*:", line):
            inside = True
            continue
        match = re.match(r"^  ([A-Za-z0-9_-]+)\s*:", line) if inside else None
        if match:
            if current:
                out.append((current, start, lines[start - 1:number - 1]))
            current, start = match.group(1), number
    if current:
        out.append((current, start, lines[start - 1:]))
    return out


def chromium_modes(after):
    """Return whether later commands launch bundled Chromium headed and/or headless.

    ``for name in ... chromium ...`` makes ``$name`` a Chromium launch. A later
    ``for`` of the same name replaces that set. ``--channel`` is a branded browser.
    """
    chromium_vars = {}
    for line in after.splitlines():
        match = re.search(r"\bfor\s+(\w+)\s+in\s+([^;\n]+)", line)
        if match:
            chromium_vars[match.group(1)] = bool(re.search(r"\bchromium\b", match.group(2)))
    full = shell = False
    for line in after.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for target in re.findall(r"--browser(?:=|\s+)[\"']?\$?(\w+)", line):
            if target != "chromium" and not chromium_vars.get(target):
                continue
            if re.search(r"--channel\b", line):
                continue
            if re.search(r"--headed\b", line):
                full = True
            else:
                shell = True
    return full, shell


def plan(root):
    engines, full_reasons = config_facts(root)
    rows = []
    workflows = os.path.join(root, ".github", "workflows")
    names = sorted(n for n in os.listdir(workflows) if n.endswith((".yml", ".yaml"))) if os.path.isdir(workflows) else []
    for name in names:
        rel = os.path.join(".github", "workflows", name)
        for job, start, body in jobs(read(os.path.join(workflows, name))):
            for offset, line in enumerate(body):
                match = INSTALL.search(line)
                if not match or line.lstrip().startswith("#"):
                    continue
                words = match.group(1).split()
                flags = {w for w in words if w.startswith("-")}
                targets = {w for w in words if not w.startswith("-")}
                where = f"{rel}:{start + offset}"
                after = "\n".join(body[offset + 1:])
                if targets - {"chromium", "firefox", "webkit"} or "chromium" not in targets:
                    if engines and targets & {"firefox", "webkit"} - engines:
                        rows.append(("warn", where, f"installs {', '.join(sorted(targets & {'firefox', 'webkit'} - engines))} but no config project uses it"))
                    continue
                uses_config = bool(re.search(r"playwright\s+test\b|npm\s+(?:run\s+)?test|npx\s+playwright\s+test", after))
                uses_cli = bool(re.search(r"playwright\s+(?:screenshot|pdf)\b", after))
                headed = bool(re.search(r"--headed\b", after))
                _launch_full, launch_shell = chromium_modes(after)
                needs_full = _launch_full or headed or (uses_config and bool(full_reasons))
                needs_shell = launch_shell or uses_cli or not (uses_config and full_reasons) and not headed
                if needs_full and needs_shell:
                    want, why = None, "job uses both the full build and the shell"
                elif needs_full:
                    want, why = "--no-shell", "; ".join(full_reasons) if not headed else "job runs --headed"
                else:
                    want, why = "--only-shell", "job runs headless only"
                have = "--only-shell" if "--only-shell" in flags else ("--no-shell" if "--no-shell" in flags else None)
                if want == have:
                    rows.append(("ok", where, f"{have or 'full + shell'} ({why})"))
                elif want is None:
                    rows.append(("suggest", where, f"remove {have} ({why})"))
                else:
                    rows.append(("suggest", where, f"{'replace ' + have + ' with' if have else 'add'} {want} ({why})"))
                if engines and targets & {"firefox", "webkit"} - engines:
                    rows.append(("warn", where, f"installs {', '.join(sorted(targets & {'firefox', 'webkit'} - engines))} but no config project uses it"))
    return rows


def plan_cli(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Recommend the lightest playwright install for each workflow job.")
    parser.add_argument("root", nargs="?", default=".", help="checkout to inspect (default: .)")
    root = parser.parse_args(argv).root
    if not os.path.isdir(root):
        print(f"btk.py plan: not a directory: {root}", file=sys.stderr)
        return 2
    rows = plan(root)
    for state, where, text in rows:
        print(f"{state:7} {where} {text}")
    if not rows:
        print("no playwright install lines in .github/workflows")
    return 1 if any(state == "suggest" for state, _, _ in rows) else 0


# ---- page inspection -------------------------------------------------------------------


SCHEMA_INSPECT = "btk-page-inspect/1"
SCHEMA_OBSERVE = "btk-page-observe/1"
SCHEMA_COMPARE = "btk-page-compare/1"
COMPARE_ENVIRONMENT_KEYS = ("os", "browser", "profile", "headless")
COMPLETE_COVERAGE = {"complete", "complete_within_window"}
INTERACTIVE_ROLES = {
    "button", "link", "textbox", "searchbox", "checkbox", "radio", "combobox",
    "slider", "spinbutton", "switch", "tab", "menuitem",
}
ACT_ACTIONS = {"click", "dblclick", "hover", "focus", "check", "uncheck", "fill", "press", "select", "wait_for_timeout", "settle", "goto"}
# Each action maps to the Playwright method of the same meaning. press without a locator sends the key to the page.
ACT_TEXT_ACTIONS = {"fill", "press", "select", "goto"}
MAX_STEPS = 20
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
    """UTF-16 code units, including unpaired surrogates that str.encode rejects."""
    units = []
    for char in text:
        code = ord(char)
        if code > 0xFFFF:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)
    return tuple(units)


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


def _unpaired_surrogate(units: tuple[int, ...]) -> bool:
    index = 0
    while index < len(units):
        unit = units[index]
        if 0xD800 <= unit <= 0xDBFF:
            if index + 1 < len(units) and 0xDC00 <= units[index + 1] <= 0xDFFF:
                index += 2
                continue
            return True
        if 0xDC00 <= unit <= 0xDFFF:
            return True
        index += 1
    return False


def storage_fingerprint(value: str) -> dict:
    """SHA-256 of a storage value. The value itself is not returned."""
    if not isinstance(value, str):
        raise InspectError("storage value must be a string", "fingerprint the host string, then drop the value")
    units = utf16_units(value)
    if _unpaired_surrogate(units):
        raw = bytes([0xFF]) + b"".join(unit.to_bytes(2, "little") for unit in units)
        encoding = "utf16le-unpaired"
    else:
        raw = value.encode("utf-8")
        encoding = "utf8"
    return {"fingerprint_version": 2, "encoding": encoding, "sha256": hashlib.sha256(raw).hexdigest()}


def evidence_relation(left, right) -> str:
    """Same, different, or unknown. Missing, truncated, and unrequested coverage is never same."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return "unknown"
    if left.get("coverage") not in COMPLETE_COVERAGE or right.get("coverage") not in COMPLETE_COVERAGE:
        return "unknown"
    left_digest = left.get("digest")
    right_digest = right.get("digest")
    if not isinstance(left_digest, str) or not isinstance(right_digest, str) or not left_digest or not right_digest:
        return "unknown"
    return "same" if left_digest == right_digest else "different"


def loopback_target(target: str) -> str:
    """Accept only http(s) on 127.0.0.1 or ::1 with an explicit port."""
    if not isinstance(target, str) or not (target.startswith("http://") or target.startswith("https://")):
        raise InspectError(
            "target must be an http or https loopback URL",
            "hostnames, file URLs, and other schemes are rejected",
        )
    try:
        parts = urllib.parse.urlsplit(target)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise InspectError(
            "target is not a loopback URL",
            "use http://127.0.0.1:PORT/path or http://[::1]:PORT/path",
        ) from exc
    if parts.username or parts.password:
        raise InspectError(
            "URL must not include credentials",
            "use http://127.0.0.1:PORT/path with no user or password",
        )
    if host not in {"127.0.0.1", "::1"}:
        raise InspectError(
            "target host must be a loopback address",
            "use 127.0.0.1 or [::1] with an explicit port; localhost and other hosts are rejected",
        )
    if port is None:
        raise InspectError(
            "target needs an explicit port",
            "write the port; implicit 80 and 443 are rejected",
        )
    return target


def clip(value: str, limit: int = 120) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def os_name() -> str:
    return {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system())


def _require_str(item: dict, key: str) -> str:
    value = item.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InspectError(f"{key} must be a string", "the observe payload was modified; run observe again", stage="inspect")
    return value


def _require_bool(item: dict, key: str, default: bool | None = None) -> bool:
    if key not in item and default is not None:
        return default
    value = item.get(key)
    if not isinstance(value, bool):
        raise InspectError(f"{key} must be a boolean", "the observe payload was modified; run observe again", stage="inspect")
    return value


def _box(item: dict) -> dict:
    raw = item.get("box")
    if not isinstance(raw, dict):
        raise InspectError("box must be an object", "the observe payload was modified; run observe again", stage="inspect")
    box = {}
    for key in ("x", "y", "width", "height"):
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise InspectError(f"box.{key} must be a finite number", "the observe payload was modified; run observe again", stage="inspect")
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
    """Turn collected controls into addressed elements and one page of them."""
    if not isinstance(raw, dict) or not isinstance(raw.get("elements"), list):
        raise InspectError("observe payload has no elements list", "run observe again", stage="inspect")
    _check_page(start, limit, SURVEY_LIMIT_MAX)
    prepared = []
    counts: dict[tuple[str, str], int] = {}
    nths = []
    for item in raw["elements"]:
        if not isinstance(item, dict):
            raise InspectError("observe element must be an object", "run observe again", stage="inspect")
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
        raise InspectError("role address has a bad percent escape", "copy the address from observe or locate")
    return urllib.parse.unquote(value)


def _split_role_address(value: str) -> tuple[str, str, int]:
    match = _ROLE_ADDRESS.fullmatch(value)
    if not match:
        raise InspectError("role address must look like role:button/Save%20draft#0", "copy an address from locate or observe")
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
        "hint": "h:N is valid only in the snapshot that minted it; reuse an address or run observe again",
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
        {"name": "observe", "needs": "playwright", "summary": "Passive CDP snapshot of one loopback page",
         "limit_default": SURVEY_LIMIT_DEFAULT, "limit_max": SURVEY_LIMIT_MAX},
        {"name": "act", "needs": "playwright", "summary": "One declared action that re-queries a locator",
         "limit_default": None, "limit_max": None},
        {"name": "count", "needs": "snapshot", "summary": "Count matches and roles without element bodies",
         "limit_default": None, "limit_max": None},
        {"name": "locate", "needs": "snapshot", "summary": "Rank controls by longest-common-substring similarity and page them",
         "limit_default": PAGE_LIMIT_DEFAULT, "limit_max": PAGE_LIMIT_MAX},
        {"name": "describe", "needs": "snapshot", "summary": "Return one control, its locators, and a few neighbor lines",
         "limit_default": CONTEXT_DEFAULT, "limit_max": CONTEXT_MAX},
        {"name": "compare", "needs": "snapshot", "summary": "Compare two observe snapshots by section relation and counts",
         "limit_default": None, "limit_max": None},
        {"name": "operations", "needs": "none", "summary": "List these commands",
         "limit_default": None, "limit_max": None},
    ]
    return {
        "schema": SCHEMA_INSPECT, "ok": True, "operation": "operations", "items": items,
        "hint": "observe, locate, and act are separate. count before locate; act re-queries an address and rejects h:N",
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


def strip_userinfo(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return url
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def restrict_request(route):
    """Stay on loopback and do not follow redirects. This does not call the page."""
    try:
        loopback_target(route.request.url)
    except InspectError:
        route.abort("blockedbyclient")
        return
    response = route.fetch(max_redirects=0)
    if 300 <= response.status < 400:
        route.abort("blockedbyclient")
    else:
        route.fulfill(response=response)


def _section(source: str | None, coverage: str, body: dict | None = None) -> dict:
    payload = {"source": source, "coverage": coverage}
    if body:
        payload.update(body)
    if coverage in COMPLETE_COVERAGE:
        canonical = json.dumps(body or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload["digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def assemble_observe(raw: dict, *, environment: dict, url: str, start: int, limit: int, sections: dict, limits: dict) -> dict:
    normalized = normalize_elements(raw, start=start, limit=limit)
    hints = [
        "h:N is an ordinal in this snapshot only. act rejects it and queries the address again",
        "a missing or not_requested section is not evidence that the page had nothing",
    ]
    if raw.get("child_frames"):
        hints.append("child frames were counted and their documents were not entered")
    hints.append("DOM attributes are not read inside shadow roots; accessibility names may still include open-shadow controls")
    if normalized["truncated"]:
        hints.append("this snapshot is a page of the observe result; raise --limit or pass --role")
    child_frames = raw.get("child_frames") or 0
    if isinstance(child_frames, bool) or not isinstance(child_frames, int):
        raise InspectError("child_frames must be an integer", "run observe again", stage="inspect")
    return {
        "schema": SCHEMA_OBSERVE,
        "ok": True,
        "url": strip_userinfo(url),
        "title": clip(str(raw.get("title") or ""), 200),
        "environment": environment,
        "limits": limits,
        "sections": sections,
        "child_frames": child_frames,
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


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise InspectError(
            "Playwright is not available in this interpreter",
            "observe and act need the browser extra; count, locate, describe, and operations run under python -S",
            stage="launch",
        ) from exc
    return sync_playwright


def _environment(browser, browser_name, channel, headed, profile, viewport) -> dict:
    return {
        "os": os_name(),
        "browser": browser_name,
        "version": browser.version,
        "channel": channel,
        "headless": not headed,
        "profile": profile,
        "viewport": {"width": viewport.get("width"), "height": viewport.get("height")},
    }


def _unavailable_sections(reason: str) -> dict:
    body = {"reason": reason}
    return {
        "dom": _section(None, "unavailable", body),
        "accessibility": _section(None, "unavailable", body),
        "scripts": _section(None, "unavailable", body),
        "resources": _section(None, "unavailable", body),
        "network": _section(None, "unavailable", body),
        "console": _section(None, "unavailable", body),
        "storage": _section(None, "not_requested"),
        "frames": _section(None, "unavailable", body),
        "shadow_roots": _section(None, "unavailable", body),
    }


def _content_digest(items: list) -> str:
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ax_text(field) -> str:
    if isinstance(field, dict) and field.get("value") is not None:
        return str(field.get("value"))
    return ""


def _walk_dom(node, found: list) -> bool:
    truncated = False
    if node.get("nodeType") == 1:
        if len(found) >= HARD_CAP:
            return True
        attrs = node.get("attributes") or []
        names = []
        values = {}
        for index in range(0, len(attrs) - 1, 2):
            names.append(str(attrs[index]))
            values[str(attrs[index])] = attrs[index + 1]
        tag = str(node.get("nodeName") or "").lower()
        found.append({
            "node_id": node.get("nodeId"),
            "backend_id": node.get("backendNodeId"),
            "tag": tag,
            "attr_names": names,
            "id": str(values.get("id") or ""),
            "testid": str(values.get("data-testid") or ""),
            "hidden_attr": "hidden" in names or values.get("aria-hidden") == "true",
            "script_src": str(values.get("src") or "") if tag == "script" else "",
            "inline_script": tag == "script" and "src" not in names,
        })
    for child in node.get("children") or []:
        if _walk_dom(child, found):
            truncated = True
            break
    return truncated


def _frame_count(node) -> int:
    return 1 + sum(_frame_count(child) for child in node.get("childFrames") or [])


def frame_rows(frame_tree: dict, *, limit: int = HARD_CAP) -> tuple[list, bool]:
    """Child frames in document order: name, URL, and origin only. Frame ids change per load, so they are not listed."""
    rows: list[dict] = []
    stack = list(reversed(frame_tree.get("childFrames") or []))
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if len(rows) >= limit:
            return rows, True
        frame = node.get("frame") or {}
        rows.append({
            "name": clip(str(frame.get("name") or ""), 120),
            "url": strip_userinfo(str(frame.get("url") or "")),
            "origin": clip(str(frame.get("securityOrigin") or ""), 200),
        })
        stack.extend(reversed(node.get("childFrames") or []))
    return rows, False


def count_shadow_roots(root: dict, *, limit: int = HARD_CAP * 10) -> dict:
    """Count open and closed shadow roots in a pierced DOM tree. Roots are counted, never entered.

    Walks children and shadowRoots of the main document only; child frame documents are not descended.
    """
    opened = closed = user_agent = visited = 0
    truncated = False
    stack = [root]
    while stack:
        node = stack.pop()
        visited += 1
        if visited > limit:
            truncated = True
            break
        for shadow in node.get("shadowRoots") or []:
            kind = shadow.get("shadowRootType")
            if kind == "user-agent":
                user_agent += 1
            elif kind == "closed":
                closed += 1
            else:
                opened += 1
            stack.append(shadow)
        stack.extend(node.get("children") or [])
    return {"open": opened, "closed": closed, "count": opened + closed, "user_agent": user_agent, "truncated": truncated}


def _controls_from_cdp(dom_nodes, ax_nodes, *, include_hidden: bool, role: str) -> tuple[list, dict]:
    by_backend = {node["backend_id"]: node for node in dom_nodes if node.get("backend_id") is not None}
    id_counts: dict[str, int] = {}
    testid_counts: dict[str, int] = {}
    for node in dom_nodes:
        if node["id"]:
            id_counts[node["id"]] = id_counts.get(node["id"], 0) + 1
        if node["testid"]:
            testid_counts[node["testid"]] = testid_counts.get(node["testid"], 0) + 1
    elements = []
    wanted = role.lower()
    for ax in ax_nodes:
        if ax.get("ignored") and not include_hidden:
            continue
        role_name = _ax_text(ax.get("role")).lower()
        if role_name not in INTERACTIVE_ROLES:
            continue
        if wanted and role_name != wanted:
            continue
        dom = by_backend.get(ax.get("backendDOMNodeId"), {})
        if dom.get("hidden_attr") and not include_hidden:
            continue
        disabled = False
        for prop in ax.get("properties") or []:
            if prop.get("name") == "disabled" and isinstance(prop.get("value"), dict) and prop["value"].get("value") is True:
                disabled = True
        element_id = dom.get("id") or ""
        testid = dom.get("testid") or ""
        name = clip(_ax_text(ax.get("name")))
        elements.append({
            "tag": dom.get("tag") or "",
            "role": role_name,
            "name": name,
            "text": name,
            "id": element_id,
            "testid": testid,
            "href": "",
            "visible": not bool(ax.get("ignored") or dom.get("hidden_attr")),
            "enabled": not disabled,
            "in_viewport": True,
            "obscured": False,
            "box": {"x": 0, "y": 0, "width": 0, "height": 0},
            "parent_tag": "",
            "css": f"#{element_id}" if element_id and id_counts.get(element_id) == 1 else "",
            "id_unique": bool(element_id) and id_counts.get(element_id) == 1,
            "testid_unique": bool(testid) and testid_counts.get(testid) == 1,
            "css_unique": bool(element_id) and id_counts.get(element_id) == 1,
        })
    scripts = []
    for node in dom_nodes:
        if node["tag"] != "script":
            continue
        if node["script_src"]:
            scripts.append({"kind": "external", "url": strip_userinfo(node["script_src"])})
        elif node["inline_script"]:
            scripts.append({"kind": "inline"})
    return elements, {"scripts": scripts, "dom_nodes": len(dom_nodes), "ax_nodes": len(ax_nodes)}


def _storage_section(client, origin: str, *, keys: bool, fingerprints: bool, sent: list) -> dict:
    if not keys and not fingerprints:
        return _section(None, "not_requested")
    if fingerprints and not keys:
        raise InspectError(
            "storage fingerprints require key names",
            "pass --include-storage-keys with --include-storage-fingerprints",
        )
    try:
        sent.append("DOMStorage.enable")
        client.send("DOMStorage.enable")
        sent.append("DOMStorage.getDOMStorageItems")
        local = client.send("DOMStorage.getDOMStorageItems", {"storageId": {"securityOrigin": origin, "isLocalStorage": True}})
        session = client.send("DOMStorage.getDOMStorageItems", {"storageId": {"securityOrigin": origin, "isLocalStorage": False}})
        sent.append("Network.getCookies")
        cookies = client.send("Network.getCookies")
    except Exception as exc:
        return _section("cdp:DOMStorage", "unavailable", {"reason": type(exc).__name__})
    areas = []
    for kind, rows in (("local", local.get("entries") or []), ("session", session.get("entries") or [])):
        items = []
        for row in rows:
            if not isinstance(row, list) or not row:
                continue
            key = str(row[0])
            item = {"key": key}
            if fingerprints and len(row) > 1:
                item.update(storage_fingerprint(str(row[1])))
            items.append(item)
        areas.append({"area": kind, "items": items})
    cookie_items = []
    for cookie in cookies.get("cookies") or []:
        item = {"key": str(cookie.get("name") or ""), "domain": cookie.get("domain") or "", "path": cookie.get("path") or ""}
        if fingerprints:
            item.update(storage_fingerprint(str(cookie.get("value") or "")))
        cookie_items.append(item)
    areas.append({"area": "cookie", "items": cookie_items})
    return _section("cdp:DOMStorage+Network.getCookies", "complete", {"areas": areas, "values": "redacted"})


def _cdp_send(client, method: str, params: dict | None, sent: list):
    if method in {"Runtime.evaluate", "Runtime.callFunctionOn"}:
        raise InspectError(
            "observe does not call page JavaScript",
            "act is the command that lets Playwright resolve a locator",
            stage="inspect",
        )
    sent.append(method)
    return client.send(method, params or {})


def _with_browser(url, browser_name, profile, headed, channel):
    sync_playwright = _playwright()
    playwright = sync_playwright().start()
    browser = None
    try:
        kwargs = {"headless": not headed}
        if channel:
            kwargs["channel"] = channel
        try:
            browser = getattr(playwright, browser_name).launch(**kwargs)
        except Exception as exc:
            raise InspectError(
                f"{type(exc).__name__}: {exc}",
                "install the browser that matches this Playwright build. Headless commands use the shell build; --headed needs the full browser",
                stage="launch",
            ) from exc
        options = context_options(playwright.devices, browser_name, profile, headed)
        context = browser.new_context(**options, service_workers="block")
        context.route("**/*", restrict_request)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(30000)
        return playwright, browser, page
    except Exception:
        if browser is not None:
            _close_browser(browser)
        playwright.stop()
        raise


def _finish(playwright, browser, failure, result):
    close_note = _close_browser(browser)
    try:
        playwright.stop()
    except Exception as exc:
        extra = f"{type(exc).__name__}: {exc}"
        close_note = f"{close_note}; {extra}" if close_note else extra
    if failure is not None:
        if close_note:
            failure.hint = failure.hint + f" Browser close also failed: {close_note}"
        raise failure
    if close_note:
        raise InspectError("browser close failed", close_note, stage="cleanup")
    return result


def observe_page(*, url: str, browser_name: str, profile: str, headed: bool, channel: str | None,
                 include_hidden: bool, include_storage_keys: bool, include_storage_fingerprints: bool,
                 role: str, start: int, limit: int, steps: list | None = None) -> list[dict]:
    """The first observation, then one observation after each step in the same browser, in order."""
    url = loopback_target(url)
    playwright, browser, page = _with_browser(url, browser_name, profile, headed, channel)
    failure = None
    results: list[dict] = []
    try:
        sent: list[str] = []
        network: list[dict] = []
        console: list[dict] = []
        state = {"network_truncated": False, "console_truncated": False}
        client = None
        try:
            client = page.context.new_cdp_session(page)
        except Exception as exc:
            viewport = page.viewport_size or {}
            limits = {
                "page_js_called": False,
                "navigation_runs_page_scripts": False,
                "service_workers": "blocked",
                "reason": "cdp_session_unavailable",
                "detail": type(exc).__name__,
                "cdp_methods": sent,
            }
            results.append(assemble_observe(
                {"title": "", "elements": [], "child_frames": 0, "total": 0, "truncated": False},
                environment=_environment(browser, browser_name, channel, headed, profile, viewport),
                url=url, start=start, limit=limit, sections=_unavailable_sections("cdp_session_unavailable"),
                limits=limits,
            ))
            return _finish(playwright, browser, None, results)
        # Network and console come from Playwright events, which exist in every engine. Listeners
        # are attached before navigation; the page itself is not called for them.
        def on_response(response):
            if len(network) >= 100:
                state["network_truncated"] = True
                return
            request = response.request
            network.append({
                "method": request.method or "",
                "status": response.status,
                "mime": (response.headers.get("content-type") or "").split(";")[0].strip(),
                "type": request.resource_type or "",
                "url": strip_userinfo(response.url or ""),
            })

        def on_request_failed(request):
            if len(network) >= 100:
                state["network_truncated"] = True
                return
            network.append({
                "method": request.method or "",
                "status": None,
                "mime": "",
                "type": request.resource_type or "",
                "url": strip_userinfo(request.url or ""),
                "failure": clip(request.failure or "", 200),
            })

        def on_console(message):
            if len(console) >= 50:
                state["console_truncated"] = True
                return
            console.append({"type": message.type or "", "argument_count": len(message.args)})

        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception as exc:
            raise InspectError(
                f"{type(exc).__name__}: {exc}",
                "check that the loopback server is up. Core checks serve a local fixture on 127.0.0.1",
                stage="navigate",
            ) from exc

        def capture(step: dict | None, page_js: bool) -> dict:
            document = _cdp_send(client, "DOM.getDocument", {"depth": -1, "pierce": False}, sent)
            pierced = _cdp_send(client, "DOM.getDocument", {"depth": -1, "pierce": True}, sent)
            shadow = count_shadow_roots(pierced.get("root") or {})
            ax = _cdp_send(client, "Accessibility.getFullAXTree", {}, sent)
            resources = _cdp_send(client, "Page.getResourceTree", {}, sent)
            frames = _cdp_send(client, "Page.getFrameTree", {}, sent)
            dom_nodes: list[dict] = []
            dom_truncated = _walk_dom(document.get("root") or {}, dom_nodes)
            elements, meta = _controls_from_cdp(dom_nodes, ax.get("nodes") or [], include_hidden=include_hidden, role=role)
            title = ""
            for ax_node in ax.get("nodes") or []:
                if _ax_text(ax_node.get("role")) == "RootWebArea":
                    title = clip(_ax_text(ax_node.get("name")), 200)
                    break
            child_frames = max(0, _frame_count(frames.get("frameTree") or {}) - 1)
            resource_rows = []
            for item in (resources.get("frameTree") or {}).get("resources") or []:
                resource_rows.append({
                    "type": item.get("type") or "",
                    "mime": item.get("mimeType") if isinstance(item.get("mimeType"), str) else "",
                    "url": strip_userinfo(item.get("url") or ""),
                })
            document_url = strip_userinfo(((frames.get("frameTree") or {}).get("frame") or {}).get("url") or "")
            frame_items, frame_truncated = frame_rows(frames.get("frameTree") or {})
            controls_digest = _content_digest([
                [e.get("address"), e.get("role"), e.get("name"), e.get("text")] for e in elements
            ])
            names_digest = _content_digest([
                [_ax_text(n.get("role")), _ax_text(n.get("name"))]
                for n in (ax.get("nodes") or []) if not n.get("ignored")
            ])
            origin = urllib.parse.urlsplit(page.url)
            origin_text = f"{origin.scheme}://{origin.netloc}"
            storage = _storage_section(
                client, origin_text, keys=include_storage_keys, fingerprints=include_storage_fingerprints, sent=sent,
            )
            network_coverage = "truncated" if state["network_truncated"] else "attach_limited"
            console_coverage = "truncated" if state["console_truncated"] else "attach_limited"
            sections = {
                "dom": _section("cdp:DOM.getDocument", "truncated" if dom_truncated else "complete", {
                    "nodes": meta["dom_nodes"], "attribute_values": "id and data-testid only",
                    "document_url": document_url, "title": title, "controls_sha256": controls_digest,
                }),
                "accessibility": _section("cdp:Accessibility.getFullAXTree", "complete", {
                    "nodes": meta["ax_nodes"], "names_sha256": names_digest,
                }),
                "scripts": _section("cdp:DOM.getDocument", "complete_within_window", {
                    "items": meta["scripts"], "note": "scripts with no DOM node are outside this section",
                }),
                "resources": _section("cdp:Page.getResourceTree", "complete", {
                    "items": resource_rows, "document_url": document_url,
                }),
                "network": _section("playwright:page.response", network_coverage, {
                    "prior_activity_available": False, "bodies": "not_requested", "items": network,
                }),
                "console": _section("playwright:page.console", console_coverage, {
                    "text": "not_requested", "prior_activity_available": False, "items": console,
                }),
                "storage": storage,
                "frames": _section("cdp:Page.getFrameTree", "truncated" if frame_truncated else "complete", {
                    "child_frames": child_frames, "contents": "not_entered", "items": frame_items,
                }),
                "shadow_roots": _section("cdp:DOM.getDocument pierce", "truncated" if shadow["truncated"] else "complete", {
                    "open": shadow["open"], "closed": shadow["closed"], "count": shadow["count"],
                    "user_agent": shadow["user_agent"], "contents": "not_entered",
                }),
            }
            viewport = page.viewport_size or {}
            limits = {
                "page_js_called": page_js,
                "navigation_runs_page_scripts": True,
                "network_source": "playwright events",
                "console_source": "playwright events; argument values are not read",
                "service_workers": "blocked",
                "redirects": "blocked",
                "non_loopback": "blocked",
                "cdp_methods": sent,
            }
            if step is not None:
                limits["step_runs_page_scripts"] = page_js
                limits["selector_engine"] = "playwright" if page_js else "none"
                if step["action"] == "click":
                    limits["click_runs_page_scripts"] = True
            result = assemble_observe(
                {"title": title, "elements": elements, "child_frames": child_frames, "total": len(elements), "truncated": dom_truncated},
                environment=_environment(browser, browser_name, channel, headed, profile, viewport),
                url=page.url, start=start, limit=limit, sections=sections, limits=limits,
            )
            if step is not None:
                result["step"] = step
            return result

        results.append(capture(None, False))
        for index, step in enumerate(steps or [], start=2):
            url_before = strip_userinfo(page.url)
            timeout_ms = int(step["text"]) if step["action"] == "wait_for_timeout" else 5000
            step_outcome: dict = {}
            try:
                page_js = _perform(page, step["action"], step["locator"], step["text"], timeout_ms, step_outcome)
            except InspectError:
                raise
            except Exception as exc:
                raise InspectError(
                    f"{type(exc).__name__}: {exc}",
                    "the locator was resolved on this step. If it missed, observe again and pass that address",
                    stage="inspect",
                ) from exc
            try:
                page.wait_for_load_state("load", timeout=30000)
            except Exception as exc:
                raise InspectError(
                    f"{type(exc).__name__}: {exc}",
                    "the step did not reach a loaded state; its snapshot was not written",
                    stage="navigate",
                ) from exc
            network.clear()
            console.clear()
            state["network_truncated"] = False
            state["console_truncated"] = False
            step_record = {
                "index": index,
                "action": step["action"],
                "locator": step["locator"],
                "url_before": url_before,
                "url_after": strip_userinfo(page.url),
                "hint": "network and console start empty after this step; url_before equal to url_after means it did not navigate; text values are not recorded",
            }
            if "quiet" in step_outcome:
                step_record["quiet"] = step_outcome["quiet"]
            results.append(capture(step_record, page_js))
    except InspectError as exc:
        failure = exc
    except Exception as exc:
        failure = InspectError(
            f"{type(exc).__name__}: {exc}",
            "the CDP read failed; the snapshot was not written",
            stage="inspect",
        )
    return _finish(playwright, browser, failure, results)


def _action_locator(page, locator: str):
    text = (locator or "").strip()
    if text.startswith("h:"):
        raise InspectError(
            "act does not accept a snapshot ordinal",
            "pass id:, testid:, role:, or css: so the control is queried again",
        )
    if text.startswith("id:"):
        ident = text[3:]
        if not SAFE.fullmatch(ident):
            raise InspectError("id locator has unsafe characters", "use the id: value from observe")
        return page.locator("#" + ident), True
    if text.startswith("testid:"):
        ident = text[7:]
        if not SAFE.fullmatch(ident):
            raise InspectError("testid locator has unsafe characters", "use the testid: value from observe")
        return page.get_by_test_id(ident), True
    if text.startswith("css:"):
        selector = text[4:]
        if "javascript:" in selector.lower():
            raise InspectError("css locator cannot carry a script URL", "pass a CSS selector")
        return page.locator(selector), True
    if text.startswith("role:"):
        role, name, nth = _split_role_address(text[5:])
        return page.get_by_role(role, name=name, exact=True).nth(nth), True
    raise InspectError(
        "act locator must be id:, testid:, role:, or css:",
        "observe prints those addresses; h:N is not accepted",
    )


# Quiet window: readyState is past "loading" and the document has not mutated for QUIET_MS.
# Same rule as Stagehand's quietWait (packages/integrations/core/src/facade/runtime.ts): 400 ms, polled every 100 ms.
# It runs page script (a MutationObserver), so it is only an act or step action, never part of passive observe.
QUIET_MS = 400
QUIET_POLL_MS = 100
QUIET_JS = """(() => {
  const s = window.__btkQuiet || (window.__btkQuiet = {last: performance.now(), observer: null});
  if (!s.observer) {
    s.observer = new MutationObserver(() => { s.last = performance.now(); });
    s.observer.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  }
  return document.readyState !== 'loading' && performance.now() - s.last >= %d;
})()""" % QUIET_MS


# Playwright runs the predicate inside the page (setTimeout polling, see frames.ts waitForFunctionExpression),
# so the observer and the global it leaves behind must be removed after every wait, success or timeout.
QUIET_CLEANUP_JS = (
    "(() => { const s = window.__btkQuiet; if (s && s.observer) s.observer.disconnect();"
    " delete window.__btkQuiet; })()"
)


def _wait_quiet(page, timeout_ms: int) -> bool:
    """True when the page went quiet before the timeout. A timeout is a result, not an error."""
    try:
        try:
            page.wait_for_function(QUIET_JS, polling=QUIET_POLL_MS, timeout=timeout_ms)
            return True
        except Exception as exc:
            if type(exc).__name__ == "TimeoutError":
                return False
            raise
    finally:
        try:
            page.evaluate(QUIET_CLEANUP_JS)
        except Exception:
            pass  # the page may have navigated away; a new document has no observer to remove


def _perform(page, action: str, locator: str, text, timeout_ms: int, outcome: dict | None = None) -> bool:
    """Run one declared action through the Playwright method of the same name. Returns page_js."""
    if action == "wait_for_timeout":
        page.wait_for_timeout(timeout_ms)
        return False
    if action == "goto":
        target_url = loopback_target(text)
        try:
            page.goto(target_url, wait_until="load", timeout=30000)
        except Exception as exc:
            raise InspectError(
                f"{type(exc).__name__}: {exc}",
                "check that the loopback server is up",
                stage="navigate",
            ) from exc
        return False
    if action == "settle":
        quiet = _wait_quiet(page, timeout_ms)
        if outcome is not None:
            outcome["quiet"] = quiet
        return True
    if action == "press" and isinstance(text, str):
        text = resolve_smart_key(text)
    if action == "press" and not (locator or "").strip():
        page.keyboard.press(text)
        return True
    target, page_js = _action_locator(page, locator)
    if action == "click":
        target.click(timeout=timeout_ms)
    elif action == "fill":
        target.fill(text, timeout=timeout_ms)
    elif action == "press":
        target.press(text, timeout=timeout_ms)
    elif action == "select":
        target.select_option(text, timeout=timeout_ms)
    elif action == "dblclick":
        target.dblclick(timeout=timeout_ms)
    elif action == "hover":
        target.hover(timeout=timeout_ms)
    elif action == "focus":
        target.focus(timeout=timeout_ms)
    elif action == "check":
        target.check(timeout=timeout_ms)
    elif action == "uncheck":
        target.uncheck(timeout=timeout_ms)
    return page_js


def act_page(*, url: str, browser_name: str, profile: str, headed: bool, channel: str | None,
             action: str, locator: str, text: str, timeout_ms: int) -> dict:
    url = loopback_target(url)
    if action not in ACT_ACTIONS:
        raise InspectError(
            f"unknown action {action}",
            "use one of " + ", ".join(sorted(ACT_ACTIONS)),
        )
    if action in ACT_TEXT_ACTIONS and text is None:
        raise InspectError(f"{action} needs --text", "pass the literal text, key name, or option value")
    if action == "goto":
        loopback_target(text)  # checked before any browser launch
    keyboard_only = action == "press" and not (locator or "").strip()
    if action not in ("wait_for_timeout", "settle", "goto") and not keyboard_only:
        _check_action_locator(locator)
    playwright, browser, page = _with_browser(url, browser_name, profile, headed, channel)
    failure = None
    result = None
    outcome: dict = {}
    try:
        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception as exc:
            raise InspectError(
                f"{type(exc).__name__}: {exc}",
                "check that the loopback server is up",
                stage="navigate",
            ) from exc
        page_js = False
        try:
            page_js = _perform(page, action, locator, text, timeout_ms, outcome)
        except InspectError:
            raise
        except Exception as exc:
            raise InspectError(
                f"{type(exc).__name__}: {exc}",
                "the locator was resolved on this call. If it missed, observe again and pass that address",
                stage="inspect",
            ) from exc
        if browser_name == "chromium":
            try:
                client = page.context.new_cdp_session(page)
                ax = _cdp_send(client, "Accessibility.getFullAXTree", {}, [])
                names = []
                for node in ax.get("nodes") or []:
                    role_name = _ax_text(node.get("role")).lower()
                    if role_name in INTERACTIVE_ROLES and not node.get("ignored"):
                        names.append(clip(_ax_text(node.get("name"))))
                ax_section = _section("cdp:Accessibility.getFullAXTree", "complete", {"names": names})
            except Exception as exc:
                ax_section = _section("cdp:Accessibility.getFullAXTree", "unavailable", {"reason": type(exc).__name__})
        else:
            ax_section = _section(None, "not_requested")
        viewport = page.viewport_size or {}
        result = {
            "schema": SCHEMA_INSPECT,
            "ok": True,
            "operation": "act",
            "action": action,
            "locator": locator,
            "url": strip_userinfo(page.url),
            "environment": _environment(browser, browser_name, channel, headed, profile, viewport),
            "limits": {
                "page_js_called": page_js,
                "bounded_to": [action],
                **({"quiet": outcome["quiet"]} if "quiet" in outcome else {}),
                "ordinals": "rejected",
                "dom": "not_requested",
                "selector_engine": "playwright" if page_js else "none",
            },
            "sections": {
                "url": _section("playwright:page.url", "complete", {"url": strip_userinfo(page.url)}),
                "accessibility": ax_section,
                "dom": _section(None, "not_requested"),
                "storage": _section(None, "not_requested"),
            },
            "hint": "url was captured. dom was not requested, so this result cannot say the markup was unchanged",
        }
    except InspectError as exc:
        failure = exc
    except Exception as exc:
        failure = InspectError(
            f"{type(exc).__name__}: {exc}",
            "the action failed before it could write a result",
            stage="inspect",
        )
    return _finish(playwright, browser, failure, result)


def read_snapshot(path: str) -> dict:
    file = Path(path)
    if not file.is_file():
        raise InspectError(f"snapshot not found: {path}", "run observe --out this path first")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InspectError("snapshot is not JSON", "run observe again and pass that file") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_OBSERVE:
        raise InspectError("snapshot schema is not btk-page-observe/1", "pass a file written by observe, not a locate result")
    elements = data.get("elements")
    if not isinstance(elements, list):
        raise InspectError("snapshot has no elements list", "run observe again")
    for element in elements:
        if not isinstance(element, dict) or not isinstance(element.get("address"), str) or not isinstance(element.get("handle"), str):
            raise InspectError("snapshot element is missing address or handle", "run observe again")
    return data


def _shadow_counts(snapshot: dict) -> dict | None:
    section = (snapshot.get("sections") or {}).get("shadow_roots")
    if not isinstance(section, dict) or section.get("coverage") not in COMPLETE_COVERAGE:
        return None
    counts = {}
    for key in ("open", "closed", "count"):
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        counts[key] = value
    return counts


def _count_pair(left, right) -> dict:
    delta = right - left if isinstance(left, int) and isinstance(right, int) else None
    return {"left": left, "right": right, "delta": delta}


def compare_snapshots(left: dict, right: dict) -> dict:
    """Section relations and counts for two observe snapshots. A missing side is never same."""
    left_sections = left.get("sections") or {}
    right_sections = right.get("sections") or {}
    sections = {}
    for name in sorted(set(left_sections) | set(right_sections)):
        left_part = left_sections.get(name)
        right_part = right_sections.get(name)
        sections[name] = {
            "relation": evidence_relation(left_part, right_part),
            "left": left_part.get("coverage") if isinstance(left_part, dict) else None,
            "right": right_part.get("coverage") if isinstance(right_part, dict) else None,
        }
    left_shadow = _shadow_counts(left)
    right_shadow = _shadow_counts(right)
    shadow = {key: _count_pair(*_side(left_shadow, right_shadow, key)) for key in ("open", "closed", "count")}
    left_env = left.get("environment") if isinstance(left.get("environment"), dict) else {}
    right_env = right.get("environment") if isinstance(right.get("environment"), dict) else {}
    environment = {key: [left_env.get(key), right_env.get(key)] for key in COMPARE_ENVIRONMENT_KEYS}
    same_environment = all(pair[0] == pair[1] for pair in environment.values())
    hints = [
        "same, different, and unknown are section relations; a missing or truncated section is never same",
        "shadow_roots counts are null when that section was not complete on one side",
    ]
    if not same_environment:
        hints.append("environments differ; section differences may come from the browser or profile, not the page")
    return {
        "schema": SCHEMA_COMPARE,
        "ok": True,
        "left_url": left.get("url"),
        "right_url": right.get("url"),
        "same_environment": same_environment,
        "environment": environment,
        "sections": sections,
        "shadow_roots": shadow,
        "child_frames": _count_pair(left.get("child_frames"), right.get("child_frames")),
        "elements": _count_pair(left.get("total"), right.get("total")),
        "hint": ". ".join(hints),
    }


def _side(left_shadow, right_shadow, key):
    return (
        left_shadow[key] if left_shadow else None,
        right_shadow[key] if right_shadow else None,
    )


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# Ported from Stagehand's sanitizeErrorMessage (packages/integrations/core/src/harness/redact.ts).
# Playwright exception text can carry URLs with keys, bearer tokens, or provider keys.
REDACTIONS = (
    (re.compile(r"([?&](?:signingKey|apiKey|api_key|token|key)=)[^&\s\"']+", re.IGNORECASE), r"\1[redacted]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{6})[A-Za-z0-9_-]+"), r"\1[redacted]"),
    (re.compile(r"\b(bb_(?:live|test)_[A-Za-z0-9]{4})[A-Za-z0-9_-]+"), r"\1[redacted]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "AIza[redacted]"),
    (re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE), r"\1[redacted]"),
)


def redact_text(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


# Ported from Playwright's resolveSmartModifierString (packages/playwright-core/src/server/input.ts).
# ControlOrMeta is Meta on macOS and Control elsewhere. Chords are split on "+" and each part resolved.
def resolve_smart_key(key: str, platform_name: str | None = None) -> str:
    name = sys.platform if platform_name is None else platform_name
    smart = "Meta" if name == "darwin" else "Control"
    return "+".join(smart if part == "ControlOrMeta" else part for part in key.split("+"))


def error_envelope(operation: str, exc: InspectError) -> dict:
    payload = {
        "schema": SCHEMA_INSPECT, "ok": False, "operation": operation, "stage": exc.stage,
        "error": redact_text(exc.error), "hint": redact_text(exc.hint),
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


def observe_text(payload: dict) -> str:
    env = payload["environment"]
    mode = "headless" if env.get("headless") else "headed"
    lines = [
        f"btk-page-observe/1 {env.get('os')} {env.get('browser')} {env.get('profile')} {mode} "
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


def compare_text(payload: dict) -> str:
    lines = [f"btk-page-compare/1 same_environment={str(payload['same_environment']).lower()}"]
    for name, item in payload["sections"].items():
        lines.append(f"section {name}={item['relation']} left={item['left']} right={item['right']}")
    for key in ("open", "closed", "count"):
        pair = payload["shadow_roots"][key]
        lines.append(f"shadow_roots {key} left={pair['left']} right={pair['right']} delta={pair['delta']}")
    for key in ("elements", "child_frames"):
        pair = payload[key]
        lines.append(f"{key} left={pair['left']} right={pair['right']} delta={pair['delta']}")
    lines.append(f"hint: {payload['hint']}")
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
    parser = argparse.ArgumentParser(prog="btk.py", description=__doc__.split("\n\n")[0], allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    observe = sub.add_parser("observe", parents=[common], help="passive CDP snapshot of a loopback page", allow_abbrev=False)
    observe.add_argument("target", help="http://127.0.0.1:PORT/path or http://[::1]:PORT/path")
    observe.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    observe.add_argument("--profile", choices=tuple(PROFILES), default="desktop")
    observe.add_argument("--channel", help="branded browser channel, for example chrome")
    observe.add_argument("--headed", action="store_true", help="launch the full browser instead of headless")
    observe.add_argument("--include-hidden", action="store_true", help="keep controls the accessibility tree ignored")
    observe.add_argument("--include-storage-keys", action="store_true", help="record storage key names, never values")
    observe.add_argument("--include-storage-fingerprints", action="store_true", help="add SHA-256 fingerprints; requires keys")
    observe.add_argument("--role", default="", help="only this role")
    observe.add_argument("--start", type=_bounded(100000), default=0)
    observe.add_argument("--limit", type=_bounded(SURVEY_LIMIT_MAX), default=SURVEY_LIMIT_DEFAULT)
    observe.add_argument("--after-click", metavar="LOCATOR", help="click this id:, testid:, role:, or css: address once, then take a second snapshot")
    observe.add_argument("--after-out", help="write the second snapshot here; requires --after-click and --out")
    observe.add_argument("--step", action="append", default=[], metavar="'ACTION LOCATOR [TEXT]'",
                         help="one action, then a snapshot; repeat for a sequence. LOCATOR - means none. Use with --out-dir")
    observe.add_argument("--out-dir", help="write 00-initial.json and one NN-action.json per --step here")
    act = sub.add_parser("act", parents=[common], help="one declared action that re-queries a locator", allow_abbrev=False)
    act.add_argument("target", help="loopback URL; a snapshot ordinal is not accepted")
    act.add_argument("--action", required=True, choices=tuple(sorted(ACT_ACTIONS)))
    act.add_argument("--locator", default="", help="id:, testid:, role:, or css: from observe")
    act.add_argument("--text", default=None, help="literal text for fill, key name for press (Playwright names, for example Enter or ControlOrMeta+A), option value for select, loopback URL for goto")
    act.add_argument("--timeout-ms", type=_bounded(120000), default=5000)
    act.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    act.add_argument("--profile", choices=tuple(PROFILES), default="desktop")
    act.add_argument("--channel", help="branded browser channel, for example chrome")
    act.add_argument("--headed", action="store_true")
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
    compare_parser = sub.add_parser("compare", parents=[common], help="compare two observe snapshots", allow_abbrev=False)
    compare_parser.add_argument("left")
    compare_parser.add_argument("right")
    sub.add_parser("operations", parents=[common], help="list commands", allow_abbrev=False)
    return parser


def _check_action_locator(locator: str | None) -> None:
    """Shared by act and observe --after-click: an address from observe, never a snapshot ordinal."""
    text = (locator or "").strip()
    if not text or text.startswith("h:"):
        raise InspectError(
            "act does not accept a snapshot ordinal",
            "pass id:, testid:, role:, or css: so the control is queried again",
        )
    if not text.startswith(("id:", "testid:", "role:", "css:")):
        raise InspectError(
            "act locator must be id:, testid:, role:, or css:",
            "observe prints those addresses; h:N is not accepted",
        )


def _check_sequence_args(args: argparse.Namespace) -> None:
    if args.after_click is None or args.after_out is None or not args.out:
        raise InspectError(
            "after-click needs --out for the first snapshot and --after-out for the second",
            "pass both file paths; each file is a btk-page-observe/1 snapshot",
        )
    _check_action_locator(args.after_click)
    if Path(args.out).resolve() == Path(args.after_out).resolve():
        raise InspectError("--out and --after-out must be different files", "give each snapshot its own path")
    for path in (args.out, args.after_out):
        if not Path(path).parent.is_dir():
            raise InspectError(f"directory does not exist: {Path(path).parent}", "create the directory before --out or --after-out")


def _parse_step(raw: str, index: int) -> dict:
    parts = raw.strip().split(None, 2)
    if not parts:
        raise InspectError(f"step {index} is empty", "use ACTION LOCATOR [TEXT]; LOCATOR - means none")
    action = parts[0]
    if action not in ACT_ACTIONS:
        raise InspectError(f"step {index}: unknown action {action}", "use one of " + ", ".join(sorted(ACT_ACTIONS)))
    locator = "" if len(parts) < 2 or parts[1] == "-" else parts[1]
    text = parts[2] if len(parts) == 3 else None
    if action in ACT_TEXT_ACTIONS and text is None:
        raise InspectError(f"step {index}: {action} needs TEXT", "write ACTION LOCATOR TEXT; text is not recorded in the output")
    if action == "goto":
        loopback_target(text)  # checked before any browser launch
    if action == "wait_for_timeout":
        if text is None or not re.fullmatch(r"[0-9]{1,6}", text) or int(text) > 120000:
            raise InspectError(f"step {index}: wait_for_timeout needs milliseconds 0..120000 as TEXT", "write wait_for_timeout - 500")
    elif action not in ("settle", "goto") and not (action == "press" and not locator):
        _check_action_locator(locator)
    return {"action": action, "locator": locator, "text": text}


def _check_step_args(args: argparse.Namespace) -> None:
    if args.after_click is not None or args.after_out is not None:
        raise InspectError("--step and --after-click cannot be combined", "use --step for every action")
    if args.out or not args.out_dir:
        raise InspectError("--step writes one file per snapshot, so it needs --out-dir and not --out", "pass --out-dir")
    if not Path(args.out_dir).is_dir():
        raise InspectError(f"directory does not exist: {args.out_dir}", "create the directory before --out-dir")
    if len(args.step) > MAX_STEPS:
        raise InspectError(f"at most {MAX_STEPS} steps", "split the sequence into more than one observe")


def _write_snapshot(path: str, payload: dict) -> None:
    try:
        Path(path).write_text(dumps(payload), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise InspectError(f"cannot write {path}: {exc}", "choose a writable file path") from exc


def dispatch(args: argparse.Namespace) -> tuple[dict, str, int]:
    if args.command == "operations":
        payload = operations()
        return payload, operations_text(payload), 0
    if args.command == "observe":
        if args.limit < 1:
            raise InspectError("limit must be at least 1", f"use 1..{SURVEY_LIMIT_MAX}")
        steps = None
        if args.after_click is not None or args.after_out is not None:
            _check_sequence_args(args)
            steps = [{"action": "click", "locator": args.after_click.strip(), "text": None}]
        if args.step:
            _check_step_args(args)
            steps = [_parse_step(raw, index) for index, raw in enumerate(args.step, start=1)]
        results = observe_page(
            url=args.target, browser_name=args.browser, profile=args.profile, headed=args.headed,
            channel=args.channel or None, include_hidden=args.include_hidden,
            include_storage_keys=args.include_storage_keys,
            include_storage_fingerprints=args.include_storage_fingerprints,
            role=args.role, start=args.start, limit=args.limit, steps=steps,
        )
        if args.step:
            names = ["00-initial.json"] + [
                f"{index:02d}-{step['action']}.json" for index, step in enumerate(steps, start=1)
            ]
            files = []
            for name, snapshot in zip(names, results):
                target = str(Path(args.out_dir) / name)
                _write_snapshot(target, snapshot)
                files.append(target)
            payload = {
                "schema": "btk-page-observe-steps/1",
                "ok": True,
                "files": files,
                "steps": [{"index": i, "action": step["action"], "locator": step["locator"]} for i, step in enumerate(steps, start=1)],
                "hint": "each file is a btk-page-observe/1 snapshot; compare any two. step text is not recorded",
            }
            return payload, "".join(f"wrote {name}\n" for name in files), 0
        payload = results[0]
        text_out = observe_text(payload)
        if len(results) == 2:
            _write_snapshot(args.after_out, results[1])
            text_out += f"after-click {args.after_click}: second snapshot written to {args.after_out}\n"
        return payload, text_out, 0
    if args.command == "act":
        if args.timeout_ms < 1:
            raise InspectError("timeout-ms must be at least 1", "use 1..120000")
        payload = act_page(
            url=args.target, browser_name=args.browser, profile=args.profile, headed=args.headed,
            channel=args.channel or None, action=args.action, locator=args.locator,
            text=args.text, timeout_ms=args.timeout_ms,
        )
        text_out = f"action={payload['action']} url={payload['url']}\nhint: {payload['hint']}\n"
        return payload, text_out, 0
    if args.command == "compare":
        payload = compare_snapshots(read_snapshot(args.left), read_snapshot(args.right))
        return payload, compare_text(payload), 0
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


def page_main(argv: list[str] | None = None) -> int:
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


# ---- command line ----------------------------------------------------------------------

FETCH_COMMANDS = ("fetch",)
PLAN_COMMANDS = ("plan",)
PAGE_COMMANDS = ("observe", "act", "locate", "count", "describe", "compare", "operations")
COMMANDS = FETCH_COMMANDS + PLAN_COMMANDS + PAGE_COMMANDS


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write("usage: btk.py {" + ",".join(COMMANDS) + "} ...\n")
        return 0 if argv else 2
    if argv[0] in FETCH_COMMANDS:
        return fetch_cli(argv[1:])
    if argv[0] in PLAN_COMMANDS:
        return plan_cli(argv[1:])
    if argv[0] in PAGE_COMMANDS:
        return page_main(argv)
    sys.stderr.write(f"btk.py: unknown command {argv[0]!r}; expected one of {COMMANDS}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
