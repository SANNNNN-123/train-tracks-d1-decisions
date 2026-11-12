"""Render model-owned states from the first Hugging Face decision image."""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

CHOICES = ("empty", "NS", "EW", "NE", "NW", "SE", "SW")
FOCUS_NOTE = " Purple outlines the target row and its clue; teal outlines the target column and its clue."


def grid_lines(projection, minimum):
    groups = []
    for index in np.flatnonzero(projection >= minimum):
        if not groups or index > groups[-1][-1] + 1:
            groups.append([int(index)])
        else:
            groups[-1].append(int(index))
    return [round(sum(group) / len(group)) for group in groups if len(group) <= 4]


def draw_piece(draw, box, shape):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    ports = {"N": (cx, y0), "S": (cx, y1), "W": (x0, cy), "E": (x1, cy)}
    for direction in shape:
        draw.line((cx, cy, *ports[direction]), fill="#222222",
                  width=max(3, (x1 - x0) // 22))


def detect_grid(image, rows, columns):
    # HF export adds 30 pixels of coordinate labels on the left and bottom.
    raw = np.asarray(image.crop((30, 0, image.width, image.height - 30)))
    # Dataset and rollout renderers draw every cell border in exact #666666.
    # Dark track strokes can span most of a row or column and must not become
    # false grid-line candidates.
    grid = np.all(raw == (102, 102, 102), axis=2).astype(np.uint8)
    xs = [x + 30 for x in grid_lines(grid.sum(0), raw.shape[0] * .60)]
    ys = grid_lines(grid.sum(1), raw.shape[1] * .60)
    if len(xs) != columns + 1 or len(ys) != rows + 1:
        raise ValueError("Grid detection failed on HF image")
    return xs, ys


def highlight_image(image, rows, columns, target, xs=None, ys=None):
    """Add visual focus only; preserve clues, givens, and all action marks."""
    if isinstance(image, dict):
        image = Image.open(BytesIO(image["bytes"]))
    image = image.convert("RGB").copy()
    if xs is None or ys is None:
        xs, ys = detect_grid(image, rows, columns)
    r, c = target
    if not (0 <= r < rows and 0 <= c < columns):
        raise ValueError("Target is outside the grid")
    draw = ImageDraw.Draw(image)
    purple, teal = "#9142ae", "#008b91"
    # Thin outlines mark the whole row/column without covering track strokes.
    draw.rectangle((xs[0] + 3, ys[r] + 3, xs[-1] - 3, ys[r + 1] - 3),
                   outline=purple, width=2)
    draw.rectangle((xs[c] + 5, ys[0] + 3, xs[c + 1] - 5, ys[-1] - 3),
                   outline=teal, width=2)
    # Source row clues sit to the right; column clues sit above the grid.
    draw.rectangle((xs[-1] + 5, ys[r] + 5, image.width - 5, ys[r + 1] - 5),
                   outline=purple, width=2)
    draw.rectangle((xs[c] + 5, 5, xs[c + 1] - 5, ys[0] - 6),
                   outline=teal, width=2)
    return image


class Board:
    def __init__(self, first_image, rows, columns, targets):
        if isinstance(first_image, dict):
            first_image = Image.open(BytesIO(first_image["bytes"]))
        self.source = first_image.convert("RGB")
        self.height, self.width = rows, columns
        self.unknown = targets
        self.actions = []
        self.deferred = set()
        self.xs, self.ys = detect_grid(self.source, rows, columns)

    def box(self, target):
        r, c = target
        return self.xs[c], self.ys[r], self.xs[c + 1], self.ys[r + 1]

    def render(self, target=None, visual_variant="plain"):
        image = self.source.copy()
        draw = ImageDraw.Draw(image)
        # Erase the first target's amber outline and all unknown interiors.
        # Given tracks and source clues remain untouched.
        for cell in self.unknown:
            x0, y0, x1, y1 = self.box(cell)
            draw.rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), fill="white")
            draw.rectangle((x0, y0, x1, y1), outline="#666", width=1)
        for action in self.actions:
            cell = action["row"] - 1, action["column"] - 1
            value = action["value"]
            if value in CHOICES[1:]:
                draw_piece(draw, self.box(cell), value)
            elif value == "empty":
                x0, y0, x1, y1 = self.box(cell)
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                draw.line((cx - 6, cy - 6, cx + 6, cy + 6), fill="#555555", width=2)
                draw.line((cx - 6, cy + 6, cx + 6, cy - 6), fill="#555555", width=2)
        for cell in self.deferred:
            x0, y0, x1, y1 = self.box(cell)
            draw.text(((x0 + x1) // 2 - 4, (y0 + y1) // 2 - 8), "?",
                      fill="#5173a6")
        if target is not None:
            x0, y0, x1, y1 = self.box(target)
            draw.rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), outline="#e69500", width=3)
            if visual_variant in {"focus", "counts", "ports", "defer"}:
                return highlight_image(image, self.height, self.width, target,
                                       self.xs, self.ys)
        if visual_variant not in {"plain", "focus", "counts", "ports", "defer"}:
            raise ValueError("Unknown visual variant")
        return image

    def add(self, target, value):
        r, c = target
        self.deferred.discard(target)
        self.actions.append({"row": r + 1, "column": c + 1, "value": value})

    def defer(self, target):
        self.deferred.add(target)
