import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gimp-spot-heal"))
from spot_core import Viewport, choose_source, stroke_bounds


def image(width=200, height=200):
    return bytearray([125, 125, 125, 255] * width * height)


class ViewportTests(unittest.TestCase):
    def test_fit_never_enlarges_small_photos(self):
        v = Viewport(100, 100)
        v.fit(1000, 800)
        self.assertEqual(v.zoom, 1)
        self.assertEqual(v.image_point(500, 400), (50, 50))

    def test_zoom_keeps_pixel_under_cursor(self):
        v = Viewport(6000, 4000)
        v.fit(1000, 700)
        before = v.image_point(345, 287)
        v.zoom_at(1.2, 345, 287)
        after = v.image_point(345, 287)
        for a, b in zip(before, after):
            self.assertAlmostEqual(a, b)

    def test_stroke_bounds_include_brush_and_clip_to_layer(self):
        self.assertEqual(stroke_bounds([(0, 0), (99, 99)], 20, 100, 100), (0, 0, 100, 100))


class SourceTests(unittest.TestCase):
    def test_donor_excludes_entire_stroke(self):
        points = [(80, 100), (120, 100)]
        dx, dy = choose_source(image(), 200, 200, points, 10)
        self.assertTrue(abs(dx) > 54 or abs(dy) > 14)

    def test_defect_interior_does_not_influence_selection(self):
        pixels = image()
        before = choose_source(pixels, 200, 200, [(100, 100)], 10)
        for y in range(96, 105):
            for x in range(96, 105):
                i = (y * 200 + x) * 4
                pixels[i:i + 4] = bytearray([255, 0, 255, 255])
        self.assertEqual(before, choose_source(pixels, 200, 200, [(100, 100)], 10))

    def test_avoids_contrasting_half_of_image(self):
        pixels = image()
        for y in range(200):
            for x in range(108, 200):
                i = (y * 200 + x) * 4
                pixels[i:i + 4] = bytearray([0, 0, 0, 255])
        dx, _ = choose_source(pixels, 200, 200, [(100, 100)], 10)
        self.assertLessEqual(dx, 0)

    def test_rejects_transparent_sources(self):
        pixels = bytearray([125, 125, 125, 0] * 200 * 200)
        for y in range(91, 110):
            for x in range(91, 110):
                pixels[(y * 200 + x) * 4 + 3] = 255
        with self.assertRaises(ValueError):
            choose_source(pixels, 200, 200, [(100, 100)], 10)

    def test_edge_is_reported_without_modifying_pixels(self):
        pixels = image()
        before = bytes(pixels)
        with self.assertRaises(ValueError):
            choose_source(pixels, 200, 200, [(2, 2)], 10)
        self.assertEqual(pixels, before)


if __name__ == "__main__":
    unittest.main()
