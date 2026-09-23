#!/usr/bin/env python3
"""Validate screenshot evidence without image-library dependencies."""
from pathlib import Path
import struct
import sys

PNG = b"\x89PNG\r\n\x1a\n"

def dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG or data[12:16] != b"IHDR":
        raise ValueError("not a valid PNG header")
    return struct.unpack(">II", data[16:24])

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_png.py FILE [...]", file=sys.stderr)
        return 2
    for raw in sys.argv[1:]:
        path = Path(raw)
        data = path.read_bytes()
        width, height = dimensions(data)
        if width < 1 or height < 1:
            raise ValueError(f"{path}: invalid dimensions")
        print(f"{path}: png {width}x{height} {len(data)} bytes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
