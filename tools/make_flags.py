#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draws the language flags used by the header buttons into assets/."""

import os
import sys

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 28, 20
SUPERSAMPLE = 8          # draw big, shrink down: gives clean diagonals
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BLUE = (1, 33, 105)
RED = (200, 16, 46)
PL_RED = (220, 20, 60)
WHITE = (255, 255, 255)


def flag_pl(draw, w, h):
    draw.rectangle([0, 0, w, h / 2], fill=WHITE)
    draw.rectangle([0, h / 2, w, h], fill=PL_RED)


def flag_gb(draw, w, h):
    draw.rectangle([0, 0, w, h], fill=BLUE)

    # diagonals: white band with a narrower red band on top of it
    for line in (((0, 0), (w, h)), ((w, 0), (0, h))):
        draw.line(line, fill=WHITE, width=int(h * 0.30))
        draw.line(line, fill=RED, width=int(h * 0.16))

    # cross of St George: red cross with white fimbriation
    bar = h * 0.16
    draw.rectangle([w / 2 - bar, 0, w / 2 + bar, h], fill=WHITE)
    draw.rectangle([0, h / 2 - bar, w, h / 2 + bar], fill=WHITE)
    bar = h * 0.10
    draw.rectangle([w / 2 - bar, 0, w / 2 + bar, h], fill=RED)
    draw.rectangle([0, h / 2 - bar, w, h / 2 + bar], fill=RED)


def render(painter, path):
    size = (WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    painter(ImageDraw.Draw(image), size[0], size[1])
    image = image.resize((WIDTH, HEIGHT), Image.LANCZOS)
    image.save(path)
    print(f"wrote {path} ({WIDTH}x{HEIGHT})")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    render(flag_pl, os.path.join(OUT_DIR, "flag_pl.png"))
    render(flag_gb, os.path.join(OUT_DIR, "flag_gb.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
