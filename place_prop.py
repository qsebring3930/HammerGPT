"""Append a catalogued model to a new copy of a Hammer map."""
import argparse
import json
from pathlib import Path
import tempfile

from hammergpt import add_prop, convert, get, parse, serialize, walk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=Path('output/catalog.json'))
    parser.add_argument('--model', required=True)
    parser.add_argument('--position', nargs=3, type=float, required=True, metavar=('X', 'Y', 'Z'))
    parser.add_argument('--angles', nargs=3, type=float, default=[0, 0, 0])
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    exe = args.cs2 / 'game/bin/win64/dmxconvert.exe'
    output = args.output.resolve()
    if output.suffix.lower() != '.vmap' or output.exists():
        parser.error('Output must be a new .vmap path')
    if not args.input.is_file() or not exe.is_file() or not args.catalog.is_file():
        parser.error('Input, CS2 converter, or catalog not found')
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    if args.model not in catalog['assets']:
        parser.error('Model not observed in the installed map catalog')
    with tempfile.TemporaryDirectory(prefix='hammergpt-prop-') as temp:
        temp = Path(temp)
        source, text, binary, check = (temp / n for n in ('source.txt', 'prop.txt', 'prop.vmap', 'check.txt'))
        convert(exe, args.input, source, 'keyvalues2')
        header, roots = parse(source.read_text(encoding='utf-8-sig'))
        try:
            result = add_prop(roots, args.model, args.position, args.angles, args.scale)
        except ValueError as error:
            parser.error(str(error))
        text.write_text(serialize(header, result), encoding='utf-8')
        convert(exe, text, binary, 'binary')
        convert(exe, binary, check, 'keyvalues2')
        _, checked = parse(check.read_text(encoding='utf-8-sig'))
        if result != checked:
            # Converter can canonicalize float formatting; verify the new entity semantically.
            world = get(next(r for r in checked if r.kind == 'CMapRootElement'), 'world')
            prop = get(world, 'children')[-1]
            props = get(prop, 'entity_properties')
            if get(props, 'classname') != 'prop_static' or get(props, 'model') != args.model:
                raise RuntimeError('Converted map did not retain the added prop')
            for key, expected in [('origin', args.position), ('angles', args.angles), ('scales', [args.scale] * 3)]:
                actual = list(map(float, get(prop, key).split()))
                if any(abs(a - b) > 0.001 for a, b in zip(actual, expected)):
                    raise RuntimeError('Converted prop transform changed')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as destination:
            destination.write(binary.read_bytes())
    print(json.dumps({'output': str(output), 'model': args.model, 'position': args.position, 'angles': args.angles, 'scale': args.scale}))


if __name__ == '__main__':
    main()
