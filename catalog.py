"""Inventory entity examples and asset references in installed CS2 source maps."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tempfile

from hammergpt import Element, convert, get, walk


ASSET_SUFFIXES = ('.vmdl', '.vmat', '.vsmart', '.vpcf', '.vmap', '.vsnd', '.vtex', '.js')


def inspect_stream(lines, source):
    """Scan converter text with bounded memory, skipping geometry data arrays."""
    quoted = r'"((?:\\.|[^"\\])*)"'
    declaration = re.compile(quoted + r'(?:\s+' + quoted + r')?\s*$')
    scalar = re.compile(quoted + r'\s+' + quoted + r'\s+' + quoted + r'\s*$')
    kinds, classes, assets = Counter(), {}, set()
    stack = []
    pending = None
    entity = None
    def finish(record):
        classname = record['properties'].get('classname')
        if not classname:
            return
        entry = classes.setdefault(classname, {'count': 0, 'property_names': set(), 'examples': []})
        entry['count'] += 1
        entry['property_names'].update(record['properties'])
        if len(entry['examples']) < 3:
            entry['examples'].append(record)
    for raw in lines:
        line = raw.strip()
        if line == '{':
            name, kind = pending or ('', '')
            kinds[kind] += 1
            if kind == 'CMapEntity':
                record = {'node_id': '', 'origin': '', 'properties': {}}
                stack.append((name, kind, entity))
                entity = record
            else:
                stack.append((name, kind, None))
            pending = None
            continue
        if line.rstrip(',') == '}':
            if not stack:
                raise ValueError('Unbalanced map element')
            _, kind, previous = stack.pop()
            if kind == 'CMapEntity':
                finish(entity)
                entity = previous
            continue
        if not line.startswith('"'):
            continue
        # Only declarations (one/two strings) are needed outside entity properties.
        match = declaration.fullmatch(line)
        if match:
            name, typ = match.groups()
            pending = (name, typ or name)
        if any(suffix in line.lower() for suffix in ASSET_SUFFIXES):
            values = re.findall(quoted, line)
            for value in values:
                if value.lower().endswith(ASSET_SUFFIXES):
                    assets.add(value.replace('\\\\', '/').replace('\\', '/'))
        if entity is None or not stack:
            continue
        name, kind, _ = stack[-1]
        if kind == 'CMapEntity' or name == 'entity_properties':
            match = scalar.fullmatch(line)
            if match:
                key, typ, value = match.groups()
                value = value.replace('\\"', '"').replace('\\\\', '\\')
                if name == 'entity_properties' and key != 'id':
                    entity['properties'][key] = value
                elif kind == 'CMapEntity' and key in ('nodeID', 'origin'):
                    entity['node_id' if key == 'nodeID' else 'origin'] = value
    if stack:
        raise ValueError('Unclosed map element')
    for entry in classes.values():
        entry['property_names'] = sorted(entry['property_names'])
    return {'source': source, 'node_types': dict(sorted(kinds.items())), 'entities': dict(sorted(classes.items())), 'assets': sorted(assets)}


def inspect_map(roots, source):
    """Describe examples without interpreting their values as entity defaults."""
    kinds = Counter()
    classes = {}
    assets = set()
    for root in roots:
        for node in walk(root):
            kinds[node.kind] += 1
            for _, value in node.attrs.values():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str) and item.lower().endswith(ASSET_SUFFIXES):
                        assets.add(item.replace('\\', '/'))
            if node.kind != 'CMapEntity':
                continue
            props = node.attrs.get('entity_properties', (None, None))[1]
            if not isinstance(props, Element) or 'classname' not in props.attrs:
                continue
            classname = get(props, 'classname')
            entry = classes.setdefault(classname, {'count': 0, 'property_names': set(), 'examples': []})
            entry['count'] += 1
            entry['property_names'].update(props.attrs.keys() - {'id'})
            if len(entry['examples']) < 3:
                entry['examples'].append({
                    'node_id': node.attrs.get('nodeID', (None, ''))[1],
                    'origin': node.attrs.get('origin', (None, ''))[1],
                    'properties': {name: value for name, (_, value) in props.attrs.items() if isinstance(value, str) and name != 'id'},
                    'connection_count': len(node.attrs.get('connectionsData', (None, []))[1]),
                })
    for entry in classes.values():
        entry['property_names'] = sorted(entry['property_names'])
    return {'source': source, 'node_types': dict(sorted(kinds.items())), 'entities': dict(sorted(classes.items())), 'assets': sorted(assets)}


def combine(maps, errors):
    classes = {}
    assets = set()
    for record in maps:
        assets.update(record['assets'])
        for classname, entry in record['entities'].items():
            result = classes.setdefault(classname, {'count': 0, 'maps': [], 'property_names': set()})
            result['count'] += entry['count']
            result['maps'].append(record['source'])
            result['property_names'].update(entry['property_names'])
    for entry in classes.values():
        entry['property_names'] = sorted(entry['property_names'])
    return {'schema_version': 1, 'note': 'Observed map examples, not a complete entity API or defaults. Prefab references are listed but not expanded.',
            'summary': {'maps_scanned': len(maps), 'maps_failed': len(errors), 'entity_classes': len(classes), 'entity_instances': sum(e['count'] for e in classes.values()), 'asset_references': len(assets)},
            'entity_classes': dict(sorted(classes.items())), 'assets': sorted(assets), 'maps': maps, 'errors': errors}


def report(catalog):
    summary = catalog['summary']
    lines = ['# Installed CS2 map catalog', '', catalog['note'], '',
             f"Scanned {summary['maps_scanned']} maps; {summary['maps_failed']} failures. Found {summary['entity_instances']} entity instances across {summary['entity_classes']} classes and {summary['asset_references']} unique asset references.", '',
             '| Entity class | Instances | Example maps |', '| --- | ---: | --- |']
    for name, entry in catalog['entity_classes'].items():
        lines.append(f"| `{name}` | {entry['count']} | {', '.join(Path(p).name for p in entry['maps'])} |")
    lines.extend(['', '## Sources', ''])
    for record in catalog['maps']:
        lines.append(f"- `{record['source']}`")
    if catalog['errors']:
        lines.extend(['', '## Failed sources', ''])
        for error in catalog['errors']:
            lines.append(f"- `{error['source']}`: {error['error']}")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2', required=True, type=Path)
    parser.add_argument('--map', action='append', type=Path, help='Explicit source map; repeat to scan several')
    parser.add_argument('--output', type=Path, default=Path('output/catalog.json'))
    args = parser.parse_args()
    exe = args.cs2 / 'game/bin/win64/dmxconvert.exe'
    if not exe.is_file():
        parser.error('CS2 dmxconvert.exe not found')
    sources = args.map
    if not sources:
        content = args.cs2 / 'content'
        sources = sorted((content / 'csgo/maps/editor/zoo').glob('*.vmap'))
        sources += sorted((content / 'csgo/maps/templates').glob('*.vmap'))
        sources += sorted((content / 'csgo_addons/cs_script_demo/maps').rglob('*.vmap'))
    if not sources:
        parser.error('No example maps found')
    if args.output.suffix.lower() != '.json' or args.output.exists() or args.output.with_suffix('.md').exists():
        parser.error('Output must be a new .json path with no existing sibling .md report')
    maps, errors = [], []
    with tempfile.TemporaryDirectory(prefix='hammergpt-catalog-') as temp:
        for i, source in enumerate(sources):
            print(f'[{i + 1}/{len(sources)}] {source.name}', flush=True)
            try:
                output = Path(temp) / f'{i}.txt'
                convert(exe, source, output, 'keyvalues2')
                try:
                    label = source.relative_to(args.cs2).as_posix()
                except ValueError:
                    label = str(source)
                with output.open(encoding='utf-8-sig') as text:
                    maps.append(inspect_stream(text, label))
            except (OSError, ValueError, RuntimeError, IndexError) as error:
                errors.append({'source': str(source), 'error': str(error)})
    catalog = combine(maps, errors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as destination:
        json.dump(catalog, destination, indent=2)
    with args.output.with_suffix('.md').open('x', encoding='utf-8') as destination:
        destination.write(report(catalog))
    print(json.dumps(catalog['summary']))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
