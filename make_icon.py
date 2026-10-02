#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draws the application icon: icon.png and a multi-size icon.ico.

A dark rounded square with "PZ" - white P, accent-blue Z. Both files are used by
the app window and by the PyInstaller build, so re-run this only when the icon
itself should change.

    python make_icon.py
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

CANVAS = 1024                      # drawn large, the .ico holds the scaled sizes
MARGIN = 40
CORNER_RADIUS = 220
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BACKDROP = (21, 26, 42, 255)       # #151a2a - matches the dark window background
WHITE = (255, 255, 255, 255)
ACCENT = (59, 130, 246, 255)       # #3b82f6 - the app's accent colour
TEXT_WIDTH_RATIO = 0.72            # how much of the canvas the letters may take
LETTER_GAP_RATIO = 0.05


def find_font():
    """Segoe UI Bold when available, otherwise a well-known alternative."""
    for name in ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        path = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.exists(path):
            return path
    return None


def fit_font(draw, text, font_path):
    font = None
    for size in range(640, 200, -10):
        candidate = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=candidate)
        if box[2] - box[0] <= int(CANVAS * TEXT_WIDTH_RATIO):
            font = candidate
            break
    return font or (ImageFont.truetype(font_path, 240) if font_path else ImageFont.load_default())


def main():
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle([MARGIN, MARGIN, CANVAS - MARGIN, CANVAS - MARGIN],
                           radius=CORNER_RADIUS, fill=BACKDROP)

    font_path = find_font()
    if font_path is None:
        print("No system font found, falling back to Pillow's default font.")
    font = fit_font(draw, "PZ", font_path)

    def ink_metrics(char):
        """Left bearing and ink width, so the letters can be centred by eye."""
        box = draw.textbbox((0, 0), char, font=font)
        return box[0], box[2] - box[0]

    gap = int(LETTER_GAP_RATIO * CANVAS)
    bearing_p, width_p = ink_metrics("P")
    bearing_z, width_z = ink_metrics("Z")
    total = width_p + gap + width_z

    x_p = (CANVAS - total) // 2 - bearing_p
    x_z = x_p + width_p + gap - bearing_z

    full_box = draw.textbbox((0, 0), "PZ", font=font)
    y = (CANVAS - (full_box[3] - full_box[1])) // 2 - full_box[1]

    draw.text((x_p, y), "P", font=font, fill=WHITE)
    draw.text((x_z, y), "Z", font=font, fill=ACCENT)

    image.save("icon.png")
    image.save("icon.ico", sizes=ICO_SIZES)
    print("wrote icon.png and icon.ico", ICO_SIZES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
