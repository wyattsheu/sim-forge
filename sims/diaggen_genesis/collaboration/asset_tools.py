#!/usr/bin/env python3
"""Fetch immutable shared assets, verify checksums, or inspect meshes on CPU."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
MAX_PACK_BYTES = 256 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError('Invalid asset path')
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in ('.', '..') for p in value.split('/')):
        raise ValueError('Asset paths must be relative without traversal')
    return path


def read_manifest(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 'diaggen-shared-assets-v1':
        raise ValueError('Unsupported shared asset manifest')
    if not isinstance(data.get('assets'), list) or not data['assets']:
        raise ValueError('No shared assets')
    expected = {}
    ids = set()
    for asset in data['assets']:
        name = asset['id']
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name) or name in ids:
            raise ValueError('Invalid or repeated asset id')
        ids.add(name)
        if asset.get('strict_genesis_accept') is not True or not asset.get('files'):
            raise ValueError('Only completed strict-accepted exports are shared by this pack')
        for relative, record in asset['files'].items():
            path = str(safe_relative(name + '/' + relative))
            if (path in expected or not re.fullmatch(r'[a-f0-9]{64}', record['sha256'])
                    or type(record['size_bytes']) is not int or record['size_bytes'] <= 0):
                raise ValueError('Invalid asset file record')
            expected[path] = record
    release = data['release']
    if (not re.fullmatch(r'[a-f0-9]{64}', release['sha256'])
            or type(release['size_bytes']) is not int
            or not 0 < release['size_bytes'] <= MAX_PACK_BYTES
            or sum(r['size_bytes'] for r in expected.values()) > MAX_PACK_BYTES):
        raise ValueError('Invalid asset pack record')
    return data, expected


def verify_assets(directory, expected):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Assets directory is missing or unsafe; run fetch first')
    found = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('Asset directories must not contain symlinks')
        if path.is_file():
            found.add(path.relative_to(directory).as_posix())
    if found != set(expected):
        raise ValueError('Asset inventory differs from the pinned manifest')
    for relative, record in expected.items():
        path = directory / relative
        if path.stat().st_size != record['size_bytes'] or sha256(path) != record['sha256']:
            raise ValueError('Asset checksum mismatch: ' + relative)
    return {'verified_files': len(expected), 'verified_bytes': sum(r['size_bytes'] for r in expected.values())}


def unpack_verified(archive, directory, manifest, expected):
    archive, directory = Path(archive), Path(directory).absolute()
    if archive.stat().st_size != manifest['release']['size_bytes'] or sha256(archive) != manifest['release']['sha256']:
        raise ValueError('Archive checksum differs from the pinned release; nothing extracted')
    if directory.exists() or directory.is_symlink():
        # A valid second fetch is idempotent; edits or older packs are never overwritten.
        return verify_assets(directory, expected)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.diaggen-assets-', dir=directory.parent) as temporary:
        stage = Path(temporary) / 'assets'
        stage.mkdir()
        with zipfile.ZipFile(archive) as source:
            records = source.infolist()
            names = [r.filename for r in records]
            if len(names) != len(set(names)) or set(names) != set(expected):
                raise ValueError('Unexpected or duplicate archive members')
            for member in records:
                relative = safe_relative(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16) or member.is_dir():
                    raise ValueError('Only regular asset files may be extracted')
                if member.file_size != expected[member.filename]['size_bytes']:
                    raise ValueError('Archive member size differs from the manifest')
                path = stage / str(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as reader, path.open('xb') as writer:
                    shutil.copyfileobj(reader, writer)
        result = verify_assets(stage, expected)
        if directory.exists() or directory.is_symlink():
            raise ValueError('Output appeared during extraction; original output retained')
        stage.rename(directory)
        return result


def fetch_assets(directory, manifest, expected, archive=None):
    if Path(directory).exists() or Path(directory).is_symlink():
        return verify_assets(directory, expected)
    if archive is not None:
        return unpack_verified(archive, directory, manifest, expected)
    url = manifest['release']['url']
    if not url.startswith('https://github.com/wyattsheu/sim-forge/releases/download/'):
        raise ValueError('Expected this project\'s HTTPS GitHub Release URL')
    with tempfile.TemporaryDirectory(prefix='diaggen-download-') as temporary:
        pack = Path(temporary) / 'assets.zip'
        request = urllib.request.Request(url, headers={'User-Agent': 'sim-forge-shared-assets/1'})
        with urllib.request.urlopen(request, timeout=60) as reader, pack.open('xb') as writer:
            total = 0
            while chunk := reader.read(1024 * 1024):
                total += len(chunk)
                if total > manifest['release']['size_bytes']:
                    raise ValueError('Download exceeds the pinned asset pack size')
                writer.write(chunk)
        return unpack_verified(pack, directory, manifest, expected)


def inspect_asset(directory, asset):
    try:
        import numpy as np
    except ImportError as error:
        raise ValueError('inspect needs NumPy: python -m pip install numpy') from error
    path = Path(directory) / asset['id']
    text = (path / 'final_mesh.mesh').read_text(encoding='utf-8')
    tokens = iter(' '.join(line.split('#', 1)[0] for line in text.splitlines()).split())
    vertices, tets = None, None
    widths = {'Triangles': 4, 'Edges': 3}
    for keyword in tokens:
        if keyword in ('MeshVersionFormatted', 'Dimension'):
            next(tokens)
        elif keyword == 'Vertices':
            count = int(next(tokens))
            vertices = np.asarray([[float(next(tokens)) for _ in range(4)] for _ in range(count)])[:, :3]
        elif keyword == 'Tetrahedra':
            count = int(next(tokens))
            tets = np.asarray([[int(next(tokens)) for _ in range(5)] for _ in range(count)], dtype=np.int64)[:, :4] - 1
        elif keyword in widths:
            for _ in range(int(next(tokens)) * widths[keyword]):
                next(tokens)
        elif keyword == 'End':
            break
        else:
            raise ValueError('Unsupported Medit mesh section: ' + keyword)
    if vertices is None or tets is None or not len(vertices) or not len(tets):
        raise ValueError('Missing tetrahedral mesh')
    if not np.isfinite(vertices).all() or tets.min() < 0 or tets.max() >= len(vertices):
        raise ValueError('Invalid mesh coordinates or tetrahedron indices')
    with np.load(path / 'heterogeneous_params.npz', allow_pickle=False) as arrays:
        labels, density, elastic = [arrays[key] for key in ('tet_part_labels', 'tet_density', 'tet_E_nu')]
        if labels.shape != (len(tets),) or density.shape != (len(tets),) or elastic.shape != (len(tets), 2):
            raise ValueError('Material arrays and tetrahedron count disagree')
        if not np.isfinite(density).all() or not np.isfinite(elastic).all():
            raise ValueError('Nonfinite material parameters')
        if not (density > 0).all() or not (elastic[:, 0] > 0).all() or not ((elastic[:, 1] > -1) & (elastic[:, 1] < .5)).all():
            raise ValueError('Material parameters outside the native physical interval')
        points = vertices[tets]
        volume = np.abs(np.linalg.det(np.stack([points[:, i] - points[:, 0] for i in (1, 2, 3)], axis=1))) / 6
        if not (volume > 0).all():
            raise ValueError('Degenerate tetrahedron')
        material_labels = sorted(int(x) for x in np.unique(labels))
        if material_labels != sorted(int(x) for x in arrays['part_indices']):
            raise ValueError('Final material coverage differs from the indexed parts')
        mass_kg = float(np.sum(volume * density))
    glb = path / 'appearance/visual_mesh.glb'
    with glb.open('rb') as reader:
        magic, version, size = struct.unpack('<4sII', reader.read(12))
    if magic != b'glTF' or version != 2 or size != glb.stat().st_size:
        raise ValueError('Invalid GLB header')
    params = json.loads((path / 'inferred_params.json').read_text(encoding='utf-8'))
    return {'id': asset['id'], 'run_id': asset['run_id'], 'vertices': len(vertices), 'tetrahedra': len(tets),
            'bbox_extent_m': (vertices.max(axis=0) - vertices.min(axis=0)).tolist(),
            'computed_mass_kg_from_inferred_density': mass_kg, 'material_labels': material_labels,
            'materials': [{key: part.get(key) for key in ('part_index', 'part_name', 'major_material_name',
                          'youngs_modulus_pa', 'density_kg_m3', 'poisson_ratio', 'volume_fill_mode')}
                          for part in params['predictions']],
            'scope': 'CPU file/geometry/material consistency only; no new Genesis simulation or real-world calibration.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('fetch', 'verify', 'inspect'))
    parser.add_argument('--manifest', type=Path, default=HERE / 'assets_manifest.json')
    parser.add_argument('--output-dir', type=Path, default=HERE / 'assets')
    parser.add_argument('--archive', type=Path, help='Use an already downloaded pinned ZIP')
    parser.add_argument('--asset', help='Inspect one asset ID; default is all assets')
    args = parser.parse_args()
    manifest, expected = read_manifest(args.manifest)
    if args.command == 'fetch':
        result = fetch_assets(args.output_dir, manifest, expected, args.archive)
    else:
        result = verify_assets(args.output_dir, expected)
        if args.command == 'inspect':
            selected = [a for a in manifest['assets'] if args.asset is None or a['id'] == args.asset]
            if not selected:
                parser.error('Unknown asset ID')
            result['assets'] = [inspect_asset(args.output_dir, a) for a in selected]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
