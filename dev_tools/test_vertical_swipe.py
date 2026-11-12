import unittest

import numpy as np

from module.base.cBezier import BezierTrajectory


class VerticalSwipeTest(unittest.TestCase):
    def test_inventory_vertical_swipes_remain_finite(self):
        for start, end in (((380, 230), (380, 560)), ((380, 560), (380, 230))):
            for timing in range(4):
                for degree in (2, 3, 4):
                    with self.subTest(start=start, timing=timing, degree=degree):
                        points = BezierTrajectory.trackArray(
                            start=start, end=end, numberList=33, le=degree,
                            deviation=30, bias=.5, type=timing, cbb=0, yhh=20)
                        self.assertEqual(points[0], list(start))
                        self.assertEqual(points[-1], list(end))
                        self.assertEqual(len(points), 33)
                        self.assertTrue(np.isfinite(points).all())

    def test_stationary_path_is_safe(self):
        self.assertEqual(BezierTrajectory.trackArray(
            start=(380, 230), end=(380, 230), numberList=33),
            [[380, 230], [380, 230]])


if __name__ == '__main__':
    unittest.main()
