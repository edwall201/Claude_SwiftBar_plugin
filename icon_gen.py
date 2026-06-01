#!/usr/bin/env python3
"""Generate the white pixel-art Claude-invader icon for the SwiftBar menu bar.
The plugin uses `templateImage=` so macOS tints it to the menu-bar label color
(white on a dark bar) and it auto-adapts to light/dark mode. Only the alpha
channel matters for a template image; eyes and gaps are transparent so the bar
shows through. Edit the GRID below and re-run; the re-embed step pastes the
base64 into the plugin."""
import base64
from PIL import Image

WHITE = (255, 255, 255, 255)        # template image is tinted by macOS anyway

# '#' = orange pixel, '.' = transparent. Classic space-invader silhouette:
# wide top block, two vertical eye slots, full-width side arms, six legs.
GRID = [
    "..############..",
    "..############..",
    "..##.######.##..",
    "..##.######.##..",
    "################",
    "################",
    "################",
    "..############..",
    "..############..",
    "..#.#.#..#.#.#..",
    "..#.#.#..#.#.#..",
]

CELL = 8                            # px per grid cell
rows, cols = len(GRID), len(GRID[0])
img = Image.new("RGBA", (cols * CELL, rows * CELL), (0, 0, 0, 0))
px = img.load()
for r, line in enumerate(GRID):
    for c, ch in enumerate(line):
        if ch == "#":
            for y in range(r * CELL, r * CELL + CELL):
                for x in range(c * CELL, c * CELL + CELL):
                    px[x, y] = WHITE

# Small transparent margin so the creature isn't edge-to-edge.
PAD = 4
canvas = Image.new("RGBA", (img.width + 2 * PAD, img.height + 2 * PAD), (0, 0, 0, 0))
canvas.alpha_composite(img, (PAD, PAD))
img = canvas

# Control the on-screen size via the PNG's DPI. macOS renders a menu-bar image at
# its POINT size (points = pixels * 72 / dpi), clamped to the bar height, so a
# higher DPI makes a physically smaller icon. We target a fixed point height:
# LOWER ICON_POINT_H -> smaller icon in the menu bar.
ICON_POINT_H = 13
dpi = img.height * 72.0 / ICON_POINT_H

png_path = "/Users/huangyukai/cluade_usage/monster.png"
img.save(png_path, dpi=(dpi, dpi))
with open(png_path, "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode()
with open("/Users/huangyukai/cluade_usage/monster.b64", "w") as fh:
    fh.write(b64)
print("saved", png_path, "len(b64)=", len(b64))
