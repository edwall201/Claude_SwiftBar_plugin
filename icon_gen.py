#!/usr/bin/env python3
"""Generate the orange Claude-monster icon (colored PNG) for the SwiftBar menu bar.
This is a COLOR icon, so the plugin uses `image=` (not `templateImage=`) to keep
the orange. Tweak colors/shapes here and re-run, then paste the base64 into the plugin."""
import base64
from PIL import Image, ImageDraw

SS = 8                      # supersample for smooth edges
W, H = 34, 36
img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

ORANGE = (217, 119, 87, 255)     # Claude coral/orange
DARK = (74, 47, 37, 255)         # eyes/mouth
WHITE = (255, 248, 244, 255)


def s(*v):
    return [x * SS for x in v]


# --- little horns ---
d.polygon(s(9, 8, 13, 8, 11, 1), fill=ORANGE)
d.polygon(s(21, 8, 25, 8, 23, 1), fill=ORANGE)

# --- body: rounded blob ---
d.rounded_rectangle(s(4, 6, 30, 30), radius=11 * SS, fill=ORANGE)

# --- feet ---
d.ellipse(s(7, 26, 15, 34), fill=ORANGE)
d.ellipse(s(19, 26, 27, 34), fill=ORANGE)

# --- eyes (white with dark pupils) ---
d.ellipse(s(9, 12, 16, 21), fill=WHITE)
d.ellipse(s(18, 12, 25, 21), fill=WHITE)
d.ellipse(s(11, 15, 15, 20), fill=DARK)
d.ellipse(s(20, 15, 24, 20), fill=DARK)
# eye glints
d.ellipse(s(12, 15, 13, 16), fill=WHITE)
d.ellipse(s(21, 15, 22, 16), fill=WHITE)

# --- small smile ---
d.arc(s(13, 20, 21, 26), start=15, end=165, fill=DARK, width=2 * SS)

img = img.resize((W, H), Image.LANCZOS)

# Pad with transparency so SwiftBar scales the visible creature smaller in the bar.
PAD_Y = 16          # vertical padding (more padding -> smaller icon in the menu bar)
PAD_X = 6
canvas = Image.new("RGBA", (W + 2 * PAD_X, H + 2 * PAD_Y), (0, 0, 0, 0))
canvas.alpha_composite(img, (PAD_X, PAD_Y))
img = canvas

png_path = "/Users/huangyukai/cluade_usage/monster.png"
img.save(png_path)
with open(png_path, "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode()
with open("/Users/huangyukai/cluade_usage/monster.b64", "w") as fh:
    fh.write(b64)
print("saved", png_path, "len(b64)=", len(b64))
