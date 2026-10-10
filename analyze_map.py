"""Extract spatial evidence from a Source 2 map without loading its mesh arrays."""
import argparse
from collections import Counter
import html
import itertools
import json
import math
from pathlib import Path
import re
import struct
import tempfile

from catalog import inspect_stream
from hammergpt import convert, get, parse, walk

QUOTE = r'"((?:\\.|[^"\\])*)"'
DECLARATION = re.compile(QUOTE + r'(?:\s+' + QUOTE + r')?\s*$')
SCALAR = re.compile(QUOTE + r'\s+' + QUOTE + r'\s+' + QUOTE + r'\s*$')
ANCHORS = {'info_player_terrorist', 'info_player_counterterrorist', 'func_bomb_target', 'func_buyzone', 'info_hostage_spawn', 'hostage_entity', 'func_hostage_rescue', 'env_cs_place'}


def transform(point, frame):
    scale = frame.get('scales', [1, 1, 1])
    x, y, z = [point[i] * scale[i] for i in range(3)]
    pitch, yaw, roll = [math.radians(v) for v in frame.get('angles', [0, 0, 0])]
    y, z = y * math.cos(roll) - z * math.sin(roll), y * math.sin(roll) + z * math.cos(roll)
    x, z = x * math.cos(pitch) + z * math.sin(pitch), -x * math.sin(pitch) + z * math.cos(pitch)
    x, y = x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)
    origin = frame.get('origin', [0, 0, 0])
    return [x + origin[0], y + origin[1], z + origin[2]]


def world_point(point, frame):
    # Hammer node transforms are authored in world space. Parent references
    # express ownership/grouping; applying their offsets again moves volumes twice.
    return transform(point, frame) if frame else list(point)


def bounds(points):
    return {'min': [min(p[i] for p in points) for i in range(3)], 'max': [max(p[i] for p in points) for i in range(3)]}


class SpatialScanner:
    def __init__(self):
        self.stack = []
        self.pending = None
        self.meshes = []
        self.entities = []
        self.prefabs = []
        self.materials = Counter()
        self.vertices = 0
        self.nodes = []

    def feed(self, raw):
        line = raw.strip()
        if line == '{':
            name, kind = self.pending or ('', '')
            parent = next((s for s in reversed(self.stack) if s['kind'].startswith('CMap')), None)
            frame = {'name': name, 'kind': kind, 'parent': parent}
            if kind.startswith('CMap'):
                self.nodes.append(frame)
            if kind == 'CMapMesh':
                frame.update(low=[math.inf] * 3, high=[-math.inf] * 3, vertex_count=0)
            self.stack.append(frame)
            self.pending = None
            return
        if line.rstrip(',') == '}':
            frame = self.stack.pop()
            kind = frame['kind']
            if kind == 'CMapMesh':
                self.meshes.append(frame)
            elif kind == 'CMapEntity':
                self.entities.append(frame)
            elif kind == 'CMapPrefab':
                self.prefabs.append(frame)
            elif frame['name'] == 'entity_properties' and self.stack:
                self.stack[-1]['properties'] = frame.get('properties', {})
            return
        if not self.stack:
            match = DECLARATION.fullmatch(line)
            if match:
                a, b = match.groups()
                self.pending = (a, b or a)
            return
        frame = self.stack[-1]
        if line == ']':
            frame['reading_positions'] = False
            frame['reading_children'] = False
            return
        if line == '[':
            if self.pending and self.pending == ('children', 'element_array') and frame['kind'].startswith('CMap'):
                frame['reading_children'] = True
            if self.pending and self.pending[0] == 'data' and frame.get('is_position'):
                frame['position_mesh'] = next((s for s in reversed(self.stack) if s['kind'] == 'CMapMesh'), None)
                frame['reading_positions'] = frame['position_mesh'] is not None
            return
        if frame.get('reading_positions') and line.startswith('"'):
            point = [float(v) for v in line.rstrip(',')[1:-1].split()]
            if len(point) != 3 or not all(math.isfinite(v) for v in point):
                raise ValueError('Invalid mesh position')
            mesh = frame['position_mesh']
            for i in range(3):
                mesh['low'][i] = min(mesh['low'][i], point[i])
                mesh['high'][i] = max(mesh['high'][i], point[i])
            mesh['vertex_count'] += 1
            self.vertices += 1
            return
        if not line.startswith('"'):
            return
        match = DECLARATION.fullmatch(line.rstrip(','))
        if match:
            a, b = match.groups()
            if frame.get('reading_children') and a == 'element' and b:
                frame.setdefault('child_refs', []).append(b)
                return
            self.pending = (a, b or a)
            if b is None and a.lower().endswith('.vmat'):
                self.materials[a] += 1
            return
        match = SCALAR.fullmatch(line)
        if not match:
            return
        name, typ, value = match.groups()
        if name == 'semanticName' and value == 'position':
            frame['is_position'] = True
        if frame['kind'].startswith('CMap'):
            if name in ('origin', 'angles', 'scales') and typ in ('vector3', 'qangle'):
                frame[name] = list(map(float, value.split()))
            elif name in ('id', 'nodeID', 'force_hidden', 'editorOnly'):
                frame[name] = value
        if frame['name'] == 'entity_properties' and name != 'id':
            frame.setdefault('properties', {})[name] = value
        if value.lower().endswith('.vmat'):
            self.materials[value] += 1

    def finish(self):
        if self.stack:
            raise ValueError('Unclosed spatial element')
        by_id = {n['id']: n for n in self.nodes if 'id' in n}
        references = {}
        for node in self.nodes:
            if 'nodeID' not in node:
                # Selection sets reference geometry for UI organization, not parenting.
                continue
            for child in node.get('child_refs', []):
                references.setdefault(child, []).append(node)
        ambiguous = 0
        for child, parents in references.items():
            if child not in by_id:
                continue
            if len(parents) == 1:
                by_id[child]['parent'] = parents[0]
            else:
                ambiguous += 1
        meshes = []
        for mesh in self.meshes:
            if not mesh['vertex_count']:
                continue
            corners = itertools.product(*zip(mesh['low'], mesh['high']))
            box = bounds([world_point(p, mesh) for p in corners])
            owner = mesh.get('parent')
            while owner and owner['kind'] != 'CMapEntity':
                owner = owner.get('parent')
            meshes.append({'node_id': mesh.get('nodeID', ''), 'vertex_count': mesh['vertex_count'], 'bounds': box,
                           'owner_entity': owner.get('nodeID', '') if owner else None,
                           'editor_only': mesh.get('editorOnly', '0') == '1', 'hidden': mesh.get('force_hidden', '0') == '1'})
        entities = [{'node_id': e.get('nodeID', ''), 'classname': e.get('properties', {}).get('classname', ''),
                     'position': world_point([0, 0, 0], e), 'properties': e.get('properties', {})} for e in self.entities]
        anchors = []
        for entity in entities:
            if entity['classname'] in ANCHORS:
                record = dict(entity)
                owned = [m for m in meshes if m['owner_entity'] == entity['node_id']]
                record['geometry_bounds'] = bounds([p for m in owned for p in (m['bounds']['min'], m['bounds']['max'])]) if owned else None
                anchors.append(record)
        all_bounds = bounds([p for m in meshes for p in (m['bounds']['min'], m['bounds']['max'])]) if meshes else None
        return {'mesh_count': len(meshes), 'vertex_count': self.vertices, 'mesh_bounds': all_bounds,
                'prefab_instances_not_expanded': len(self.prefabs), 'ambiguous_shared_node_parents': ambiguous, 'meshes': meshes, 'entities': entities,
                'gameplay_anchors': anchors, 'material_references': dict(self.materials.most_common())}


def vpk_paths(path):
    """Read directory entries only; never unpack or change game files."""
    with path.open('rb') as file:
        magic, version, length = struct.unpack('<III', file.read(12))
        if magic != 0x55AA1234 or version not in (1, 2):
            raise ValueError(f'Unsupported VPK directory: {path}')
        if version == 2:
            file.read(16)
        tree = file.read(length)
    offset = 0
    def string():
        nonlocal offset
        end = tree.index(b'\0', offset)
        value = tree[offset:end].decode('utf-8')
        offset = end + 1
        return value
    while True:
        ext = string()
        if not ext:
            break
        while True:
            folder = string()
            if not folder:
                break
            while True:
                name = string()
                if not name:
                    break
                _, preload, _, _, _, terminator = struct.unpack_from('<IHHIIH', tree, offset)
                if terminator != 0xFFFF:
                    raise ValueError('Invalid VPK entry terminator')
                offset += 18 + preload
                yield ((folder + '/' if folder != ' ' else '') + name + '.' + ext).lower()


def audit_assets(assets, cs2, addon):
    roots = [addon, cs2 / 'content/csgo', cs2 / 'content/core', cs2 / 'game/csgo_addons' / addon.name, cs2 / 'game/csgo', cs2 / 'game/core']
    packed = set()
    archives, archive_errors = [], []
    for root in roots[3:]:
        for archive in root.glob('*_dir.vpk'):
            try:
                packed.update(vpk_paths(archive))
                archives.append(str(archive))
            except (OSError, ValueError, struct.error) as error:
                archive_errors.append({'path': str(archive), 'error': str(error)})
    counts = Counter()
    results = []
    for asset in assets:
        normalized = asset.replace('\\', '/')
        if normalized.startswith('/') or '..' in normalized.split('/'):
            status = 'invalid_relative_path'
        elif any((root / normalized).is_file() for root in roots):
            status = 'source_or_loose_asset'
        elif any((root / (normalized + '_c')).is_file() for root in roots) or (normalized.lower() + '_c') in packed:
            status = 'compiled_asset_available'
        else:
            status = 'unresolved_in_checked_mounts'
        counts[status] += 1
        results.append({'asset': asset, 'status': status})
    return {'counts': dict(counts), 'checked_roots': list(map(str, roots)), 'vpk_directories': archives, 'archive_errors': archive_errors, 'references': results}


def resolve_anchor_hulls(spatial, frames, cs2, addon, temp):
    """Recover decompiled physics volumes when their model transforms are identity."""
    roots = [addon, cs2 / 'content/csgo']
    by_id = {f.get('nodeID'): f for f in frames}
    exe = cs2 / 'game/bin/win64/dmxconvert.exe'
    for index, anchor in enumerate(spatial['gameplay_anchors']):
        if anchor['geometry_bounds'] or anchor['classname'].startswith('info_'):
            continue
        model = anchor['properties'].get('model', '')
        if not model or '..' in model.split('/') or model.startswith('/'):
            continue
        source = next((r / model for r in roots if (r / model).is_file()), None)
        if source is None:
            continue
        points, failure = [], None
        for filename in re.findall(r'filename\s*=\s*"([^"]+\.dmx)"', source.read_text(encoding='utf-8-sig')):
            if '..' in filename.split('/') or filename.startswith('/'):
                continue
            hull = next((r / filename for r in roots if (r / filename).is_file()), None)
            if hull is None:
                failure = 'Referenced DMX hull is missing'
                break
            converted = temp / f'hull-{index}-{len(points)}.txt'
            try:
                convert(exe, hull, converted, 'keyvalues2')
                _, elements = parse(converted.read_text(encoding='utf-8-sig'))
                for root in elements:
                    for node in walk(root):
                        if node.kind == 'DmeTransform':
                            position = list(map(float, get(node, 'position').split()))
                            orientation = list(map(float, get(node, 'orientation').split()))
                            if position != [0, 0, 0] or orientation != [0, 0, 0, 1]:
                                raise ValueError('Non-identity model skeleton transform is not yet supported')
                        if node.kind == 'DmeVertexData':
                            for name, (typ, value) in node.attrs.items():
                                if name.startswith('position$') and typ == 'vector3_array':
                                    points.extend(world_point(list(map(float, p.split())), by_id[anchor['node_id']]) for p in value)
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                failure = str(error)
                break
        if points and failure is None:
            anchor['geometry_bounds'] = bounds(points)
            anchor['bounds_source'] = 'decompiled_model_dmx_hulls'
        elif failure:
            anchor['bounds_error'] = failure


def overview(spatial):
    # Bounds show mesh extents, not walkable floors or unobstructed routes.
    box = spatial['mesh_bounds']
    if box is None:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'
    low, high = box['min'], box['max']
    factor = 900 / max(high[0] - low[0], high[1] - low[1], 1)
    def xy(point):
        return 50 + (point[0] - low[0]) * factor, 950 - (point[1] - low[1]) * factor
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1040" viewBox="0 0 1000 1040">', '<rect width="1000" height="1040" fill="#111827"/>', '<text x="40" y="28" fill="white" font-family="sans-serif">Mesh extents and gameplay anchors — not a navigation map</text>']
    for mesh in spatial['meshes']:
        b = mesh['bounds']
        x, y = xy([b['min'][0], b['max'][1]])
        w, h = [(b['max'][i] - b['min'][i]) * factor for i in (0, 1)]
        lines.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#64748b" fill-opacity=".025" stroke="#94a3b8" stroke-opacity=".12" stroke-width=".4"/>')
    for anchor in spatial['gameplay_anchors']:
        p = anchor['position']
        if anchor['geometry_bounds']:
            b = anchor['geometry_bounds']
            p = [(b['min'][i] + b['max'][i]) / 2 for i in range(3)]
        x, y = xy(p)
        cls = anchor['classname']
        color = '#60a5fa' if cls == 'info_player_counterterrorist' else '#fb923c' if cls == 'info_player_terrorist' else '#facc15'
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"><title>{html.escape(cls)} {html.escape(anchor["node_id"])}</title></circle>')
    lines.extend(['<text x="40" y="1015" fill="white" font-family="sans-serif">Blue: CT spawns · Orange: T spawns · Yellow: objective / buy volumes</text>', '</svg>'])
    return '\n'.join(lines)


def report(data):
    spatial, inventory, audit = data['spatial'], data['inventory'], data['asset_audit']
    lines = ['# Map analysis: ' + Path(data['source']).name, '',
             f"Extracted {spatial['mesh_count']} meshes, {spatial['vertex_count']} vertices, {sum(e['count'] for e in inventory['entities'].values())} entities, and {len(inventory['assets'])} unique asset references.", '',
             'This report extracts map evidence; running analysis does not train a model. Mesh bounding boxes do not establish room boundaries, walkability, sightlines, cover effectiveness, or gameplay balance. Decompilation may have merged geometry and lost original groups.', '',
             f"Unexpanded prefab instances: {spatial['prefab_instances_not_expanded']}. Prop positions are included, but prop model geometry is not included in mesh bounds. Objective and named-area volumes use local decompiled DMX hulls where supported.", '',
             '## Asset resolution', '', '| Status | References |', '| --- | ---: |']
    lines.extend(f'| {k} | {v} |' for k, v in audit['counts'].items())
    lines.extend(['', 'Only addon, CS2/core source and game mounts, and their readable VPK directories are checked. Unresolved references are candidates for repair, not proof of a broken map.', '', '## Gameplay anchors', '', '| Class | Count |', '| --- | ---: |'])
    lines.extend(f'| `{k}` | {v} |' for k, v in sorted(Counter(e['classname'] for e in spatial['gameplay_anchors']).items()))
    places = Counter(e['properties'].get('place_name', '(unnamed)') for e in spatial['gameplay_anchors'] if e['classname'] == 'env_cs_place')
    lines.extend(['', '## Named areas', '', ', '.join(sorted(places)), '', f"Located volume bounds for {sum(a['geometry_bounds'] is not None for a in spatial['gameplay_anchors'])} gameplay/area anchors."])
    lines.extend(['', '## Entity classes', '', '| Class | Count |', '| --- | ---: |'])
    lines.extend(f"| `{k}` | {v['count']} |" for k, v in inventory['entities'].items())
    lines.extend(['', '## Most referenced materials', '', '| Material | References |', '| --- | ---: |'])
    lines.extend(f'| `{k}` | {v} |' for k, v in list(spatial['material_references'].items())[:20])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2', required=True, type=Path)
    parser.add_argument('--addon', required=True, type=Path)
    parser.add_argument('--map', required=True, type=Path)
    parser.add_argument('--text', type=Path, help='Previously converted KeyValues2 map; avoids conversion')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix != '.json' or any(args.output.with_suffix(s).exists() for s in ('.json', '.md', '.svg')):
        parser.error('Output must be a new .json path without existing report files')
    if not args.map.is_file() or not args.addon.is_dir():
        parser.error('Map or addon does not exist')
    with tempfile.TemporaryDirectory(prefix='hammergpt-analysis-') as temp:
        text = args.text or Path(temp) / 'map.txt'
        if not args.text:
            convert(args.cs2 / 'game/bin/win64/dmxconvert.exe', args.map, text, 'keyvalues2')
        scanner = SpatialScanner()
        def lines():
            with text.open(encoding='utf-8-sig') as file:
                for line in file:
                    scanner.feed(line)
                    yield line
        print('Scanning geometry, entities, and assets...', flush=True)
        inventory = inspect_stream(lines(), str(args.map))
        spatial = scanner.finish()
        print('Resolving objective and named-area collision hulls...', flush=True)
        resolve_anchor_hulls(spatial, scanner.entities, args.cs2, args.addon, Path(temp))
        print('Checking asset mounts and VPK directories...', flush=True)
        audit = audit_assets(inventory['assets'], args.cs2, args.addon)
    data = {'schema_version': 1, 'source': str(args.map), 'source_size_bytes': args.map.stat().st_size,
            'inventory': inventory, 'spatial': spatial, 'asset_audit': audit}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2), encoding='utf-8')
    args.output.with_suffix('.md').write_text(report(data), encoding='utf-8')
    args.output.with_suffix('.svg').write_text(overview(spatial), encoding='utf-8')
    print(json.dumps({'meshes': spatial['mesh_count'], 'vertices': spatial['vertex_count'], 'entity_classes': len(inventory['entities']), 'asset_resolution': audit['counts'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
