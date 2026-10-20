import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gimp-spot-heal"))
from spot_core import Viewport, choose_source, stroke_bounds, resample_stroke


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



class ResampleTests(unittest.TestCase):
    def test_fast_drag_has_no_uncovered_gaps(self):
        points = resample_stroke([(10, 20), (90, 20)], 2)
        self.assertEqual(points[0], (10, 20))
        self.assertEqual(points[-1], (90, 20))
        self.assertGreater(len(points), 2)
        for a, b in zip(points, points[1:]):
            self.assertLessEqual(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5, 2.000001)

    def test_curve_keeps_corner_and_last_point(self):
        points = resample_stroke([(0, 0), (20, 0), (20, 30)], 3)
        self.assertIn((20, 0), points)
        self.assertEqual(points[-1], (20, 30))
        self.assertTrue(all(x == 20 or y == 0 for x, y in points))

    def test_single_click_stays_single(self):
        self.assertEqual(resample_stroke([(2, 3), (2, 3)], 1), [(2, 3)])

    def test_excessive_stroke_is_rejected_before_painting(self):
        with self.assertRaises(ValueError):
            resample_stroke([(0, 0), (1000, 0)], 1, max_points=10)


if __name__ == "__main__":
    unittest.main()
