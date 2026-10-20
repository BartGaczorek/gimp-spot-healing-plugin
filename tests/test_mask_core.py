import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from mask_core import (rasterize_stroke, source_is_safe, choose_sources, boundary_of,
                       poisson_patch, mask_bounds, encode, Viewport)


def flat(width=96, height=96, color=125):
    return bytearray([color, color, color, 255] * width * height)


def paste(pixels, width, bounds, patch):
    result = bytearray(pixels)
    x0, y0, bw, bh = bounds
    for y in range(bh):
        i = ((y0 + y) * width + x0) * 4
        result[i:i + bw * 4] = patch[y * bw * 4:(y + 1) * bw * 4]
    return result


class MaskTests(unittest.TestCase):
    def test_single_click_is_a_disk(self):
        mask = rasterize_stroke([(48, 48)], 6, 96, 96)
        self.assertIn((48, 48), mask)
        self.assertTrue(all((x - 48) ** 2 + (y - 48) ** 2 <= 9 for x, y in mask))

    def test_fast_drag_covers_the_complete_segment(self):
        mask = rasterize_stroke([(20, 48), (76, 48)], 6, 96, 96)
        self.assertTrue(all((x, 48) in mask for x in range(20, 77)))

    def test_one_pixel_brush_at_subpixel_position_still_marks_a_pixel(self):
        self.assertTrue(rasterize_stroke([(48.5, 48.5)], 1, 96, 96))

    def test_scribble_forms_one_filled_area(self):
        mask = rasterize_stroke([(30, 30), (60, 30), (60, 36), (30, 36),
                                 (30, 42), (60, 42)], 8, 96, 96)
        self.assertTrue(all((x, y) in mask for x in range(30, 61) for y in range(30, 43)))

    def test_source_uses_shape_not_just_overlapping_bounding_boxes(self):
        mask = rasterize_stroke([(20, 20), (60, 60)], 2, 96, 96)
        self.assertTrue(source_is_safe(mask, (6, -6), 96, 96))
        self.assertFalse(source_is_safe(mask, (1, 0), 96, 96))

    def test_margin_and_image_bounds_are_enforced(self):
        mask = frozenset([(48, 48)])
        self.assertFalse(source_is_safe(mask, (2, 0), 96, 96))
        self.assertTrue(source_is_safe(mask, (3, 0), 96, 96))
        self.assertFalse(source_is_safe(mask, (47, 0), 96, 96))

    def test_boundary_is_outside_the_defect(self):
        mask = rasterize_stroke([(48, 48)], 6, 96, 96)
        self.assertFalse(set(mask) & boundary_of(mask))

    def test_large_masks_require_more_source_displacement(self):
        pixels = flat()
        small = rasterize_stroke([(48, 48)], 4, 96, 96)
        large = frozenset((x, y) for x in range(38, 59) for y in range(38, 59))
        a = choose_sources(pixels, 96, 96, small, 4)
        b = choose_sources(pixels, 96, 96, large, 4)
        self.assertGreater(math.hypot(*b[0]["offset"]), math.hypot(*a[0]["offset"]))
        for item in b:
            self.assertTrue(source_is_safe(large, item["offset"], 96, 96))

    def test_transparent_sources_are_rejected(self):
        pixels = flat()
        pixels[3::4] = bytearray([0] * (96 * 96))
        mask = rasterize_stroke([(48, 48)], 6, 96, 96)
        for x, y in set(mask) | boundary_of(mask):
            pixels[(x + y * 96) * 4 + 3] = 255
        with self.assertRaises(ValueError):
            choose_sources(pixels, 96, 96, mask, 6)

    def test_oversized_masks_and_edge_strokes_are_rejected(self):
        with self.assertRaises(ValueError):
            rasterize_stroke([(200, 200)], 200, 400, 400)
        with self.assertRaises(ValueError):
            rasterize_stroke([(0, 48)], 6, 96, 96)


class PoissonTests(unittest.TestCase):
    def test_recovers_texture_with_illumination_difference_and_keeps_exterior(self):
        width = height = 96
        clean = flat()
        for y in range(height):
            for x in range(width):
                value = 0.3 + 0.1 * math.sin(x * math.pi / 4) + 0.07 * math.cos(y * math.pi / 4) + 0.1 * x / width
                i = (x + y * width) * 4
                clean[i:i + 3] = bytearray([encode(value)] * 3)
        pixels = bytearray(clean)
        mask = rasterize_stroke([(48, 48)], 12, width, height)
        for x, y in mask:
            i = (x + y * width) * 4
            pixels[i:i + 3] = bytearray([255, 0, 255])
        before = bytearray(pixels)
        bounds, patch, stats = poisson_patch(pixels, width, height, mask, (24, 0))
        output = paste(pixels, width, bounds, patch)
        errors = [abs(output[(x + y * width) * 4 + c] - clean[(x + y * width) * 4 + c])
                  for x, y in mask for c in range(3)]
        self.assertLessEqual(max(errors), 2)
        texture = [output[(x + y * width) * 4] for x, y in mask]
        self.assertGreater(max(texture) - min(texture), 30)
        self.assertEqual(pixels, before)
        for y in range(height):
            for x in range(width):
                if (x, y) not in mask:
                    i = (x + y * width) * 4
                    self.assertEqual(output[i:i + 4], before[i:i + 4])
        self.assertLessEqual(stats["residual"], 1e-5)

    def test_result_does_not_depend_on_the_defect_colors(self):
        mask = rasterize_stroke([(48, 48), (54, 50)], 6, 96, 96)
        a, b = flat(), flat()
        for x, y in mask:
            i = (x + y * 96) * 4
            a[i:i + 3] = bytearray([255, 0, 0])
            b[i:i + 3] = bytearray([0, 255, 255])
        self.assertEqual(poisson_patch(a, 96, 96, mask, (24, 0))[1],
                         poisson_patch(b, 96, 96, mask, (24, 0))[1])

    def test_fills_constant_target_boundary_even_when_donor_is_brighter(self):
        pixels = flat()
        mask = rasterize_stroke([(32, 48)], 8, 96, 96)
        for x, y in set(mask) | boundary_of(mask):
            i = ((x + 32) + y * 96) * 4
            pixels[i:i + 3] = bytearray([210, 210, 210])
        bounds, patch, stats = poisson_patch(pixels, 96, 96, mask, (32, 0))
        result = paste(pixels, 96, bounds, patch)
        self.assertTrue(all(abs(result[(x + y * 96) * 4] - 125) <= 1 for x, y in mask))

    def test_nonconverged_solution_and_overlapping_source_are_rejected(self):
        pixels = flat()
        mask = rasterize_stroke([(32, 48)], 8, 96, 96)
        for x, y in set(mask) | boundary_of(mask):
            i = ((x + 32) + y * 96) * 4
            pixels[i:i + 3] = bytearray([210, 210, 210])
        with self.assertRaises(ValueError):
            poisson_patch(pixels, 96, 96, mask, (32, 0), max_iterations=0)
        with self.assertRaises(ValueError):
            poisson_patch(pixels, 96, 96, mask, (0, 0))


class ViewTests(unittest.TestCase):
    def test_fit_and_zoom_anchor(self):
        view = Viewport(6000, 4000)
        view.fit(1000, 700)
        self.assertLess(view.zoom, 1)
        before = view.image_point(300, 200)
        view.zoom_at(1.2, 300, 200)
        for a, b in zip(before, view.image_point(300, 200)):
            self.assertAlmostEqual(a, b)


if __name__ == "__main__":
    unittest.main()
