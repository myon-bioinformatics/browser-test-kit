#!/usr/bin/env python3
"""btk: browser-test-kit's stdlib-only operations in one file.

Commands:
  fetch   fetch one archive from an allowed host, verify its integrity, and extract only named members
  plan    recommend the lightest ``playwright install`` for each workflow job of a checkout

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
import os
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


def build_parser() -> argparse.ArgumentParser:
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
    args = build_parser().parse_args(argv)
    try:
        source, integrity, members = resolve(args)
        payload = fetch_members(source, integrity, members, args.dest)
    except (FetchError, OSError, tarfile.TarError) as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
        return 2
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


# ---- plan ------------------------------------------------------------------------------

INSTALL = re.compile(r"playwright(?:@[\w.]+)?\s+install\b([^\n]*)")
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


# ---- command line ----------------------------------------------------------------------

COMMANDS = ("fetch", "plan")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write("usage: btk.py {fetch,plan} ...\n")
        return 0 if argv else 2
    if argv[0] == "fetch":
        return fetch_cli(argv[1:])
    if argv[0] == "plan":
        return plan_cli(argv[1:])
    sys.stderr.write(f"btk.py: unknown command {argv[0]!r}; expected one of {COMMANDS}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
