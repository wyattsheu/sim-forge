"""Portable pack integrity checks; no network, GPU, or generation required."""
import hashlib
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import warnings
import zipfile

import asset_tools as tools


class AssetPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / 'pack.zip'
        self.dest = self.root / 'assets'
        self.content = b'known asset bytes'
        self.expected = {'toy/model.glb': {'size_bytes': len(self.content),
                         'sha256': hashlib.sha256(self.content).hexdigest()}}

    def make_pack(self, members=None):
        with zipfile.ZipFile(self.pack, 'w') as archive:
            for name, data in members or [('toy/model.glb', self.content)]:
                archive.writestr(name, data)
        return {'release': {'size_bytes': self.pack.stat().st_size, 'sha256': tools.sha256(self.pack)}}

    def test_roundtrip_is_verified_and_second_fetch_preserves_files(self):
        manifest = self.make_pack()
        result = tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertEqual(result['verified_files'], 1)
        before = (self.dest / 'toy/model.glb').stat().st_mtime_ns
        tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertEqual((self.dest / 'toy/model.glb').stat().st_mtime_ns, before)

    def test_modified_archive_is_rejected_before_extraction(self):
        manifest = self.make_pack()
        self.pack.write_bytes(self.pack.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'Archive checksum'):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertFalse(self.dest.exists())

    def test_wrong_member_bytes_leave_no_partial_destination(self):
        manifest = self.make_pack([('toy/model.glb', b'x' * len(self.content))])
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertFalse(self.dest.exists())

    def test_existing_modified_assets_are_not_overwritten(self):
        manifest = self.make_pack()
        tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        target = self.dest / 'toy/model.glb'
        target.write_bytes(b'my experiment')
        with self.assertRaises(ValueError):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertEqual(target.read_bytes(), b'my experiment')

    def test_path_traversal_and_extra_members_are_rejected(self):
        manifest = self.make_pack([('toy/model.glb', self.content), ('../outside.txt', b'bad')])
        with self.assertRaisesRegex(ValueError, 'archive members'):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        self.assertFalse((self.root / 'outside.txt').exists())
        for path in ('../outside', '/absolute', 'C:/absolute', 'toy\\escape', 'toy/../escape'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tools.safe_relative(path)

    def test_duplicate_zip_members_are_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            manifest = self.make_pack([('toy/model.glb', self.content)] * 2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)

    def test_symlink_zip_member_is_rejected(self):
        member = zipfile.ZipInfo('toy/model.glb')
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        manifest = self.make_pack([(member, self.content)])
        with self.assertRaisesRegex(ValueError, 'regular asset files'):
            tools.unpack_verified(self.pack, self.dest, manifest, self.expected)

    def test_added_file_is_detected_as_inventory_change(self):
        manifest = self.make_pack()
        tools.unpack_verified(self.pack, self.dest, manifest, self.expected)
        (self.dest / 'unexpected.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            tools.verify_assets(self.dest, self.expected)

    def test_manifest_cannot_mark_unaccepted_assets_as_shareable(self):
        manifest = self.make_pack()
        manifest.update(schema_version='diaggen-shared-assets-v1', assets=[{
            'id': 'toy', 'strict_genesis_accept': False,
            'files': {'model.glb': self.expected['toy/model.glb']}}])
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'strict-accepted'):
            tools.read_manifest(path)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / 'toy'
        (self.asset / 'appearance').mkdir(parents=True)
        (self.asset / 'final_mesh.mesh').write_text('MeshVersionFormatted 1\nDimension 3\nVertices\n4\n0 0 0 1\n1 0 0 1\n0 1 0 1\n0 0 1 1\nTetrahedra\n1\n1 2 3 4 1\nEnd\n')
        (self.asset / 'appearance/visual_mesh.glb').write_bytes(struct.pack('<4sII', b'glTF', 2, 12))
        (self.asset / 'inferred_params.json').write_text('{"predictions":[]}')
        self.save_arrays()

    def save_arrays(self, count=1):
        self.np.savez(self.asset / 'heterogeneous_params.npz', tet_part_labels=self.np.zeros(count, dtype=int),
                      tet_density=self.np.full(count, 6.), tet_E_nu=self.np.tile([100., .3], (count, 1)),
                      part_indices=self.np.array([0]))

    def test_cpu_inspection_reports_geometry_and_computed_mass(self):
        result = tools.inspect_asset(self.root, {'id': 'toy', 'run_id': 'synthetic'})
        self.assertEqual(result['tetrahedra'], 1)
        self.assertEqual(result['bbox_extent_m'], [1., 1., 1.])
        self.assertAlmostEqual(result['computed_mass_kg_from_inferred_density'], 1.)

    def test_wrong_material_array_length_is_rejected(self):
        self.save_arrays(count=2)
        with self.assertRaisesRegex(ValueError, 'count disagree'):
            tools.inspect_asset(self.root, {'id': 'toy', 'run_id': 'synthetic'})


if __name__ == '__main__':
    unittest.main()
