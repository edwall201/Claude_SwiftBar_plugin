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

# Center the creature in a large SQUARE transparent canvas. SwiftBar scales the
# whole image to fit the bar, so a small creature in a big square shrinks it
# regardless of whether width or height drives the scaling.
# Smaller CREATURE_FRACTION -> smaller icon in the menu bar.
CREATURE_FRACTION = 0.18
side = int(max(img.width, img.height) / CREATURE_FRACTION)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))
img = canvas

png_path = "/Users/huangyukai/cluade_usage/monster.png"
img.save(png_path)
with open(png_path, "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode()
with open("/Users/huangyukai/cluade_usage/monster.b64", "w") as fh:
    fh.write(b64)
print("saved", png_path, "len(b64)=", len(b64))
