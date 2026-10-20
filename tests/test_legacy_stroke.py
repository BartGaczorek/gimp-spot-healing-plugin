"""Legacy controller regression tests; GTK and native Healing are test doubles."""
import os
import runpy
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakePDB(object):
    def __init__(self):
        self.calls = []
        self.data = bytearray([125, 125, 125, 255] * 200 * 200)
        self.fail_after = None

    def __getattr__(self, name):
        return lambda *args: None

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
            module = runpy.run_path(os.path.join(ROOT, "legacy", "spot-heal-210.py"))
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
        s.status = type("Label", (object,), {"set_text": lambda self, text: None})()
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


if __name__ == "__main__":
    unittest.main()
