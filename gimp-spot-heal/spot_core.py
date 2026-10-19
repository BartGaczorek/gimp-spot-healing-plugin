"""Source selection and viewport geometry; no GIMP or third-party dependencies."""
import math
from dataclasses import dataclass


@dataclass
class Viewport:
    width: int
    height: int
    zoom: float = 1.0
    x: float = 0.0
    y: float = 0.0

    def fit(self, canvas_width, canvas_height):
        self.zoom = min(1.0, max(0.01, min(canvas_width / self.width,
                                         canvas_height / self.height) * 0.96))
        self.x = (canvas_width - self.width * self.zoom) / 2
        self.y = (canvas_height - self.height * self.zoom) / 2

    def image_point(self, x, y):
        return (x - self.x) / self.zoom, (y - self.y) / self.zoom

    def zoom_at(self, factor, x, y):
        ix, iy = self.image_point(x, y)
        self.zoom = min(4.0, max(0.01, self.zoom * factor))
        self.x, self.y = x - ix * self.zoom, y - iy * self.zoom


def stroke_bounds(points, diameter, width, height):
    margin = math.ceil(diameter / 2) + 4
    x = max(0, math.floor(min(p[0] for p in points)) - margin)
    y = max(0, math.floor(min(p[1] for p in points)) - margin)
    right = min(width, math.ceil(max(p[0] for p in points)) + margin + 1)
    bottom = min(height, math.ceil(max(p[1] for p in points)) + margin + 1)
    return x, y, right - x, bottom - y


def choose_source(pixels, width, height, points, diameter):
    """Find an offset using a sparse exterior ring, never the defect interior.

    RGBA bytes are used only to rank donors. Native-precision GIMP Healing
    performs the actual reconstruction. Entire donor bounding boxes must be
    disjoint from the stroke bounding box (conservative for curved strokes).
    """
    if not points or diameter < 1:
        raise ValueError("Empty stroke or invalid diameter")
    radius = diameter / 2
    left = min(x for x, _ in points) - radius - 2
    top = min(y for _, y in points) - radius - 2
    right = max(x for x, _ in points) + radius + 2
    bottom = max(y for _, y in points) + radius + 2
    if left < 0 or top < 0 or right >= width or bottom >= height:
        raise ValueError("Zmniejsz pędzel lub odsuń go od krawędzi warstwy.")

    def pixel(x, y):
        i = (int(y) * width + int(x)) * 4
        return pixels[i:i + 4]

    # Sample the boundary of the stroke bounding box; defect stays inside it.
    ring = []
    for i in range(12):
        t = i / 11
        ring.extend(((left + (right - left) * t, top),
                     (left + (right - left) * t, bottom),
                     (left, top + (bottom - top) * t),
                     (right, top + (bottom - top) * t)))
    target = [pixel(x, y) for x, y in ring]
    if any(p[3] < 250 for p in target):
        raise ValueError("Wybierz obszar bez przezroczystości.")

    best = None
    # Bounded local search, deterministic; the nearest ring starts just
    # outside one brush diameter, outer rings up to six diameters away.
    for distance in (1.3, 2.0, 3.0, 4.5, 6.0):
        for angle in range(32):
            theta = angle * math.tau / 32
            dx = round(math.cos(theta) * max(4, diameter) * distance)
            dy = round(math.sin(theta) * max(4, diameter) * distance)
            if not (right + dx < left or left + dx > right or
                    bottom + dy < top or top + dy > bottom):
                continue
            if left + dx < 0 or top + dy < 0 or right + dx >= width or bottom + dy >= height:
                continue
            donor = [pixel(x + dx, y + dy) for x, y in ring]
            # Check donor interior too, to avoid transparent holes.
            interior = [pixel(left + dx + (right - left) * u / 4,
                              top + dy + (bottom - top) * v / 4)
                        for u in range(5) for v in range(5)]
            if any(p[3] < 250 for p in donor + interior):
                continue
            shifts = [sum(a[c] - b[c] for a, b in zip(target, donor)) / len(ring)
                      for c in range(3)]
            # Match texture after compensating a constant color difference;
            # retain a color penalty so the healer need not bridge huge shifts.
            error = sum((a[c] - b[c] - shifts[c]) ** 2
                        for a, b in zip(target, donor) for c in range(3)) / (3 * len(ring))
            score = error + 0.2 * sum(s * s for s in shifts) / 3 + 0.1 * distance
            candidate = score, dx, dy
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise ValueError("Brak odpowiedniego źródła w otoczeniu. Zmniejsz pędzel lub skróć ruch.")
    return best[1], best[2]
