# -*- coding: utf-8 -*-
"""Replace desk_icons[0] (game icon) in desktop_assets.h with a metronome icon.

FIXED VERSION: only the first 1024 values are replaced, so the original four
row braces  }, {  are preserved.  The previous version flattened all 4096
values into one inner brace and caused:
    error: too many initializers for 'const uint16_t [1024]'

Usage:
    python3 gen_metronome_icon.py path/to/desktop_assets.h
"""
import re
import sys

PATH = sys.argv[1]

BG = 0x08A4      # deep blue background used by all desk icons
INK = 0xFE8F     # bright warm white
WARM = 0xFD80    # warm amber
CYAN = 0x8FE3    # cyan accent
SHADOW = 0x10A4  # slightly lighter background

N = 32
px = [[BG for _ in range(N)] for _ in range(N)]


def put(x, y, c):
    if 0 <= x < N and 0 <= y < N:
        px[y][x] = c


def line(x0, y0, x1, y1, c, w=1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        for wy in range(-(w // 2), w // 2 + 1):
            for wx in range(-(w // 2), w // 2 + 1):
                put(x0 + wx, y0 + wy, c)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


def fill_triangle(p0, p1, p2, c):
    def sign(a, b, cpt):
        return (a[0] - cpt[0]) * (b[1] - cpt[1]) - (b[0] - cpt[0]) * (a[1] - cpt[1])
    minx = int(min(p0[0], p1[0], p2[0])); maxx = int(max(p0[1], p1[1], p2[1]))
    miny = int(min(p0[1], p1[1], p2[1])); maxy = int(max(p0[1], p1[1], p2[1]))
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            a = sign(p0, p1, (x, y)); b = sign(p1, p2, (x, y)); cc = sign(p2, p0, (x, y))
            neg = (a < 0) or (b < 0) or (cc < 0)
            pos = (a > 0) or (b > 0) or (cc > 0)
            if not (neg and pos):
                put(x, y, c)


# Metronome shape
fill_triangle((6, 27), (25, 27), (18, 11), SHADOW)
fill_triangle((7, 26), (24, 26), (17, 12), INK)
fill_triangle((10, 25), (21, 25), (17, 15), BG)
line(5, 27, 26, 27, INK, 2)
for yy in range(10, 13):
    for xx in range(16, 19):
        if (xx - 17) ** 2 + (yy - 11) ** 2 <= 2:
            put(xx, yy, WARM)
line(17, 11, 9, 3, WARM, 2)
for yy in range(2, 8):
    for xx in range(6, 13):
        if (xx - 9) ** 2 + (yy - 5) ** 2 <= 6:
            put(xx, yy, CYAN)
line(20, 4, 23, 2, SHADOW, 1)
line(23, 8, 27, 7, SHADOW, 1)

vals = ["0x%04x" % px[y][x] for y in range(N) for x in range(N)]
assert len(vals) == 1024, len(vals)

src = open(PATH, encoding="utf-8").read()
start = src.index("desk_icons[4][1024]")

# Locate the whole initializer, from the first '{' to the closing '};'.
outer_open = src.index("{", src.index("=", start))
outer_close = src.index("};", outer_open) + 1
array = src[outer_open:outer_close]

all_matches = list(re.finditer(r"0x[0-9a-fA-F]{4}", array))
assert len(all_matches) == 4096, "expected 4096 icon values, got %d" % len(all_matches)

# Preserve row separators: only replace values 0..1023 (the game icon).
first_val = outer_open + all_matches[0].start()
end_first_row = outer_open + all_matches[1023].end()

lines = [",".join(vals[i:i + 16]) for i in range(0, 1024, 16)]
new_block = ",\n".join(lines)

out = src[:first_val] + new_block + src[end_first_row:]
open(PATH, "w", encoding="utf-8").write(out)

# Verify: exactly 4 rows, 1024 values each, 3 row separators kept.
check = open(PATH, encoding="utf-8").read()
cstart = check.index("desk_icons[4][1024]")
copen = check.index("{", check.index("=", cstart))
cclose = check.index("};", copen) + 1
carray = check[copen:cclose]
rows = re.split(r"},\s*{", carray)
counts = [len(re.findall(r"0x[0-9a-fA-F]{4}", row)) for row in rows]
assert counts == [1024, 1024, 1024, 1024], "row counts wrong: %r" % counts

print("icon replaced OK: rows=%s, separators=%d" % (counts, len(rows) - 1))
