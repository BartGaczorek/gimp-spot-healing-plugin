"""Normal-direction source selection and complete-footprint safety."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gimp-spot-heal"))
from spot_core import choose_perpendicular_sources, resample_stroke, source_is_safe


class PerpendicularSourceTests(unittest.TestCase):
    def setUp(self):
        self.pixels = bytearray([125, 125, 125, 255] * 200 * 200)

    def sources(self, points, diameter=10):
        return choose_perpendicular_sources(self.pixels, 200, 200, points, diameter)

    def test_horizontal_has_only_top_and_bottom_sources(self):
        sources = self.sources([(40, 100), (160, 100)])
        self.assertEqual(set(sources), set((1, -1)))
        for side, source in sources.items():
            dx, dy = source["offset"]
            self.assertAlmostEqual(dx, 0)
            self.assertGreater(side * dy, 10)

    def test_vertical_has_only_left_and_right_sources(self):
        for side, source in self.sources([(100, 40), (100, 160)]).items():
            dx, dy = source["offset"]
            self.assertAlmostEqual(dy, 0)
            self.assertLess(side * dx, -10)

    def test_diagonal_offsets_are_perpendicular(self):
        for source in self.sources([(60, 60), (140, 140)]).values():
            dx, dy = source["offset"]
            self.assertAlmostEqual(80 * dx + 80 * dy, 0, places=7)

    def test_actual_brush_disks_do_not_overlap_anywhere_along_a_curve(self):
        path = resample_stroke([(50, 100), (100, 110), (150, 100)], 1)
        for source in self.sources(path).values():
            dx, dy = source["offset"]
            donor = [(math.floor(x + dx), math.floor(y + dy)) for x, y in path]
            nearest = min(math.hypot(x - sx, y - sy)
                          for x, y in path for sx, sy in donor)
            self.assertGreater(nearest, 10)
            self.assertTrue(source_is_safe(path, 10, 200, 200, source["offset"]))

    def test_longitudinal_offset_is_forbidden_even_if_disjoint(self):
        self.assertFalse(source_is_safe([(40, 100), (60, 100)], 10, 200, 200, (80, 0)))

    def test_too_close_parallel_paths_are_forbidden(self):
        self.assertFalse(source_is_safe([(40, 100), (160, 100)], 10, 200, 200, (0, 9)))

    def test_image_edge_can_leave_only_one_safe_side(self):
        self.assertEqual(set(self.sources([(40, 15), (160, 15)])), set((1,)))

    def test_opaque_donor_required_on_each_available_side(self):
        for y in range(80):
            for x in range(200):
                self.pixels[(x + y * 200) * 4 + 3] = 0
        self.assertEqual(set(self.sources([(40, 100), (160, 100)])), set((1,)))

    def test_initial_choice_prefers_side_matching_the_surroundings(self):
        for y in range(80):
            for x in range(200):
                i = (x + y * 200) * 4
                self.pixels[i:i + 3] = bytearray([220, 220, 220])
        sources = self.sources([(40, 100), (160, 100)])
        self.assertEqual(min(sources, key=lambda key: sources[key]["score"]), 1)

    def test_closed_path_is_rejected_without_a_direction(self):
        with self.assertRaises(ValueError):
            self.sources([(80, 80), (120, 100), (80, 80)])

    def test_strong_bend_is_rejected_when_neither_strip_can_be_separated(self):
        with self.assertRaises(ValueError):
            self.sources([(50, 40), (100, 160), (150, 40)])


if __name__ == "__main__":
    unittest.main()
