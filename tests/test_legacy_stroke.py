"""Legacy controller regression tests; GTK and native Healing are test doubles."""
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakePDB(object):
    def __init__(self):
        self.calls = []
        self.data = bytearray([125, 125, 125, 255] * 200 * 200)
        self.fail_after = None
        self.brush_sizes = []

    def __getattr__(self, name):
        return lambda *args: None

    def gimp_context_set_brush_size(self, diameter):
        self.brush_sizes.append(diameter)

    def gimp_heal(self, layer, source, sx, sy, count, coordinates):
        if self.fail_after is not None and len(self.calls) == self.fail_after:
            raise RuntimeError("Simulated native Healing failure")
        self.calls.append((sx, sy, count, list(coordinates)))
        x, y = coordinates
        self.data[(int(y) * 200 + int(x)) * 4] = 255


class LegacyStrokeTests(unittest.TestCase):
    def setUp(self):
        self.native = FakePDB()
        gtk = types.ModuleType("gtk")
        ui = types.ModuleType("gimpui")
        fu = types.ModuleType("gimpfu")
        fu.gimp = types.ModuleType("gimp")
        fu.gimp.displays_flush = lambda: None
        fu.pdb = self.native
        fu.register = fu.main = lambda *args, **kwargs: None
        fu.PF_IMAGE = fu.PF_DRAWABLE = fu.NORMAL_MODE = 0
        stubs = {"gtk": gtk, "gimpui": ui, "gimpfu": fu}
        saved = dict((key, sys.modules.get(key)) for key in stubs)
        try:
            sys.modules.update(stubs)
            path = os.path.join(ROOT, "legacy", "spot-heal-210.py")
            module = {"__name__": "spot_heal_test", "__file__": path}
            with open(path, "rb") as stream:
                eval(compile(stream.read(), path, "exec"), module)
        finally:
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value
        self.session = module["LegacySession"].__new__(module["LegacySession"])
        s = self.session
        s.width = s.height = 200
        s.diameter = 10
        s.layer = type("Layer", (object,), {"bpp": 4})()
        s.pixels = bytearray(self.native.data)
        s.history = []
        s.history_bytes = 0
        s.points = []
        s.area = type("Area", (object,), {"queue_draw": lambda self: None})()
        s.status = type("Label", (object,), {"set_text": lambda self, text: setattr(self, "text", text)})()
        s.side_button = type("Button", (object,), {"set_sensitive": lambda self, enabled: setattr(self, "enabled", enabled)})()
        s.refresh = lambda: None
        s.read_patch = lambda bounds: bytearray(self.native.data)
        s.restore = lambda bounds, snapshot: self.native.data.__setitem__(slice(None), snapshot)

    def test_drag_repairs_start_middle_end_and_undoes_as_one_action(self):
        original = bytearray(self.native.data)
        self.session.repair([(80, 100), (120, 100)])
        targets = [call[3] for call in self.native.calls]
        self.assertIn([80, 100], targets)
        self.assertIn([100, 100], targets)
        self.assertIn([120, 100], targets)
        self.assertEqual(len(self.session.history), 1)
        self.assertNotEqual(self.native.data, original)
        self.session.undo()
        self.assertEqual(self.native.data, original)
        self.assertEqual(self.session.history, [])

    def test_native_failure_rolls_back_the_whole_drag(self):
        original = bytearray(self.native.data)
        self.native.fail_after = 2
        self.session.repair([(80, 100), (120, 100)])
        self.assertEqual(len(self.native.calls), 2)
        self.assertEqual(self.native.data, original)
        self.assertEqual(self.session.history, [])


    def test_all_dabs_use_one_normal_offset(self):
        self.session.repair([(80, 100), (120, 100)])
        offsets = [(sx - p[0], sy - p[1]) for sx, sy, count, p in self.native.calls]
        self.assertTrue(all(abs(dx) < 1e-7 for dx, dy in offsets))
        self.assertTrue(all(abs(dy - offsets[0][1]) < 1e-7 for dx, dy in offsets))
        self.assertTrue(self.session.side_button.enabled)

    def test_repeated_side_switch_replays_the_whole_line_without_extra_undo(self):
        s = self.session
        s.repair([(80, 100), (120, 100)])
        initial = s.history[-1]["side"]
        count = len(self.native.calls)
        snapshot_bytes = s.history_bytes
        self.native.calls = []
        s.change_side()
        self.assertEqual(s.history[-1]["side"], -initial)
        self.assertEqual(len(self.native.calls), count)
        self.assertEqual(len(s.history), 1)
        self.assertEqual(s.history_bytes, snapshot_bytes)
        self.assertTrue(all(initial * (sy - p[1]) < 0 for sx, sy, n, p in self.native.calls))
        s.change_side()
        self.assertEqual(s.history[-1]["side"], initial)
        self.assertEqual(len(s.history), 1)

    def test_switch_uses_original_brush_size_and_preserves_previous_repairs(self):
        s = self.session
        s.repair([(80, 70), (120, 70)])
        previous = bytearray(self.native.data)
        s.repair([(80, 120), (120, 120)])
        s.diameter = 80
        s.change_side()
        self.assertEqual(self.native.brush_sizes[-1], 10)
        self.assertEqual(len(s.history), 2)
        s.undo()
        self.assertEqual(self.native.data, previous)
        s.undo()
        self.assertEqual(s.history_bytes, 0)

    def test_failed_switch_restores_previous_result_and_selected_side(self):
        s = self.session
        s.repair([(80, 100), (120, 100)])
        previous = bytearray(self.native.data)
        side = s.history[-1]["side"]
        self.native.fail_after = len(self.native.calls) + 2
        s.change_side()
        self.assertEqual(self.native.data, previous)
        self.assertEqual(s.history[-1]["side"], side)
        self.assertEqual(len(s.history), 1)

    def test_single_point_has_no_side_switch(self):
        s = self.session
        s.repair([(100, 100)])
        self.assertFalse(s.side_button.enabled)
        count = len(self.native.calls)
        s.change_side()
        self.assertEqual(len(self.native.calls), count)

    def test_missing_opposite_side_does_not_destroy_the_result(self):
        s = self.session
        s.repair([(40, 15), (160, 15)])
        self.assertEqual(len(s.history), 1)
        self.assertFalse(s.side_button.enabled)
        previous = bytearray(self.native.data)
        calls = len(self.native.calls)
        s.change_side()
        self.assertEqual(self.native.data, previous)
        self.assertEqual(len(self.native.calls), calls)

    def test_undo_reenables_switch_for_the_previous_line(self):
        s = self.session
        s.repair([(80, 100), (120, 100)])
        s.repair([(100, 150)])
        self.assertFalse(s.side_button.enabled)
        s.undo()
        self.assertTrue(s.side_button.enabled)
        self.assertEqual(len(s.history), 1)


if __name__ == "__main__":
    unittest.main()
