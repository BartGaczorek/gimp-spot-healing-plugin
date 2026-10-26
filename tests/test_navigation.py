"""Wheel routing regression tests without a GIMP installation."""
import os
import sys
import types
import unittest


class NavigationTests(unittest.TestCase):
    def setUp(self):
        gtk = types.ModuleType('gtk')
        gtk.gdk = types.ModuleType('gdk')
        for name, value in [('SCROLL_UP', 0), ('SCROLL_DOWN', 1),
                            ('CONTROL_MASK', 4), ('MOD1_MASK', 8)]:
            setattr(gtk.gdk, name, value)
        fu = types.ModuleType('gimpfu')
        fu.gimp = fu.pdb = None
        fu.PF_IMAGE = fu.PF_DRAWABLE = fu.NORMAL_MODE = 0
        fu.register = fu.main = lambda *a, **kw: None
        stubs = {'gtk': gtk, 'gimpui': types.ModuleType('gimpui'), 'gimpfu': fu}
        saved = dict((k, sys.modules.get(k)) for k in stubs)
        self.module = {'__name__': 'navigation_test'}
        try:
            sys.modules.update(stubs)
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'legacy', 'spot-heal-210.py')
            with open(path, 'rb') as stream:
                eval(compile(stream.read(), path, 'exec'), self.module)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        cls = self.module['LegacySession']
        s = self.s = cls.__new__(cls)
        s.view = self.module['Viewport'](200, 200)
        s.points, s.busy, s.diameter = [], False, 16
        s.area = type('Area', (object,), {'queue_draw': lambda self: None})()
        s.size = type('Size', (object,), {
            'set_value': lambda widget, v: (setattr(widget, 'value', v), s.change_size(widget)),
            'get_value': lambda widget: widget.value})()

    def scroll(self, state=0, direction=0):
        event = type('Event', (object,), dict(state=state, direction=direction, x=75, y=60))()
        return self.s.scroll(self.s.area, event)

    def test_plain_scroll_pans_only_vertically_and_reverses(self):
        v = self.s.view
        before = v.x, v.y, v.zoom
        self.scroll()
        self.assertEqual((v.x, v.y, v.zoom), (before[0], before[1]+50, before[2]))
        self.scroll(direction=1)
        self.assertEqual((v.x, v.y, v.zoom), before)

    def test_control_zoom_preserves_cursor_anchor(self):
        v = self.s.view
        anchor = v.image_point(75, 60)
        zoom = v.zoom
        self.scroll(4)
        self.assertAlmostEqual(v.zoom, zoom*1.2)
        for a,b in zip(anchor, v.image_point(75,60)):
            self.assertAlmostEqual(a,b)
        self.scroll(4,1)
        self.assertAlmostEqual(v.zoom, zoom)

    def test_control_alt_changes_size_without_moving_view(self):
        v = self.s.view
        before = v.x,v.y,v.zoom
        self.scroll(12)
        self.assertEqual(self.s.diameter,17)
        self.assertEqual(self.s.size.value,17)
        self.scroll(12,1)
        self.assertEqual(self.s.diameter,16)
        self.assertEqual((v.x,v.y,v.zoom),before)
        self.s.diameter=256
        self.scroll(12)
        self.assertEqual(self.s.diameter,256)
        self.s.diameter=1
        self.scroll(12,1)
        self.assertEqual(self.s.diameter,1)

    def test_stroke_blocks_all_wheel_actions(self):
        v=self.s.view
        before=v.x,v.y,v.zoom,self.s.diameter
        self.s.points=[(20,20)]
        for state in (0,4,12):
            self.scroll(state)
            self.assertEqual((v.x,v.y,v.zoom,self.s.diameter),before)

    def test_horizontal_event_is_not_mistaken_for_zoom_out(self):
        v=self.s.view
        before=v.x,v.y,v.zoom,self.s.diameter
        self.scroll(4,2)
        self.assertEqual((v.x,v.y,v.zoom,self.s.diameter),before)
