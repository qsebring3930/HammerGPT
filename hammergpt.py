"""Create editable Source 2 room maps using a saved Hammer cube as a template.

Standard-library only. Valve's dmxconvert performs binary/text conversion.
"""
import argparse
import copy
import json
import math
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Element:
    kind: str
    attrs: dict


def parse(text):
    """Read the typed, nested KeyValues2 representation emitted by dmxconvert."""
    header, body = text.split('\n', 1)
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}\[\],]', body)
    pos = 0

    def take():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError('Unexpected end of KeyValues2')
        value = tokens[pos]
        pos += 1
        return value

    def string():
        value = take()
        if not value.startswith('"'):
            raise ValueError(f'Expected quoted string, got {value}')
        return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    def element(kind):
        if take() != '{':
            raise ValueError('Expected element body')
        attrs = {}
        while tokens[pos] != '}':
            name, typ = string(), string()
            if typ.endswith('_array'):
                if take() != '[':
                    raise ValueError('Expected array')
                values = []
                while tokens[pos] != ']':
                    value = string()
                    if typ == 'element_array':
                        if tokens[pos] == '{':
                            value = element(value)
                        elif value == 'element':
                            value = string()
                    values.append(value)
                    if tokens[pos] == ',':
                        take()
                take()
                attrs[name] = (typ, values)
            elif tokens[pos] == '{':
                attrs[name] = (typ, element(typ))
            else:
                attrs[name] = (typ, string())
        take()
        return Element(kind, attrs)

    roots = []
    while pos < len(tokens):
        roots.append(element(string()))
    return header, roots


def serialize(header, roots):
    def quote(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'

    def body(node, depth):
        indent = '\t' * depth
        lines = [indent + '{']
        for name, (typ, value) in node.attrs.items():
            lead = indent + '\t' + quote(name) + ' ' + quote(typ)
            if isinstance(value, Element):
                lines.append(lead)
                lines.extend(body(value, depth + 1))
            elif isinstance(value, list):
                lines.extend([lead, indent + '\t['])
                for index, item in enumerate(value):
                    comma = ',' if index < len(value) - 1 else ''
                    if isinstance(item, Element):
                        lines.append(indent + '\t\t' + quote(item.kind))
                        section = body(item, depth + 2)
                        section[-1] += comma
                        lines.extend(section)
                    else:
                        prefix = quote('element') + ' ' if typ == 'element_array' else ''
                        lines.append(indent + '\t\t' + prefix + quote(item) + comma)
                lines.append(indent + '\t]')
            else:
                lines.append(lead + ' ' + quote(value))
        lines.append(indent + '}')
        return lines

    lines = [header]
    for root in roots:
        lines.append(quote(root.kind))
        lines.extend(body(root, 0))
    return '\n'.join(lines) + '\n'


def walk(node):
    yield node
    for _, value in node.attrs.values():
        if isinstance(value, Element):
            yield from walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Element):
                    yield from walk(item)


def get(node, key):
    return node.attrs[key][1]


def set_value(node, key, value):
    node.attrs[key] = (node.attrs[key][0], value)


def vector(values):
    return ' '.join(f'{v:.8g}' for v in values)


def positions(mesh):
    data = get(get(mesh, 'meshData'), 'vertexData')
    return next(s for s in get(data, 'streams') if get(s, 'semanticName') == 'position')


def fresh_copy(template, node_id):
    result = copy.deepcopy(template)
    elements = list(walk(result))
    ids = {get(e, 'id'): str(uuid.uuid4()) for e in elements if 'id' in e.attrs}
    for e in elements:
        for name, (typ, value) in list(e.attrs.items()):
            if typ in ('elementid', 'element') and isinstance(value, str) and value in ids:
                set_value(e, name, ids[value])
            elif typ == 'element_array':
                set_value(e, name, [ids.get(v, v) if isinstance(v, str) else v for v in value])
    set_value(result, 'nodeID', str(node_id))
    set_value(result, 'referenceID', hex(uuid.uuid4().int & ((1 << 64) - 1)))
    return result


def make_box(template, node_id, center, size):
    mesh = fresh_copy(template, node_id)
    points = [list(map(float, p.split())) for p in get(positions(mesh), 'data')]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    if len(points) != 8 or any(high[i] <= low[i] for i in range(3)):
        raise ValueError('Reference mesh must be a non-degenerate, eight-vertex box')
    if any(any(min(abs(p[i] - low[i]), abs(p[i] - high[i])) > 0.001 for i in range(3)) for p in points):
        raise ValueError('Reference mesh must be an axis-aligned box')
    set_value(positions(mesh), 'data', [vector([(p[i] - low[i]) / (high[i] - low[i]) * size[i] - size[i] / 2 for i in range(3)]) for p in points])
    set_value(mesh, 'origin', vector(center))
    set_value(mesh, 'angles', '0 0 0')
    set_value(mesh, 'scales', '1 1 1')
    return mesh


def create_room(roots, width=512, depth=512, height=256, thickness=16):
    if any(not math.isfinite(v) or v <= 0 or v > 16384 for v in (width, depth, height, thickness)):
        raise ValueError('Dimensions must be finite and between 0 and 16384 Hammer units')
    if thickness >= min(width, depth, height) / 2:
        raise ValueError('Wall thickness must be less than half the smallest room dimension')
    result = copy.deepcopy(roots)
    root = next(r for r in result if r.kind == 'CMapRootElement')
    world = get(root, 'world')
    nodes = list(walk(world))
    cube = next((n for n in nodes if n.kind == 'CMapMesh'), None)
    light = next((n for n in nodes if n.kind == 'CMapEntity' and get(get(n, 'entity_properties'), 'classname') == 'light_omni2'), None)
    if cube is None or light is None:
        raise ValueError('Save a cube and a light_omni2 in the reference map first')
    if get(cube, 'angles') != '0 0 0' or get(cube, 'scales') != '1 1 1':
        raise ValueError('Reference cube must have zero rotation and unit scale')
    first_id = max(int(get(n, 'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs) + 1
    boxes = [
        ((0, 0, -thickness / 2), (width + 2 * thickness, depth + 2 * thickness, thickness)),
        ((0, 0, height + thickness / 2), (width + 2 * thickness, depth + 2 * thickness, thickness)),
        ((-width / 2 - thickness / 2, 0, height / 2), (thickness, depth + 2 * thickness, height)),
        ((width / 2 + thickness / 2, 0, height / 2), (thickness, depth + 2 * thickness, height)),
        ((0, -depth / 2 - thickness / 2, height / 2), (width, thickness, height)),
        ((0, depth / 2 + thickness / 2, height / 2), (width, thickness, height)),
    ]
    children = [make_box(cube, first_id + i, center, size) for i, (center, size) in enumerate(boxes)]
    lamp = fresh_copy(light, first_id + 6)
    set_value(lamp, 'origin', vector((0, 0, height * .75)))
    set_value(lamp, 'angles', '0 0 0')
    props = get(lamp, 'entity_properties')
    set_value(props, 'targetname', 'hammergpt_room_light')
    set_value(props, 'range', str(max(width, depth, height) * 2))
    children.append(lamp)
    # Separate output map: replace world contents; retain world settings and editor metadata.
    set_value(world, 'children', children)
    camera = get(root, 'defaultcamera')
    set_value(camera, 'position', vector((width * .3, -depth * .3, height * .5)))
    set_value(camera, 'lookat', vector((0, 0, height * .4)))
    return result


def convert(exe, source, output, encoding):
    completed = subprocess.run([str(exe), '-i', str(source), '-o', str(output), '-oe', encoding], capture_output=True, text=True)
    if completed.returncode or not output.is_file():
        raise RuntimeError(completed.stdout + completed.stderr)


def add_prop(roots, model, origin, angles=(0, 0, 0), scale=1):
    """Append a static model while retaining all existing map contents."""
    if not model.startswith('models/') or not model.endswith('.vmdl') or '..' in model.split('/'):
        raise ValueError('Model must be a relative models/... .vmdl asset path')
    if len(origin) != 3 or len(angles) != 3 or any(not math.isfinite(v) for v in (*origin, *angles, scale)) or scale <= 0:
        raise ValueError('Position/angles must be finite triples and scale must be positive')
    result = copy.deepcopy(roots)
    root = next(r for r in result if r.kind == 'CMapRootElement')
    world = get(root, 'world')
    nodes = [n for r in result for n in walk(r)]
    template = next((n for n in walk(world) if n.kind == 'CMapEntity' and not get(n, 'children')), None)
    if template is None:
        raise ValueError('Input map needs an existing leaf entity as an editor template')
    node_id = max(int(get(n, 'nodeID')) for n in nodes if 'nodeID' in n.attrs) + 1
    prop = fresh_copy(template, node_id)
    set_value(prop, 'origin', vector(origin))
    set_value(prop, 'angles', vector(angles))
    set_value(prop, 'scales', vector((scale, scale, scale)))
    prop.attrs['entity_properties'] = ('EditGameClassProps', Element('EditGameClassProps', {
        'id': ('elementid', str(uuid.uuid4())),
        'classname': ('string', 'prop_static'),
        'model': ('string', model),
        'rendercolor': ('string', '255 255 255'),
        'solid': ('string', '6'),
    }))
    if 'connectionsData' in prop.attrs:
        set_value(prop, 'connectionsData', [])
    if 'variableTargetKeys' in prop.attrs:
        set_value(prop, 'variableTargetKeys', [])
    if 'variableNames' in prop.attrs:
        set_value(prop, 'variableNames', [])
    if 'transformPin' in prop.attrs:
        pin = get(prop, 'transformPin')
        set_value(pin, 'targetReferenceID', '0x0')
        set_value(pin, 'referenceName', '')
    for key in ('force_hidden', 'editorOnly', 'transformLocked'):
        if key in prop.attrs:
            set_value(prop, key, '0')
    get(world, 'children').append(prop)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2', type=Path, required=True, help='CS2 installation directory')
    parser.add_argument('--reference', type=Path, required=True, help='Saved map containing a cube and omni light')
    parser.add_argument('--output', type=Path, required=True, help='New .vmap path; existing files are refused')
    for name, default in [('width', 512), ('depth', 512), ('height', 256), ('thickness', 16)]:
        parser.add_argument('--' + name, type=float, default=default)
    args = parser.parse_args()
    exe = args.cs2 / 'game/bin/win64/dmxconvert.exe'
    output = args.output.resolve()
    if output.suffix.lower() != '.vmap' or output.exists():
        parser.error('Output must be a new .vmap file')
    if not exe.is_file() or not args.reference.is_file():
        parser.error('CS2 dmxconvert.exe or reference map does not exist')
    with tempfile.TemporaryDirectory(prefix='hammergpt-') as temp:
        temp = Path(temp)
        source, generated, binary = temp / 'reference.txt', temp / 'room.txt', temp / 'room.vmap'
        convert(exe, args.reference, source, 'keyvalues2')
        header, roots = parse(source.read_text(encoding='utf-8-sig'))
        room = create_room(roots, args.width, args.depth, args.height, args.thickness)
        generated.write_text(serialize(header, room), encoding='utf-8')
        convert(exe, generated, binary, 'binary')
        # Verify Valve can read the produced binary before publishing the new file.
        check = temp / 'check.txt'
        convert(exe, binary, check, 'keyvalues2')
        _, checked = parse(check.read_text(encoding='utf-8-sig'))
        world = get(next(r for r in checked if r.kind == 'CMapRootElement'), 'world')
        if len(get(world, 'children')) != 7:
            raise RuntimeError('Converted map failed the room object count check')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as destination:
            destination.write(binary.read_bytes())
    print(json.dumps({'output': str(output), 'meshes': 6, 'lights': 1, 'interior': [args.width, args.depth, args.height]}))


if __name__ == '__main__':
    main()
