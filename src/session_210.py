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

