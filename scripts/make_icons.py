"""Write plain PNG app icons (dark square, white play triangle) with the stdlib only.

Run from the repo root: python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

BG = (17, 24, 39)
FG = (255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "reels_api" / "static"


def _chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def make_icon(size: int, path: Path) -> None:
    x0, x1 = size * 0.36, size * 0.74
    y0, y1 = size * 0.26, size * 0.74
    cy = (y0 + y1) / 2
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter byte: none
        for x in range(size):
            inside = False
            if x0 <= x <= x1 and y0 <= y <= y1:
                t = (x - x0) / (x1 - x0)  # 0 at the flat left edge, 1 at the apex
                inside = abs(y - cy) <= (y1 - y0) / 2 * (1 - t)
            row += bytes(FG if inside else BG)
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_icon(192, OUT / "icon-192.png")
    make_icon(512, OUT / "icon-512.png")
    print("wrote", OUT / "icon-192.png", "and", OUT / "icon-512.png")
