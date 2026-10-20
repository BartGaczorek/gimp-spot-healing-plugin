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
        self.dialog = gtk.Dialog("Spot Heal 2.10 - probka prostopadla", None, gtk.DIALOG_MODAL,
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
        self.side_button = gtk.Button("Zmien strone")
        self.side_button.connect("clicked", self.change_side)
        self.side_button.set_sensitive(False)
        self.side_button.set_tooltip_text("Ponow ostatnia linie z probka po przeciwnej stronie.")
        toolbar.pack_start(self.side_button, False, False)
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
                self.update_side_control()
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

    def apply_dabs(self, dabs, offset, diameter):
        dx, dy = offset
        pdb.gimp_context_push()
        try:
            pdb.gimp_context_set_brush("2. Hardness 100")
            pdb.gimp_context_set_brush_size(diameter)
            pdb.gimp_context_set_brush_aspect_ratio(0)
            pdb.gimp_context_set_brush_angle(0)
            pdb.gimp_context_set_brush_hardness(1.0)
            pdb.gimp_context_set_brush_force(1.0)
            pdb.gimp_context_set_brush_spacing(10)
            pdb.gimp_context_set_dynamics("Dynamics Off")
            pdb.gimp_context_set_opacity(100)
            pdb.gimp_context_set_paint_mode(NORMAL_MODE)
            pdb.gimp_context_set_sample_merged(False)
            for x, y in dabs:
                pdb.gimp_heal(self.layer, self.layer, x + dx, y + dy, 2, [x, y])
        finally:
            pdb.gimp_context_pop()

    def update_side_control(self):
        enabled = False
        if self.history and not self.points:
            record = self.history[-1]
            enabled = record["side"] is not None and -record["side"] in record["sources"]
        self.side_button.set_sensitive(enabled)

    def record_status(self, record):
        if record["side"] is None:
            return "Naprawiono punkt. Dostepne cofniecia: %d" % len(self.history)
        dx, dy = record["sources"][record["side"]]["offset"]
        message = "Linia: strona %s, odsuniecie %.1f px. Cofniecia: %d" % (
            "A" if record["side"] == 1 else "B", math.hypot(dx, dy), len(self.history))
        if -record["side"] not in record["sources"]:
            message += " | Brak bezpiecznej probki po drugiej stronie."
        return message

    def repair(self, points):
        snapshot = None
        try:
            diameter = self.diameter
            dabs = resample_stroke(points, max(1.0, diameter * 0.2))
            sources, side = {}, None
            if len(dabs) > 1:
                sources = choose_perpendicular_sources(self.pixels, self.width, self.height,
                                                       dabs, diameter)
                side = min(sources, key=lambda key: sources[key]["score"])
                offset = sources[side]["offset"]
            else:
                offset = choose_source(self.pixels, self.width, self.height, points, diameter)
            bounds = stroke_bounds(points, diameter, self.width, self.height)
            # Keep pre- and post-images so a failed side change is atomic.
            if 2 * bounds[2] * bounds[3] * self.layer.bpp > MAX_HISTORY:
                raise ValueError("Ruch jest zbyt rozlegly. Podziel go na krotsze odcinki.")
            snapshot = self.read_patch(bounds)
            self.apply_dabs(dabs, offset, diameter)
            after = self.read_patch(bounds)
            self.refresh()
            record = {"bounds": bounds, "before": snapshot, "after": after,
                      "dabs": dabs, "diameter": diameter, "sources": sources, "side": side}
            self.history.append(record)
            self.history_bytes += len(snapshot) + len(after)
            while self.history_bytes > MAX_HISTORY and len(self.history) > 1:
                old = self.history.pop(0)
                self.history_bytes -= len(old["before"]) + len(old["after"])
            self.status.set_text(self.record_status(record))
        except Exception as error:
            if snapshot is not None:
                self.restore(bounds, snapshot)
                self.refresh()
            self.status.set_text(str(error))
            traceback.print_exc()
        self.update_side_control()
        self.area.queue_draw()
        gimp.displays_flush()

    def change_side(self, *unused):
        if self.points or not self.history:
            return
        record = self.history[-1]
        if record["side"] is None:
            self.status.set_text("Zmiana strony dotyczy ostatniej linii, nie pojedynczego punktu.")
            return
        opposite = -record["side"]
        if opposite not in record["sources"]:
            self.status.set_text("Brak bezpiecznej probki po drugiej stronie.")
            return
        bounds = record["bounds"]
        previous = self.read_patch(bounds)
        try:
            self.restore(bounds, record["before"])
            self.apply_dabs(record["dabs"], record["sources"][opposite]["offset"],
                            record["diameter"])
            after = self.read_patch(bounds)
            self.refresh()
            self.history_bytes += len(after) - len(record["after"])
            record["after"], record["side"] = after, opposite
            self.status.set_text(self.record_status(record))
        except Exception as error:
            self.restore(bounds, previous)
            self.refresh()
            self.status.set_text("Nie zmieniono strony: " + str(error))
            traceback.print_exc()
        self.update_side_control()
        self.area.queue_draw()
        gimp.displays_flush()

    def undo(self, *unused):
        if self.points or not self.history:
            return
        record = self.history.pop()
        self.history_bytes -= len(record["before"]) + len(record["after"])
        self.restore(record["bounds"], record["before"])
        self.refresh()
        self.status.set_text("Cofnieto naprawe. Cofniecia: %d" % len(self.history))
        self.update_side_control()
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
