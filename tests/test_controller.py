"""Exercise actual mask computation and blending; only GIMP/GTK are doubles."""
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from mask_core import rasterize_stroke


def as_bytes(data):
    return data.decode("latin1").encode("latin1")


class Region(object):
    def __init__(self, layer):
        self.layer = layer

    def __getitem__(self, slices):
        xs, ys = slices
        result = bytearray()
        for y in range(ys.start, ys.stop):
            i = (y * self.layer.width + xs.start) * self.layer.bpp
            result.extend(self.layer.data[i:i + (xs.stop - xs.start) * self.layer.bpp])
        return as_bytes(result)

    def __setitem__(self, slices, value):
        xs, ys = slices
        row = (xs.stop - xs.start) * self.layer.bpp
        for n, y in enumerate(range(ys.start, ys.stop)):
            i = (y * self.layer.width + xs.start) * self.layer.bpp
            self.layer.data[i:i + row] = bytearray(value[n * row:(n + 1) * row])
            if self.layer.fail_next:
                self.layer.fail_next = False
                raise RuntimeError("Simulated native write failure")


class Layer(object):
    def __init__(self, bpp=4):
        self.width = self.height = 96
        self.bpp = bpp
        self.data = bytearray(([125, 125, 125, 255] if bpp == 4 else [125] * 3) * 96 * 96)
        self.fail_next = False

    def get_pixel_rgn(self, *args):
        return Region(self)

    def flush(self):
        pass

    def update(self, *args):
        pass


class Widget(object):
    def queue_draw(self):
        pass

    def grab_focus(self):
        pass

    def set_sensitive(self, value):
        self.enabled = value

    def set_text(self, value):
        self.text = value

    def set_response_sensitive(self, *args):
        pass


class ControllerTests(unittest.TestCase):
    def setUp(self):
        gtk, ui, fu = (types.ModuleType(name) for name in ("gtk", "gimpui", "gimpfu"))
        gtk.RESPONSE_OK, gtk.RESPONSE_CANCEL = 1, 0
        gtk.events_pending = lambda: False
        gtk.gdk = types.ModuleType("gdk")
        gtk.gdk.COLORSPACE_RGB = 0
        gtk.gdk.pixbuf_new_from_data = lambda *args: None
        fu.gimp = types.ModuleType("gimp")
        fu.gimp.displays_flush = lambda: None
        fu.pdb = object()  # Any PDB Healing call would fail the test.
        fu.register = fu.main = lambda *args, **kwargs: None
        fu.PF_IMAGE = fu.PF_DRAWABLE = 0
        stubs = {"gtk": gtk, "gimpui": ui, "gimpfu": fu}
        saved = dict((key, sys.modules.get(key)) for key in stubs)
        try:
            sys.modules.update(stubs)
            path = os.path.join(ROOT, "legacy", "spot-heal-mask-210.py")
            self.module = {"__name__": "mask_test", "__file__": path}
            with open(path, "rb") as stream:
                eval(compile(stream.read(), path, "exec"), self.module)
        finally:
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value
        cls = self.module["MaskSession"]
        self.session = cls.__new__(cls)
        s = self.session
        s.layer = Layer()
        s.width = s.height = 96
        s.view = self.module["Viewport"](96, 96)
        s.points, s.pending_points, s.history = [], [], []
        s.busy = False
        s.history_bytes = 0
        s.diameter = 6
        s.pan = s.cursor = None
        s.toolbar, s.area, s.dialog = Widget(), Widget(), Widget()
        s.status, s.alternative_button = Widget(), Widget()
        self.make_defect([(40, 48), (55, 48)])
        s.refresh()

    def make_defect(self, points):
        s = self.session
        for x, y in rasterize_stroke(points, s.diameter, 96, 96):
            i = (x + y * 96) * s.layer.bpp
            s.layer.data[i:i + 3] = bytearray([255, 0, 255])

    def event(self, x, y):
        return type("Event", (object,), {"x": x, "y": y, "button": 1})()

    def test_only_release_triggers_one_solve_for_the_entire_drag(self):
        s = self.session
        before = bytearray(s.layer.data)
        calls = []
        solve = self.module["poisson_patch"]
        def counted(*args, **kwargs):
            calls.append(len(args[3]))
            return solve(*args, **kwargs)
        self.module["poisson_patch"] = counted
        s.press(s.area, self.event(40, 48))
        s.motion(s.area, self.event(55, 48))
        self.assertEqual(s.layer.data, before)
        self.assertEqual(calls, [])
        s.release(s.area, self.event(55, 48))
        self.assertEqual(len(calls), 1)
        self.assertGreater(calls[0], 100)
        self.assertEqual(len(s.history), 1)
        self.assertNotEqual(s.layer.data, before)
        self.assertFalse(s.busy)

    def test_alternative_and_undo_preserve_one_history_action(self):
        s = self.session
        before = bytearray(s.layer.data)
        s.repair([(40, 48), (55, 48)])
        self.assertTrue(s.alternative_button.enabled)
        count = len(s.history[-1]["mask"])
        s.diameter = 50
        s.alternative()
        self.assertEqual(s.history[-1]["index"], 1)
        self.assertEqual(len(s.history[-1]["mask"]), count)
        self.assertEqual(len(s.history), 1)
        s.undo()
        self.assertEqual(s.layer.data, before)
        self.assertEqual(s.history_bytes, 0)

    def test_failed_alternative_restores_previous_result(self):
        s = self.session
        s.repair([(40, 48), (55, 48)])
        before = bytearray(s.layer.data)
        s.layer.fail_next = True
        s.alternative()
        self.assertEqual(s.layer.data, before)
        self.assertEqual(s.history[-1]["index"], 0)
        self.assertFalse(s.busy)

    def test_initial_native_failure_leaves_image_and_history_unchanged(self):
        s = self.session
        before = bytearray(s.layer.data)
        s.layer.fail_next = True
        s.repair([(40, 48), (55, 48)])
        self.assertEqual(s.layer.data, before)
        self.assertEqual(s.history, [])
        self.assertFalse(s.busy)

    def test_rgb_region_conversion_is_lossless_and_supported(self):
        s = self.session
        s.layer = Layer(bpp=3)
        self.make_defect([(40, 48), (55, 48)])
        s.refresh()
        before = bytearray(s.layer.data)
        s.repair([(40, 48), (55, 48)])
        self.assertEqual(len(s.history), 1)
        self.assertNotEqual(s.layer.data, before)
        s.undo()
        self.assertEqual(s.layer.data, before)

    def test_previous_repair_survives_repainting_and_undoing_latest_area(self):
        s = self.session
        s.repair([(40, 48), (55, 48)])
        previous = bytearray(s.layer.data)
        self.make_defect([(48, 70)])
        s.refresh()
        with_new_defect = bytearray(s.layer.data)
        s.repair([(48, 70)])
        s.alternative()
        s.undo()
        self.assertEqual(s.layer.data, with_new_defect)
        for x, y in s.history[-1]["mask"]:
            i = (x + y * 96) * 4
            self.assertEqual(s.layer.data[i:i + 4], previous[i:i + 4])

    def test_no_new_stroke_can_start_while_busy(self):
        s = self.session
        s.busy = True
        s.press(s.area, self.event(40, 48))
        self.assertEqual(s.points, [])

    def test_failed_undo_restores_result_and_keeps_history(self):
        s = self.session
        s.repair([(40, 48), (55, 48)])
        before = bytearray(s.layer.data)
        s.layer.fail_next = True
        s.undo()
        self.assertEqual(s.layer.data, before)
        self.assertEqual(len(s.history), 1)


if __name__ == "__main__":
    unittest.main()
