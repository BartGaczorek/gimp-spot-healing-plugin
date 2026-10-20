#!/usr/bin/env python3
"""Experimental GIMP 3 spot-healing session, with native GIMP reconstruction."""
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spot_core import Viewport, choose_source, stroke_bounds

import gi
gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gegl", "0.4")
gi.require_version("Gtk", "3.0")
gi.require_version("Babl", "0.1")
from gi.repository import Gimp, GimpUi, Gegl, Babl, Gtk, Gdk, GdkPixbuf, GLib

PROC = "plug-in-spot-heal"
MAX_HISTORY = 128 * 1024 * 1024


def rectangle(bounds):
    return Gegl.Rectangle.new(*bounds)


class Session:
    def __init__(self, image, layer):
        self.image, self.layer = image, layer
        self.width, self.height = layer.get_width(), layer.get_height()
        self.view = Viewport(self.width, self.height)
        self.history = []
        self.history_bytes = 0
        self.points = []
        self.pan = None
        self.cursor = None
        self.initialized = False
        self.diameter = 16
        # GEGL's Python get/set overrides accept format names, not Babl pointers.
        self.preview_format = "R'G'B'A u8"
        self.native_format = Babl.get_name(layer.get_format())
        self.refresh()

        self.dialog = Gtk.Dialog(title="Spot Heal — prototyp 0.1", modal=True)
        self.dialog.set_default_size(1040, 740)
        self.dialog.add_button("Anuluj", Gtk.ResponseType.CANCEL)
        self.dialog.add_button("Zastosuj", Gtk.ResponseType.OK)
        GimpUi.window_set_transient(self.dialog)
        content = self.dialog.get_content_area()
        toolbar = Gtk.Box(spacing=8, margin=8)
        content.pack_start(toolbar, False, False, 0)
        toolbar.pack_start(Gtk.Label(label="Średnica (px zdjęcia):"), False, False, 0)
        self.size = Gtk.SpinButton.new_with_range(1, 256, 1)
        self.size.set_value(self.diameter)
        self.size.connect("value-changed", self.change_size)
        toolbar.pack_start(self.size, False, False, 0)
        for label, callback in (("Dopasuj", self.fit), ("100%", self.actual_size),
                                ("Cofnij", self.undo)):
            button = Gtk.Button(label=label)
            button.connect("clicked", callback)
            toolbar.pack_start(button, False, False, 0)
        self.zoom_label = Gtk.Label()
        toolbar.pack_end(self.zoom_label, False, False, 0)
        self.area = Gtk.DrawingArea()
        self.area.set_size_request(320, 240)
        self.area.set_can_focus(True)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                             Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                             Gdk.EventMask.SMOOTH_SCROLL_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        for event, callback in (("draw", self.draw), ("size-allocate", self.allocate),
                                ("button-press-event", self.press),
                                ("button-release-event", self.release),
                                ("motion-notify-event", self.motion),
                                ("scroll-event", self.scroll),
                                ("leave-notify-event", self.leave)):
            self.area.connect(event, callback)
        self.dialog.connect("key-press-event", self.key)
        content.pack_start(self.area, True, True, 0)
        self.status = Gtk.Label(label="LPM: naprawa • przeciągnij: rysa • kółko: zoom • ŚPM: przesuwanie • Ctrl+Z: cofnij",
                                margin=8, xalign=0)
        self.status.set_line_wrap(True)
        content.pack_start(self.status, False, False, 0)

    def refresh(self):
        buffer = self.layer.get_buffer()
        self.pixels = bytes(buffer.get(rectangle((0, 0, self.width, self.height)), 1.0,
                                       self.preview_format, Gegl.AbyssPolicy.NONE))
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(self.pixels),
                         GdkPixbuf.Colorspace.RGB, True, 8,
                         self.width, self.height, self.width * 4)

    def change_size(self, widget):
        self.diameter = widget.get_value()
        self.area.queue_draw()

    def allocate(self, widget, allocation):
        if not self.initialized:
            self.fit()
            self.initialized = True

    def fit(self, *_):
        self.view.fit(self.area.get_allocated_width(), self.area.get_allocated_height())
        self.area.queue_draw()

    def actual_size(self, *_):
        w, h = self.area.get_allocated_width(), self.area.get_allocated_height()
        self.view.zoom_at(1 / self.view.zoom, w / 2, h / 2)
        self.area.queue_draw()

    def draw(self, widget, cr):
        cr.set_source_rgb(0.16, 0.16, 0.16)
        cr.paint()
        cr.save()
        cr.translate(self.view.x, self.view.y)
        cr.scale(self.view.zoom, self.view.zoom)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()
        cr.restore()
        if self.points:
            cr.set_source_rgba(0.2, 0.8, 1.0, 0.45)
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
            cr.arc(*self.cursor, max(1, self.diameter * self.view.zoom / 2), 0, math.tau)
            cr.stroke()
        self.zoom_label.set_text(f"{self.view.zoom:.0%}")

    def press(self, widget, event):
        widget.grab_focus()
        if event.button == 2:
            self.pan = event.x, event.y
        elif event.button == 1:
            p = self.view.image_point(event.x, event.y)
            if 0 <= p[0] < self.width and 0 <= p[1] < self.height:
                self.points = [p]
        return True

    def motion(self, widget, event):
        self.cursor = event.x, event.y
        if self.pan:
            self.view.x += event.x - self.pan[0]
            self.view.y += event.y - self.pan[1]
            self.pan = event.x, event.y
        elif self.points:
            p = self.view.image_point(event.x, event.y)
            if math.dist(p, self.points[-1]) >= max(1, self.diameter / 5):
                self.points.append(p)
        widget.queue_draw()
        return True

    def release(self, widget, event):
        if event.button == 2:
            self.pan = None
        elif event.button == 1 and self.points:
            points, self.points = self.points, []
            end = self.view.image_point(event.x, event.y)
            if math.dist(end, points[-1]) >= 1:
                points.append(end)
            self.repair(points)
        return True

    def scroll(self, widget, event):
        if self.points:
            return True
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            _, _, dy = event.get_scroll_deltas()
        else:
            dy = -1 if event.direction == Gdk.ScrollDirection.UP else 1
        self.view.zoom_at(1.2 ** (-max(-3, min(3, dy))), event.x, event.y)
        widget.queue_draw()
        return True

    def leave(self, widget, event):
        self.cursor = None
        widget.queue_draw()

    def key(self, widget, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.undo()
            return True
        return False

    def restore(self, bounds, snapshot):
        buffer = self.layer.get_buffer()
        buffer.set(rectangle(bounds), self.native_format, snapshot)
        buffer.flush()
        self.layer.update(*bounds)

    def repair(self, points):
        snapshot = None
        try:
            dx, dy = choose_source(self.pixels, self.width, self.height, points, self.diameter)
            bounds = stroke_bounds(points, self.diameter, self.width, self.height)
            snapshot = bytes(self.layer.get_buffer().get(rectangle(bounds), 1.0,
                                      self.native_format, Gegl.AbyssPolicy.NONE))
            if len(snapshot) > MAX_HISTORY:
                raise ValueError("Ruch jest zbyt rozległy. Podziel go na krótsze odcinki.")
            Gimp.context_push()
            try:
                brush = Gimp.Brush.get_by_name("2. Hardness 100")
                if brush is None:
                    raise ValueError("Brakuje standardowego pędzla ‘2. Hardness 100’.")
                Gimp.context_set_brush(brush)
                Gimp.context_set_brush_size(self.diameter)
                Gimp.context_set_brush_aspect_ratio(0.0)
                Gimp.context_set_brush_angle(0.0)
                Gimp.context_set_brush_hardness(1.0)
                Gimp.context_set_brush_force(1.0)
                Gimp.context_set_brush_spacing(10.0)
                Gimp.context_enable_dynamics(False)
                Gimp.context_set_opacity(100.0)
                Gimp.context_set_paint_mode(Gimp.LayerMode.NORMAL)
                Gimp.context_set_sample_merged(False)
                strokes = [v for point in points for v in point]
                if not Gimp.heal(self.layer, self.layer,
                                 points[0][0] + dx, points[0][1] + dy, strokes):
                    raise RuntimeError("GIMP Healing nie wykonał naprawy.")
            finally:
                Gimp.context_pop()
            self.refresh()
            self.history.append((bounds, snapshot))
            self.history_bytes += len(snapshot)
            while self.history_bytes > MAX_HISTORY and len(self.history) > 1:
                self.history_bytes -= len(self.history.pop(0)[1])
            self.status.set_text(f"Naprawiono. Źródło dobrane automatycznie • dostępne cofnięcia: {len(self.history)}")
        except Exception as error:
            if snapshot is not None:
                self.restore(bounds, snapshot)
                self.refresh()
            self.status.set_text(str(error))
            traceback.print_exc()
        self.area.queue_draw()
        Gimp.displays_flush()

    def undo(self, *_):
        if self.points or not self.history:
            return
        bounds, snapshot = self.history.pop()
        self.history_bytes -= len(snapshot)
        self.restore(bounds, snapshot)
        self.refresh()
        self.status.set_text(f"Cofnięto naprawę • dostępne cofnięcia: {len(self.history)}")
        self.area.queue_draw()
        Gimp.displays_flush()

    def run(self):
        self.dialog.show_all()
        try:
            return self.dialog.run() == Gtk.ResponseType.OK
        finally:
            self.dialog.destroy()


def run(procedure, run_mode, image, drawables, config, data):
    layer = None
    started = False
    keep = False
    try:
        if run_mode != Gimp.RunMode.INTERACTIVE:
            raise ValueError("Uruchom wtyczkę interaktywnie z menu GIMP-a.")
        if len(drawables) != 1 or not isinstance(drawables[0], Gimp.Layer) or drawables[0].is_group():
            raise ValueError("Wybierz jedną zwykłą warstwę RGB.")
        source = drawables[0]
        _, ox, oy = source.get_offsets()
        if ox or oy:
            raise ValueError("Prototyp wymaga warstwy bez przesunięcia względem płótna (offset 0, 0).")
        if not source.is_rgb() or source.get_mask() is not None or source.get_filters():
            raise ValueError("Prototyp wymaga warstwy RGB bez maski i aktywnych filtrów. Użyj kopii z widocznego obrazu.")
        if not Gimp.Selection.is_empty(image):
            raise ValueError("Najpierw usuń zaznaczenie: Zaznaczenie → Nic.")
        if source.get_width() * source.get_height() > 32_000_000:
            raise ValueError("Prototyp obsługuje warstwy do 32 megapikseli.")
        Gegl.init(None)
        GimpUi.init("gimp-spot-heal")
        image.undo_group_start()
        started = True
        layer = source.copy()
        image.insert_layer(layer, source.get_parent(), image.get_item_position(source))
        layer.set_name(source.get_name() + " — Spot Heal")
        layer.set_lock_content(False)
        layer.set_lock_alpha(False)
        keep = Session(image, layer).run()
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS if keep else Gimp.PDBStatusType.CANCEL, None)
    except Exception as error:
        traceback.print_exc()
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(error)))
    finally:
        if layer is not None and not keep:
            image.remove_layer(layer)
            image.set_selected_layers(drawables)
        if started:
            image.undo_group_end()
        Gimp.displays_flush()


class SpotHeal(Gimp.PlugIn):
    def do_query_procedures(self):
        return [PROC]

    def do_create_procedure(self, name):
        if name != PROC:
            return None
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        procedure.set_image_types("RGB*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        procedure.set_menu_label("Spot Heal…")
        procedure.add_menu_path("<Image>/Filters/Enhance")
        procedure.set_documentation("Retusz ze źródłem dobieranym automatycznie",
                                    "Eksperymentalny retusz jednym kliknięciem w osobnym oknie.", name)
        procedure.set_attribution("BartGaczorek and contributors", "BartGaczorek and contributors", "2026")
        return procedure


Gimp.main(SpotHeal.__gtype__, sys.argv)
