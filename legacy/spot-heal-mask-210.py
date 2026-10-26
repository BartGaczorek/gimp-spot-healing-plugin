#!/usr/bin/env python2
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


# -*- coding: utf-8 -*-
# Appended to mask_core.py by tools/build_plugin.py.
import traceback
import gtk
import gimpui
from gimpfu import gimp, pdb, register, main, PF_IMAGE, PF_DRAWABLE

MAX_HISTORY = 128 * 1024 * 1024


def point_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class MaskSession(object):
    def __init__(self, image, layer):
        self.image, self.layer = image, layer
        self.width, self.height = layer.width, layer.height
        self.view = Viewport(self.width, self.height)
        self.points, self.history = [], []
        self.pending_points = []
        self.busy = False
        self.history_bytes = 0
        self.pan = self.cursor = None
        self.initialized = False
        self.diameter = 16.0
        self.refresh()
        self.dialog = gtk.Dialog("Spot Heal - maska jednego ruchu", None, gtk.DIALOG_MODAL,
                                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_APPLY, gtk.RESPONSE_OK))
        screen = self.dialog.get_screen()
        self.dialog.set_default_size(min(1040, int(screen.get_width() * 0.85)),
                                     min(740, int(screen.get_height() * 0.85)))
        toolbar = gtk.HBox(False, 8)
        self.toolbar = toolbar
        toolbar.set_border_width(8)
        self.dialog.vbox.pack_start(toolbar, False, False)
        toolbar.pack_start(gtk.Label("Srednica (px zdjecia):"), False, False)
        self.size = gtk.SpinButton(gtk.Adjustment(16, 1, 128, 1, 10, 0), 1, 0)
        self.size.connect("value-changed", self.change_size)
        toolbar.pack_start(self.size, False, False)
        for label, callback in (("Dopasuj", self.fit), ("100%", self.actual_size), ("Cofnij", self.undo)):
            button = gtk.Button(label)
            button.connect("clicked", callback)
            toolbar.pack_start(button, False, False)
        self.alternative_button = gtk.Button("Inna probka")
        self.alternative_button.connect("clicked", self.alternative)
        self.alternative_button.set_sensitive(False)
        toolbar.pack_start(self.alternative_button, False, False)
        self.zoom_label = gtk.Label()
        toolbar.pack_end(self.zoom_label, False, False)
        self.area = gtk.DrawingArea()
        self.area.set_size_request(240, 180)
        self.area.set_flags(gtk.CAN_FOCUS)
        self.area.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK |
                             gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.SCROLL_MASK |
                             gtk.gdk.LEAVE_NOTIFY_MASK)
        for event, callback in (("expose-event", self.draw), ("size-allocate", self.allocate),
                                ("button-press-event", self.press), ("button-release-event", self.release),
                                ("motion-notify-event", self.motion), ("scroll-event", self.scroll),
                                ("leave-notify-event", self.leave)):
            self.area.connect(event, callback)
        self.dialog.connect("key-press-event", self.key)
        self.dialog.connect("delete-event", lambda *args: self.busy)
        self.dialog.vbox.pack_start(self.area, True, True)
        self.status = gtk.Label("Maluj LPM. Pusc LPM, aby naprawic caly obszar. Kolko: gora/dol | Ctrl+kolko: gora/dol | Ctrl+kolko: zoom | Ctrl+Alt+kolko: rozmiar | Ctrl+Alt+kolko: rozmiar | SPM: przesuwanie")
        self.status.set_alignment(0, 0.5)
        self.status.set_padding(8, 8)
        self.status.set_line_wrap(True)
        self.dialog.vbox.pack_start(self.status, False, False)

    def read_patch(self, bounds):
        x, y, w, h = bounds
        region = self.layer.get_pixel_rgn(x, y, w, h, False, False)
        return region[x:x + w, y:y + h]

    def refresh(self):
        self.raw = self.read_patch((0, 0, self.width, self.height))
        channels = self.layer.bpp
        if channels not in (3, 4):
            raise ValueError("Warstwa musi byc RGB lub RGBA.")
        self.pixels = bytearray(self.width * self.height * 4)
        raw = bytearray(self.raw)
        for c in range(3):
            self.pixels[c::4] = raw[c::channels]
        self.pixels[3::4] = raw[3::4] if channels == 4 else bytearray([255]) * (self.width * self.height)
        self.pixbuf = gtk.gdk.pixbuf_new_from_data(self.raw, gtk.gdk.COLORSPACE_RGB,
                       channels == 4, 8, self.width, self.height, self.width * channels)

    def change_size(self, widget):
        self.diameter = widget.get_value()
        self.area.queue_draw()

    def allocate(self, widget, allocation):
        if not self.initialized:
            self.fit()
            self.initialized = True

    def fit(self, *unused):
        self.view.fit(self.area.allocation.width, self.area.allocation.height)
        self.area.queue_draw()

    def actual_size(self, *unused):
        w, h = self.area.allocation.width, self.area.allocation.height
        self.view.zoom_at(1 / self.view.zoom, w / 2.0, h / 2.0)
        self.area.queue_draw()

    def draw(self, widget, event):
        cr = widget.window.cairo_create()
        cr.set_source_rgb(0.16, 0.16, 0.16)
        cr.paint()
        cr.save()
        cr.translate(self.view.x, self.view.y)
        cr.scale(self.view.zoom, self.view.zoom)
        cr.set_source_pixbuf(self.pixbuf, 0, 0)
        cr.paint()
        cr.restore()
        visible_points = self.points or self.pending_points
        if visible_points:
            cr.set_source_rgba(0.2, 0.8, 1, 0.45)
            cr.set_line_width(max(2, self.diameter * self.view.zoom))
            cr.set_line_cap(1)
            cr.set_line_join(1)
            if len(visible_points) == 1:
                x, y = visible_points[0]
                cr.arc(self.view.x + x * self.view.zoom, self.view.y + y * self.view.zoom,
                       self.diameter * self.view.zoom / 2, 0, 2 * math.pi)
                cr.fill()
            for i, (x, y) in enumerate(visible_points):
                x, y = self.view.x + x * self.view.zoom, self.view.y + y * self.view.zoom
                if i == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()
        if self.cursor:
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1)
            cr.arc(self.cursor[0], self.cursor[1], max(1, self.diameter * self.view.zoom / 2), 0, 2 * math.pi)
            cr.stroke()
        self.zoom_label.set_text("%.0f%%" % (self.view.zoom * 100))
        return False

    def press(self, widget, event):
        if self.busy:
            return True
        widget.grab_focus()
        if event.button == 2 and not self.points:
            self.pan = event.x, event.y
        elif event.button == 1:
            point = self.view.image_point(event.x, event.y)
            if 0 <= point[0] < self.width and 0 <= point[1] < self.height:
                self.points = [point]
        return True

    def motion(self, widget, event):
        if self.busy:
            return True
        self.cursor = event.x, event.y
        if self.pan:
            self.view.x += event.x - self.pan[0]
            self.view.y += event.y - self.pan[1]
            self.pan = event.x, event.y
        elif self.points:
            point = self.view.image_point(event.x, event.y)
            if point_distance(point, self.points[-1]) >= max(1, self.diameter / 5):
                self.points.append(point)
        widget.queue_draw()
        return True

    def release(self, widget, event):
        if self.busy:
            return True
        if event.button == 2:
            self.pan = None
        elif event.button == 1 and self.points:
            points, self.points = self.points, []
            end = self.view.image_point(event.x, event.y)
            if point_distance(end, points[-1]) >= 1:
                points.append(end)
            self.pending_points = points
            self.repair(points)
            self.pending_points = []
            self.area.queue_draw()
        return True

    def scroll(self, widget, event):
        if self.busy or self.points:
            return True
        if event.direction not in (gtk.gdk.SCROLL_UP, gtk.gdk.SCROLL_DOWN):
            return True
        step = 1 if event.direction == gtk.gdk.SCROLL_UP else -1
        control = bool(event.state & gtk.gdk.CONTROL_MASK)
        alt = bool(event.state & gtk.gdk.MOD1_MASK)
        if control and alt:
            # Updating the spin button also updates diameter and the brush outline.
            self.size.set_value(max(1, min(128, self.diameter + step)))
        elif control:
            factor = 1.2 if step > 0 else 1 / 1.2
            self.view.zoom_at(factor, event.x, event.y)
        else:
            self.view.y += step * 50
        widget.queue_draw()
        return True

    def leave(self, widget, event):
        self.cursor = None
        widget.queue_draw()

    def key(self, widget, event):
        if self.busy:
            return True
        if event.state & gtk.gdk.CONTROL_MASK and gtk.gdk.keyval_name(event.keyval).lower() == "z":
            self.undo()
            return True
        return False

    def restore(self, bounds, snapshot):
        x, y, w, h = bounds
        region = self.layer.get_pixel_rgn(x, y, w, h, True, False)
        region[x:x + w, y:y + h] = snapshot
        self.layer.flush()
        self.layer.update(x, y, w, h)


    def write_patch(self, bounds, raw):
        self.restore(bounds, raw)

    def raw_patch(self, rgba):
        if self.layer.bpp == 4:
            return rgba.decode("latin1").encode("latin1")
        rgb = bytearray(len(rgba) // 4 * 3)
        for c in range(3):
            rgb[c::3] = rgba[c::4]
        return rgb.decode("latin1").encode("latin1")

    def controls(self):
        enabled = bool(self.history and len(self.history[-1]["sources"]) > 1 and not self.busy)
        self.alternative_button.set_sensitive(enabled)

    def set_busy(self, busy):
        self.busy = busy
        self.toolbar.set_sensitive(not busy)
        self.area.set_sensitive(not busy)
        self.dialog.set_response_sensitive(gtk.RESPONSE_OK, not busy)
        self.dialog.set_response_sensitive(gtk.RESPONSE_CANCEL, not busy)
        self.controls()

    def progress(self, fraction):
        self.status.set_text("Naprawianie calego obszaru... %d%%" % int(fraction * 100))
        self.area.queue_draw()
        while gtk.events_pending():
            gtk.main_iteration(False)

    def result_status(self, record):
        return "Naprawiono obszar %d px. Probka %d/%d. Ctrl+Z: cofnij caly ruch." % (
            len(record["mask"]), record["index"] + 1, len(record["sources"]))

    def render(self, record, index):
        offset = record["sources"][index]["offset"]
        bounds, rgba, stats = poisson_patch(self.pixels, self.width, self.height,
                                            record["mask"], offset, self.progress)
        if bounds != record["bounds"]:
            raise RuntimeError("Niezgodny obszar naprawy.")
        raw = self.raw_patch(rgba)
        self.write_patch(bounds, raw)
        self.refresh()
        return raw, stats

    def repair(self, points):
        if self.busy:
            return
        before = None
        self.set_busy(True)
        try:
            mask = rasterize_stroke(points, self.diameter, self.width, self.height)
            bounds = mask_bounds(mask)
            if 2 * bounds[2] * bounds[3] * self.layer.bpp > MAX_HISTORY:
                raise ValueError("Zbyt rozlegly obszar do cofania. Skroc ruch.")
            sources = choose_sources(self.pixels, self.width, self.height, mask,
                                     self.diameter, self.progress)
            before = self.read_patch(bounds)
            record = {"mask": mask, "bounds": bounds, "before": before,
                      "sources": sources, "index": 0}
            after, stats = self.render(record, 0)
            record["after"], record["stats"] = after, stats
            self.history.append(record)
            self.history_bytes += len(before) + len(after)
            while self.history_bytes > MAX_HISTORY and len(self.history) > 1:
                old = self.history.pop(0)
                self.history_bytes -= len(old["before"]) + len(old["after"])
            self.status.set_text(self.result_status(record))
        except Exception as error:
            if before is not None:
                self.write_patch(bounds, before)
                self.refresh()
            self.status.set_text(str(error))
            traceback.print_exc()
        finally:
            self.set_busy(False)
        self.area.queue_draw()
        gimp.displays_flush()

    def alternative(self, *unused):
        if self.busy or self.points or not self.history:
            return
        record = self.history[-1]
        if len(record["sources"]) < 2:
            return
        previous = record["after"]
        index = (record["index"] + 1) % len(record["sources"])
        self.set_busy(True)
        try:
            # The donor and Dirichlet boundary are outside the mask, so neither
            # depends on the preceding solution. Re-solving is equivalent to
            # undoing this mask and applying the new donor, without a flicker.
            after, stats = self.render(record, index)
            self.history_bytes += len(after) - len(previous)
            record["after"], record["stats"], record["index"] = after, stats, index
            self.status.set_text(self.result_status(record))
        except Exception as error:
            self.write_patch(record["bounds"], previous)
            self.refresh()
            self.status.set_text("Nie zmieniono probki: " + str(error))
            traceback.print_exc()
        finally:
            self.set_busy(False)
        self.area.queue_draw()
        gimp.displays_flush()

    def undo(self, *unused):
        if self.busy or self.points or not self.history:
            return
        record = self.history[-1]
        try:
            self.write_patch(record["bounds"], record["before"])
            self.refresh()
        except Exception as error:
            self.write_patch(record["bounds"], record["after"])
            self.refresh()
            self.status.set_text("Nie cofnieto naprawy: " + str(error))
            traceback.print_exc()
            return
        self.history.pop()
        self.history_bytes -= len(record["before"]) + len(record["after"])
        self.controls()
        self.status.set_text("Cofnieto caly obszar. Pozostalo: %d" % len(self.history))
        self.area.queue_draw()
        gimp.displays_flush()

    def run(self):
        self.dialog.show_all()
        try:
            return self.dialog.run() == gtk.RESPONSE_OK
        finally:
            self.dialog.destroy()


def spot_heal_mask_210(image, drawable):
    layer = None
    started = keep = False
    try:
        if not pdb.gimp_item_is_layer(drawable) or pdb.gimp_item_is_group(drawable):
            raise ValueError("Wybierz zwykla warstwe RGB.")
        if not pdb.gimp_drawable_is_rgb(drawable) or drawable.mask is not None:
            raise ValueError("Wybierz warstwe RGB bez maski.")
        if pdb.gimp_image_get_precision(image) != 150:
            raise ValueError("Wymagany obraz RGB 8-bit gamma sRGB. W razie konwersji pracuj na kopii dokumentu.")
        if drawable.offsets != (0, 0):
            raise ValueError("Warstwa musi miec przesuniecie 0, 0.")
        if not pdb.gimp_selection_is_empty(image):
            raise ValueError("Usun zaznaczenie: Zaznaczenie > Nic.")
        if drawable.width * drawable.height > 32000000:
            raise ValueError("Prototyp obsluguje warstwy do 32 megapikseli.")
        gimpui.gimp_ui_init()
        pdb.gimp_image_undo_group_start(image)
        started = True
        parent = pdb.gimp_item_get_parent(drawable)
        position = pdb.gimp_image_get_item_position(image, drawable)
        layer = drawable.copy()
        pdb.gimp_image_insert_layer(image, layer, parent, position)
        pdb.gimp_item_set_name(layer, "Spot Heal - maska")
        pdb.gimp_item_set_lock_content(layer, False)
        layer.lock_alpha = False
        keep = MaskSession(image, layer).run()
    except Exception as error:
        traceback.print_exc()
        pdb.gimp_message(str(error))
    finally:
        if layer is not None and not keep:
            pdb.gimp_image_remove_layer(image, layer)
            pdb.gimp_image_set_active_layer(image, drawable)
        if started:
            pdb.gimp_image_undo_group_end(image)
        gimp.displays_flush()


register("python-fu-spot-heal-mask-210", "Retusz calej maski jednego ruchu",
         "Maluj LPM, pusc aby naprawic obszar jedna probka z laczeniem Poissona.",
         "BartGaczorek and contributors", "BartGaczorek and contributors", "2026",
         "Spot Heal - maska...", "RGB*",
         [(PF_IMAGE, "image", "Image", None), (PF_DRAWABLE, "drawable", "Layer", None)],
         [], spot_heal_mask_210, menu="<Image>/Filters/Enhance")
main()

