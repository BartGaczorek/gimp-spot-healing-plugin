# -*- coding: utf-8 -*-
"""Whole-mask retouching, Python 2.7 / 3, without third-party dependencies."""
from __future__ import division
import math

MAX_PIXELS = 25000
MAX_ROI = 1000000
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Viewport(object):
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.zoom, self.x, self.y = 1.0, 0.0, 0.0

    def fit(self, width, height):
        self.zoom = min(1.0, 0.96 * min(width / self.width, height / self.height))
        self.x = (width - self.width * self.zoom) / 2
        self.y = (height - self.height * self.zoom) / 2

    def image_point(self, x, y):
        return (x - self.x) / self.zoom, (y - self.y) / self.zoom

    def zoom_at(self, factor, x, y):
        ix, iy = self.image_point(x, y)
        self.zoom = max(0.01, min(4.0, self.zoom * factor))
        self.x, self.y = x - ix * self.zoom, y - iy * self.zoom


def mask_bounds(mask, padding=0):
    left = min(x for x, y in mask) - padding
    top = min(y for x, y in mask) - padding
    right = max(x for x, y in mask) + padding + 1
    bottom = max(y for x, y in mask) + padding + 1
    return left, top, right - left, bottom - top


def rasterize_stroke(points, diameter, width, height):
    """Rasterize the union of swept circular brushes, including between events."""
    if not points or diameter < 1:
        raise ValueError("Brak ruchu lub nieprawidlowa srednica.")
    radius = diameter / 2.0
    left = max(0, int(math.floor(min(x for x, y in points) - radius)))
    top = max(0, int(math.floor(min(y for x, y in points) - radius)))
    right = min(width - 1, int(math.ceil(max(x for x, y in points) + radius)))
    bottom = min(height - 1, int(math.ceil(max(y for x, y in points) + radius)))
    if (right - left + 1) * (bottom - top + 1) > MAX_ROI:
        raise ValueError("Zbyt rozlegly ruch. Podziel go na mniejsze obszary.")
    mask = set()
    segments = list(zip(points, points[1:])) or [(points[0], points[0])]
    for a, b in segments:
        vx, vy = b[0] - a[0], b[1] - a[1]
        length2 = vx * vx + vy * vy
        x0 = max(left, int(math.floor(min(a[0], b[0]) - radius)))
        x1 = min(right, int(math.ceil(max(a[0], b[0]) + radius)))
        y0 = max(top, int(math.floor(min(a[1], b[1]) - radius)))
        y1 = min(bottom, int(math.ceil(max(a[1], b[1]) + radius)))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / length2)) if length2 else 0.0
                if (x - a[0] - t * vx) ** 2 + (y - a[1] - t * vy) ** 2 <= radius * radius:
                    if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                        raise ValueError("Odsun pedzel od brzegu zdjecia o co najmniej 1 piksel.")
                    mask.add((x, y))
                    if len(mask) > MAX_PIXELS:
                        raise ValueError("Maska przekracza 25000 pikseli. Zmniejsz pedzel lub skroc ruch.")
    if not mask:
        x, y = (int(math.floor(v + 0.5)) for v in points[0])
        if 0 < x < width - 1 and 0 < y < height - 1:
            mask.add((x, y))
        else:
            raise ValueError("Ruch jest poza zdjeciem.")
    return frozenset(mask)


def dilate_mask(mask, margin=2):
    return set((x + dx, y + dy) for x, y in mask
               for dx in range(-margin, margin + 1)
               for dy in range(-margin, margin + 1))


def source_is_safe(mask, offset, width, height, guarded=None):
    dx, dy = offset
    guarded = dilate_mask(mask) if guarded is None else guarded
    for x, y in mask:
        sx, sy = x + dx, y + dy
        if sx < 1 or sy < 1 or sx >= width - 1 or sy >= height - 1 or (sx, sy) in guarded:
            return False
    return True


def boundary_of(mask):
    return set((x + dx, y + dy) for x, y in mask for dx, dy in NEIGHBORS
               if (x + dx, y + dy) not in mask)


def choose_sources(pixels, width, height, mask, diameter, progress=None):
    """Rank whole-mask translations using true exterior-boundary samples."""
    guarded = dilate_mask(mask)
    boundary = sorted(boundary_of(mask))
    samples = [boundary[int(i * (len(boundary) - 1) / min(95, len(boundary) - 1))]
               for i in range(min(96, len(boundary)))] if len(boundary) > 1 else boundary

    def pixel(point):
        i = (point[0] + point[1] * width) * 4
        return pixels[i:i + 4]

    if any(pixel(p)[3] < 250 for p in set(mask) | set(boundary)):
        raise ValueError("Obszar i jego granica musza byc nieprzezroczyste.")
    target = [pixel(p) for p in samples]
    count = len(mask)
    mx = sum(x for x, y in mask) / count
    my = sum(y for x, y in mask) / count
    xx = sum((x - mx) ** 2 for x, y in mask) / count
    yy = sum((y - my) ** 2 for x, y in mask) / count
    xy = sum((x - mx) * (y - my) for x, y in mask) / count
    principal = 0.5 * math.atan2(2 * xy, xx - yy)
    spread = math.sqrt((xx - yy) ** 2 + 4 * xy * xy)
    elongated = (xx + yy + spread) > 3 * max(0.01, xx + yy - spread)
    normal = principal + math.pi / 2
    angles = [normal, normal + math.pi] if elongated else []
    angles += [i * math.pi / 8 for i in range(16)]
    _, _, bw, bh = mask_bounds(mask)
    limit = min(math.hypot(width, height), 3 * max(bw, bh, diameter) + 8)
    seen, candidates = set(), []
    for index, angle in enumerate(angles):
        distance = max(3.0, diameter * 0.75)
        accepted = 0
        for attempt in range(45):
            if distance > limit or accepted >= 3:
                break
            offset = int(round(math.cos(angle) * distance)), int(round(math.sin(angle) * distance))
            distance = max(distance + 2, distance * 1.25)
            if offset in seen:
                continue
            seen.add(offset)
            if not source_is_safe(mask, offset, width, height, guarded):
                continue
            dx, dy = offset
            source_boundary = [(x + dx, y + dy) for x, y in boundary]
            if any(pixel((x + dx, y + dy))[3] < 250 for x, y in mask):
                continue
            if any(pixel(p)[3] < 250 for p in source_boundary):
                continue
            donor = [pixel((x + dx, y + dy)) for x, y in samples]
            shifts = [sum(a[c] - b[c] for a, b in zip(target, donor)) / len(samples)
                      for c in range(3)]
            error = sum((a[c] - b[c] - shifts[c]) ** 2
                        for a, b in zip(target, donor) for c in range(3)) / (3 * len(samples))
            angular = 2 * abs(math.cos(angle - principal)) if elongated else 0
            score = error + 0.2 * sum(v * v for v in shifts) / 3 + angular + 0.15 * math.hypot(dx, dy) / max(4, diameter)
            candidates.append({"offset": offset, "score": score})
            accepted += 1
        if progress:
            progress(0.35 * (index + 1) / len(angles))
    if not candidates:
        raise ValueError("Brak bezpiecznej probki dla calej maski. Zmniejsz obszar.")
    return sorted(candidates, key=lambda candidate: candidate["score"])


LINEAR = tuple((v / 255.0) / 12.92 if v <= 10 else ((v / 255.0 + 0.055) / 1.055) ** 2.4
               for v in range(256))


def encode(value):
    value = min(1.0, max(0.0, value))
    srgb = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return int(round(255 * srgb))


def poisson_patch(pixels, width, height, mask, offset, progress=None, max_iterations=400):
    """Solve one masked Dirichlet problem, preserving donor gradients.

    Solve for a harmonic correction to the translated donor in linear RGB.
    The correction's boundary values are target minus donor. This is one
    sparse system over all mask pixels, not a sequence of Healing strokes.
    """
    if not source_is_safe(mask, offset, width, height):
        raise ValueError("Probka przecina maske lub wychodzi poza zdjecie.")
    nodes = sorted(mask)
    indices = dict((point, i) for i, point in enumerate(nodes))
    neighbors, rhs, donor_values = [], [], []
    dx, dy = offset
    for x, y in nodes:
        adjacent, b = [], [0.0, 0.0, 0.0]
        si = ((y + dy) * width + x + dx) * 4
        donor_values.extend(LINEAR[pixels[si + c]] for c in range(3))
        for vx, vy in NEIGHBORS:
            q = x + vx, y + vy
            j = indices.get(q)
            if j is not None:
                adjacent.append(j)
            else:
                ti = (q[1] * width + q[0]) * 4
                sj = ((q[1] + dy) * width + q[0] + dx) * 4
                for c in range(3):
                    b[c] += LINEAR[pixels[ti + c]] - LINEAR[pixels[sj + c]]
        neighbors.append(adjacent)
        rhs.extend(b)

    def multiply(vector):
        result = [0.0] * len(vector)
        for i, adjacent in enumerate(neighbors):
            k = i * 3
            for c in range(3):
                result[k + c] = 4 * vector[k + c] - sum(vector[j * 3 + c] for j in adjacent)
        return result

    solution = [0.0] * len(rhs)
    residual = list(rhs)
    direction = list(rhs)
    norm = sum(v * v for v in residual)
    tolerance = len(rhs) * 1e-10
    iterations = 0
    for iteration in range(max_iterations):
        if norm <= tolerance:
            break
        product = multiply(direction)
        denominator = sum(a * b for a, b in zip(direction, product))
        if denominator <= 0:
            raise ValueError("Nie udalo sie rozwiazac laczenia probki.")
        alpha = norm / denominator
        solution = [a + alpha * b for a, b in zip(solution, direction)]
        residual = [a - alpha * b for a, b in zip(residual, product)]
        next_norm = sum(v * v for v in residual)
        beta = next_norm / norm
        direction = [a + beta * b for a, b in zip(residual, direction)]
        norm = next_norm
        iterations = iteration + 1
        if progress and iteration % 8 == 0:
            progress(0.35 + 0.6 * (iteration + 1) / max_iterations)
    if norm > tolerance:
        raise ValueError("Laczenie nie osiagnelo wymaganej dokladnosci. Zmniejsz obszar.")
    bounds = mask_bounds(mask)
    x0, y0, bw, bh = bounds
    patch = bytearray()
    for y in range(y0, y0 + bh):
        start = (y * width + x0) * 4
        patch.extend(pixels[start:start + bw * 4])
    clipped = 0
    for i, (x, y) in enumerate(nodes):
        k, j = i * 3, ((y - y0) * bw + x - x0) * 4
        for c in range(3):
            value = donor_values[k + c] + solution[k + c]
            clipped += int(value < 0 or value > 1)
            patch[j + c] = encode(value)
    if progress:
        progress(1.0)
    return bounds, patch, {"iterations": iterations, "residual": math.sqrt(norm / len(rhs)), "clipped": clipped}
