#!/usr/bin/env python2
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


# -*- coding: utf-8 -*-
# This file is appended to the shared core by tools/build_legacy.py.
import traceback
import gtk
import gimpui
from gimpfu import gimp, pdb, register, main, PF_IMAGE, PF_DRAWABLE, NORMAL_MODE

MAX_HISTORY = 128 * 1024 * 1024


def point_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class LegacySession(object):
    def __init__(self, image, layer):
        self.image, self.layer = image, layer
        self.width, self.height = layer.width, layer.height
        self.view = Viewport(self.width, self.height)
        self.points, self.history = [], []
        self.history_bytes = 0
        self.pan = self.cursor = None
        self.initialized = False
        self.diameter = 16.0
        self.refresh()
        self.dialog = gtk.Dialog("Spot Heal 2.10 - prototyp", None, gtk.DIALOG_MODAL,
                                (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                 gtk.STOCK_APPLY, gtk.RESPONSE_OK))
        screen = self.dialog.get_screen()
        self.dialog.set_default_size(min(1040, int(screen.get_width() * 0.85)),
                                     min(740, int(screen.get_height() * 0.85)))
        toolbar = gtk.HBox(False, 8)
        toolbar.set_border_width(8)
        self.dialog.vbox.pack_start(toolbar, False, False)
        toolbar.pack_start(gtk.Label("Srednica (px zdjecia):"), False, False)
        self.size = gtk.SpinButton(gtk.Adjustment(16, 1, 256, 1, 10, 0), 1, 0)
        self.size.connect("value-changed", self.change_size)
        toolbar.pack_start(self.size, False, False)
        for label, callback in (("Dopasuj", self.fit), ("100%", self.actual_size), ("Cofnij", self.undo)):
            button = gtk.Button(label)
            button.connect("clicked", callback)
            toolbar.pack_start(button, False, False)
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
        self.dialog.vbox.pack_start(self.area, True, True)
        self.status = gtk.Label("LPM: naprawa / rysa | kolko: zoom | SPM: przesuwanie | Ctrl+Z: cofnij")
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
        if self.points:
            cr.set_source_rgba(0.2, 0.8, 1, 0.45)
            cr.set_line_width(max(2, self.diameter * self.view.zoom))
            cr.set_line_cap(1)
            for i, (x, y) in enumerate(self.points):
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
        widget.grab_focus()
        if event.button == 2:
            self.pan = event.x, event.y
        elif event.button == 1:
            point = self.view.image_point(event.x, event.y)
            if 0 <= point[0] < self.width and 0 <= point[1] < self.height:
                self.points = [point]
        return True

    def motion(self, widget, event):
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
        if event.button == 2:
            self.pan = None
        elif event.button == 1 and self.points:
            points, self.points = self.points, []
            end = self.view.image_point(event.x, event.y)
            if point_distance(end, points[-1]) >= 1:
                points.append(end)
            self.repair(points)
        return True

    def scroll(self, widget, event):
        if not self.points:
            factor = 1.2 if event.direction == gtk.gdk.SCROLL_UP else 1 / 1.2
            self.view.zoom_at(factor, event.x, event.y)
            widget.queue_draw()
        return True

    def leave(self, widget, event):
        self.cursor = None
        widget.queue_draw()

    def key(self, widget, event):
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

    def repair(self, points):
        snapshot = None
        try:
            dabs = resample_stroke(points, max(1.0, self.diameter * 0.2))
            dx, dy = choose_source(self.pixels, self.width, self.height, points, self.diameter)
            bounds = stroke_bounds(points, self.diameter, self.width, self.height)
            if bounds[2] * bounds[3] * self.layer.bpp > MAX_HISTORY:
                raise ValueError("Ruch jest zbyt rozlegly. Podziel go na krotsze odcinki.")
            snapshot = self.read_patch(bounds)
            pdb.gimp_context_push()
            try:
                pdb.gimp_context_set_brush("2. Hardness 100")
                pdb.gimp_context_set_brush_size(self.diameter)
                pdb.gimp_context_set_brush_aspect_ratio(0)
                pdb.gimp_context_set_brush_angle(0)
                pdb.gimp_context_set_brush_hardness(1.0)
                pdb.gimp_context_set_brush_force(1.0)
                pdb.gimp_context_set_brush_spacing(10)
                pdb.gimp_context_set_dynamics("Dynamics Off")
                pdb.gimp_context_set_opacity(100)
                pdb.gimp_context_set_paint_mode(NORMAL_MODE)
                pdb.gimp_context_set_sample_merged(False)
                # Each dab explicitly supplies its own donor. This avoids
                # relying on multi-point interpolation in the legacy PDB.
                for x, y in dabs:
                    pdb.gimp_heal(self.layer, self.layer, x + dx, y + dy,
                                  2, [x, y])
            finally:
                pdb.gimp_context_pop()
            self.refresh()
            self.history.append((bounds, snapshot))
            self.history_bytes += len(snapshot)
            while self.history_bytes > MAX_HISTORY and len(self.history) > 1:
                self.history_bytes -= len(self.history.pop(0)[1])
            self.status.set_text("Naprawiono. Dostepne cofniecia: %d" % len(self.history))
        except Exception as error:
            if snapshot is not None:
                self.restore(bounds, snapshot)
                self.refresh()
            self.status.set_text(str(error))
            traceback.print_exc()
        self.area.queue_draw()
        gimp.displays_flush()

    def undo(self, *unused):
        if self.points or not self.history:
            return
        bounds, snapshot = self.history.pop()
        self.history_bytes -= len(snapshot)
        self.restore(bounds, snapshot)
        self.refresh()
        self.status.set_text("Cofnieto. Dostepne cofniecia: %d" % len(self.history))
        self.area.queue_draw()
        gimp.displays_flush()

    def run(self):
        self.dialog.show_all()
        try:
            return self.dialog.run() == gtk.RESPONSE_OK
        finally:
            self.dialog.destroy()


def spot_heal_210(image, drawable):
    layer = None
    started = keep = False
    try:
        if not pdb.gimp_item_is_layer(drawable) or pdb.gimp_item_is_group(drawable):
            raise ValueError("Wybierz zwykla warstwe RGB.")
        if not pdb.gimp_drawable_is_rgb(drawable) or drawable.mask is not None:
            raise ValueError("Wybierz warstwe RGB bez maski.")
        # Legacy PixelRgn always exposes gamma-encoded 8-bit pixels. Reject
        # higher precision and linear images instead of quantizing undo data.
        if pdb.gimp_image_get_precision(image) != 150:
            raise ValueError("Wersja 2.10 wymaga: Obraz > Precyzja > 8-bitowa calkowita, gamma perceptualna (sRGB). Pracuj na kopii dokumentu.")
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
        pdb.gimp_item_set_name(layer, "Spot Heal - retusz")
        pdb.gimp_item_set_lock_content(layer, False)
        layer.lock_alpha = False
        keep = LegacySession(image, layer).run()
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


register("python-fu-spot-heal-210", "Retusz ze zrodlem dobieranym automatycznie",
         "Eksperymentalny retusz jednym kliknieciem, GIMP 2.10 / Python 2.7.",
         "BartGaczorek and contributors", "BartGaczorek and contributors", "2026",
         "Spot Heal 2.10...", "RGB*",
         [(PF_IMAGE, "image", "Image", None), (PF_DRAWABLE, "drawable", "Layer", None)],
         [], spot_heal_210, menu="<Image>/Filters/Enhance")
main()
