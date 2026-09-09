"""Canonical 16:9 layout coordinates shared by preview and PPTX renderers.

Coordinates are inches on a 13.333 x 7.5 PowerPoint canvas. The web preview
converts the same values to percentages, so a visual hierarchy does not need
to be separately invented for the browser and for a downloaded deck.
"""
from __future__ import annotations

SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5

# Image-backed information slide: lead statement and three compact decision
# cards on the left, constrained raster visual on the right.
IMAGE_CONTENT = {
    "lead": (0.76, 2.12, 6.55, 0.72),
    "cards": (0.76, 2.98, 6.55, 3.45),
    "card_height": 1.02,
    "card_gap": 0.14,
    "image": (8.12, 2.12, 4.45, 4.45),
}


def x_percent(value: float) -> str:
    return f"{value / SLIDE_WIDTH * 100:.3f}%"


def y_percent(value: float) -> str:
    return f"{value / SLIDE_HEIGHT * 100:.3f}%"
