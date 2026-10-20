# -*- coding: utf-8 -*-
"""Source selection and viewport geometry; compatible with Python 2.7 and 3."""
from __future__ import division
import math


class Viewport(object):
    def __init__(self, width, height, zoom=1.0, x=0.0, y=0.0):
        self.width, self.height = width, height
        self.zoom, self.x, self.y = zoom, x, y

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
    return tuple(int(v) for v in (x, y, right - x, bottom - y))


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
            theta = angle * (2 * math.pi) / 32
            dx = int(round(math.cos(theta) * max(4, diameter) * distance))
            dy = int(round(math.sin(theta) * max(4, diameter) * distance))
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


def resample_stroke(points, spacing, max_points=4096):
    """Cover every segment, including its end, with dabs no farther than spacing."""
    if not points or spacing <= 0 or max_points < 1:
        raise ValueError("Invalid stroke or spacing")
    result = [points[0]]
    for end in points[1:]:
        start = result[-1]
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length == 0:
            continue
        steps = int(math.ceil(length / spacing))
        if len(result) + steps > max_points:
            raise ValueError("Ruch jest zbyt dlugi. Podziel go na krotsze odcinki.")
        for i in range(1, steps + 1):
            t = i / steps
            result.append((start[0] + (end[0] - start[0]) * t,
                           start[1] + (end[1] - start[1]) * t))
    return result


def stroke_normal(points):
    """One global normal, from the first to the last point of an open stroke."""
    if len(points) < 2:
        raise ValueError("Linia wymaga co najmniej dwoch punktow.")
    vx = points[-1][0] - points[0][0]
    vy = points[-1][1] - points[0][1]
    length = math.hypot(vx, vy)
    if length < 1.0:
        raise ValueError("Poczatek i koniec linii sa zbyt blisko. Podziel petle na odcinki.")
    return -vy / length, vx / length


def source_is_safe(points, diameter, width, height, offset):
    """Separate entire swept brush footprints by projection onto the normal.

    A straight segment's normal projection lies between its endpoint
    projections. Disjoint padded strips therefore guarantee separation for
    every point of every segment, including curves between recorded points.
    Native donor coordinates are floored by GIMP; check those coordinates too.
    This is conservative: some non-intersecting curved paths are rejected.
    """
    nx, ny = stroke_normal(points)
    dx, dy = offset
    if abs(dx * ny - dy * nx) > 1e-7:
        return False
    radius = diameter / 2.0 + 2.0
    source = [(math.floor(x + dx), math.floor(y + dy)) for x, y in points]
    for x, y in list(points) + source:
        if x - radius < 0 or y - radius < 0 or x + radius >= width or y + radius >= height:
            return False
    target_projections = [x * nx + y * ny for x, y in points]
    source_projections = [x * nx + y * ny for x, y in source]
    gap = max(min(source_projections) - max(target_projections),
              min(target_projections) - max(source_projections))
    return gap > 2 * radius


def choose_perpendicular_sources(pixels, width, height, points, diameter):
    """Return the best safe donor per side; each offset is global and normal."""
    nx, ny = stroke_normal(points)
    radius = diameter / 2.0 + 2.0
    left = min(x for x, y in points) - radius
    right = max(x for x, y in points) + radius
    top = min(y for x, y in points) - radius
    bottom = max(y for x, y in points) + radius
    if left < 0 or top < 0 or right >= width or bottom >= height:
        raise ValueError("Zmniejsz pedzel lub odsun linie od krawedzi warstwy.")

    def pixel(x, y):
        i = (int(x) + int(y) * width) * 4
        return pixels[i:i + 4]

    ring = []
    for i in range(12):
        t = i / 11
        ring.extend(((left + (right - left) * t, top),
                     (left + (right - left) * t, bottom),
                     (left, top + (bottom - top) * t),
                     (right, top + (bottom - top) * t)))
    target = [pixel(x, y) for x, y in ring]
    if any(p[3] < 250 for p in target):
        raise ValueError("Wybierz obszar bez przezroczystosci.")
    # Sparse interior checks are for alpha only, never for scoring the defect.
    centers = [points[int(i * (len(points) - 1) / 23)] for i in range(24)]
    sources = {}
    for side in (1, -1):
        best = None
        for scale in (1.3, 2.0, 3.0, 4.5, 6.0):
            distance = max(4, diameter) * scale
            dx, dy = side * nx * distance, side * ny * distance
            if not source_is_safe(points, diameter, width, height, (dx, dy)):
                continue
            shifted_ring = [(x + dx, y + dy) for x, y in ring]
            if any(x < 0 or y < 0 or x >= width or y >= height for x, y in shifted_ring):
                continue
            donor = [pixel(x, y) for x, y in shifted_ring]
            interior = [pixel(x + dx + sx * diameter / 2.0,
                              y + dy + sy * diameter / 2.0)
                        for x, y in centers
                        for sx, sy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))]
            if any(p[3] < 250 for p in donor + interior):
                continue
            shifts = [sum(a[c] - b[c] for a, b in zip(target, donor)) / len(ring)
                      for c in range(3)]
            error = sum((a[c] - b[c] - shifts[c]) ** 2
                        for a, b in zip(target, donor) for c in range(3)) / (3 * len(ring))
            score = error + 0.2 * sum(v * v for v in shifts) / 3 + 0.1 * scale
            candidate = {"offset": (dx, dy), "score": score}
            if best is None or score < best["score"]:
                best = candidate
        if best is not None:
            sources[side] = best
    if not sources:
        raise ValueError("Brak bezpiecznej probki po bokach. Zmniejsz pedzel lub podziel linie.")
    return sources
