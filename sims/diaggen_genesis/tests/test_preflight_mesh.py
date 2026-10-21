"""Native tetrahedral material coverage regression; run in hag4r_mesh."""
from pathlib import Path
import sys
import unittest

NATIVE = Path(__file__).resolve().parents[3] / "tools" / "diaggen"
sys.path.insert(0, str(NATIVE))
try:
    import numpy as np
    from hag4r.tools.volumetric_meshing import analyze_tet_mesh, validate_tet_mesh, TetMeshValidationError
    IMPORT_ERROR = None
except ImportError as error:
    IMPORT_ERROR = str(error)


@unittest.skipIf(IMPORT_ERROR is not None, f"Run with hag4r_mesh Python: {IMPORT_ERROR}")
class NativeMaterialCoverageTests(unittest.TestCase):
    def setUp(self):
        self.points = np.asarray([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        self.tets = np.asarray([[0, 1, 2, 3]], dtype=np.int64)
        self.labels = np.asarray([0], dtype=np.int64)

    def arguments(self, expected, mode="exact"):
        return dict(points=self.points, tets=self.tets, tet_part_labels=self.labels,
                    expected_part_indices=expected, material_coverage=mode)

    def test_exact_missing_label_is_hard_failure_in_report_and_validator(self):
        report = analyze_tet_mesh(**self.arguments([0, 1]))
        self.assertFalse(report["material_label_coverage_valid"])
        self.assertFalse(report["valid"])
        self.assertEqual(report["missing_material_labels"], [1])
        self.assertTrue(any("coverage incomplete" in text for text in report["failures"]))
        with self.assertRaisesRegex(TetMeshValidationError, "coverage incomplete"):
            validate_tet_mesh(**self.arguments([0, 1]))

    def test_resolver_subset_still_permits_a_missing_original_label(self):
        report = analyze_tet_mesh(**self.arguments([0, 1], "subset"))
        self.assertTrue(report["valid"])
        self.assertTrue(report["material_label_coverage_valid"])
        self.assertEqual(report["missing_material_labels"], [1])
        self.assertTrue(validate_tet_mesh(**self.arguments([0, 1], "subset"))["valid"])

    def test_complete_exact_material_coverage_remains_valid(self):
        report = analyze_tet_mesh(**self.arguments([0]))
        self.assertTrue(report["valid"])
        self.assertTrue(report["material_label_coverage_valid"])
        self.assertTrue(validate_tet_mesh(**self.arguments([0]))["valid"])

    def test_subset_still_rejects_unexpected_material_label(self):
        with self.assertRaisesRegex(TetMeshValidationError, "unexpected labels"):
            validate_tet_mesh(**self.arguments([1], "subset"))


if __name__ == "__main__":
    unittest.main()
