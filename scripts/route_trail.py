"""Turn an emoji page trail such as '🏠 → 🗺 ↔ 🌍' into the URLs to visit, in order.

A trail names pages by their emoji identity: `A → B` goes from A to B, `A ↔ B`
goes to B and back to A (ASCII `->` and `<->` work too; spaces are ignored).
The emoji -> route registry is read from a JSON object ({route: emoji} or
{emoji: route}) or from a source file with a map literal ('/route': '🏠'), such
as a generated Dart/TS registry; `--map NAME` limits reading to one named map.

Emoji are compared without variation selectors (U+FE0E/U+FE0F), so a typed 🗺
matches a registered 🗺️; a registry whose emoji collide after that is an error.

Exit codes: 0 OK, 2 input error (unknown emoji, bad trail or registry).
"""
from __future__ import annotations

import argparse
import json
import re
import sys

GO, ROUND = "→", "↔"
_PAIR = re.compile(r"""['"](/[^'"]*)['"]\s*:\s*['"]([^'"]+)['"]""")


def norm(emoji: str) -> str:
    return re.sub(r"[\s︎️]", "", emoji)


def load_registry(text: str, *, name: str | None = None, map_name: str | None = None) -> dict:
    """Return {normalized emoji: route}. JSON when it parses as an object, else map-literal pairs."""
    pairs = None
    if (name or "").endswith(".json") or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            if map_name is not None:
                data = data.get(map_name)
                if not isinstance(data, dict):
                    raise ValueError(f"map not found: {map_name}")
            pairs = [(k, v) if str(k).startswith("/") else (v, k) for k, v in data.items()]
    if pairs is None:
        if map_name is not None:
            start = text.find(map_name)
            if start < 0:
                raise ValueError(f"map not found: {map_name}")
            end = text.find("}", start)
            text = text[start:end if end > 0 else None]
        # Values that are routes belong to alias maps, not to page identities.
        pairs = [(r, e) for r, e in _PAIR.findall(text) if not e.startswith("/")]
    registry = {}
    for route, emoji in pairs:
        if not isinstance(route, str) or not isinstance(emoji, str) or not route.startswith("/"):
            raise ValueError(f"registry entry must pair a /route with an emoji: {route!r}: {emoji!r}")
        key = norm(emoji)
        if not key:
            raise ValueError(f"empty emoji for {route}")
        if key in registry and registry[key] != route:
            raise ValueError(f"emoji {emoji} names two routes: {registry[key]} and {route}")
        registry[key] = route
    if not registry:
        raise ValueError("registry has no /route: emoji pairs")
    return registry


def parse_trail(trail: str) -> list[str]:
    """'A → B ↔ C' -> ['A', 'B', 'C', 'B'] (normalized emoji, in visiting order)."""
    text = re.sub(r"\s", "", trail).replace("<->", ROUND).replace("->", GO)
    tokens = re.split(f"([{GO}{ROUND}])", text)
    if not tokens[0] or any(not t for t in tokens[2::2]):
        raise ValueError("trail must alternate pages and arrows, e.g. '🏠 → 🗺 ↔ 🌍'")
    steps = [norm(tokens[0])]
    for arrow, page in zip(tokens[1::2], tokens[2::2]):
        previous = steps[-1]
        steps.append(norm(page))
        if arrow == ROUND:
            steps.append(previous)
    return steps


def resolve(trail: str, registry: dict, *, base: str = "http://localhost:8080/", hash_routing: bool = True) -> list[dict]:
    rows = []
    for emoji in parse_trail(trail):
        route = registry.get(emoji)
        if route is None:
            raise ValueError(f"unknown page emoji: {emoji}")
        url = base + "#" + route if hash_routing else base.rstrip("/") + route
        rows.append({"emoji": emoji, "route": route, "url": url})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trail", help="e.g. '🏠 → 🗺 ↔ 🌍' (or ASCII -> and <->)")
    parser.add_argument("--registry", required=True, help="JSON registry or a source file with '/route': 'emoji' pairs")
    parser.add_argument("--map", dest="map_name", help="read only this named map (e.g. pageEmojis)")
    parser.add_argument("--base", default="http://localhost:8080/")
    parser.add_argument("--path-routing", action="store_true", help="BASE/route instead of BASE#route")
    parser.add_argument("--json", action="store_true", help="emoji, route and url per step")
    args = parser.parse_args(argv)
    try:
        with open(args.registry, encoding="utf-8") as handle:
            registry = load_registry(handle.read(), name=args.registry, map_name=args.map_name)
        rows = resolve(args.trail, registry, base=args.base, hash_routing=not args.path_routing)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rows, ensure_ascii=False) if args.json else "\n".join(r["url"] for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
