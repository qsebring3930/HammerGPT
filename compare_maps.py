"""Build comparable, measured reference profiles for a future map planner."""
import argparse
from collections import Counter
import json
from pathlib import Path

from build_routes import center


def percentile(values, fraction):
    values = sorted(values)
    position = fraction * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def profile(name, reference, nav, graph):
    areas = [a for a in nav['areas'] if a['hull'] == graph['hull'] and a['movable_mesh_id'] == 0xffffffff]
    points = [center(a) for a in areas]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    heights = [p[2] for p in points]
    box = reference['spatial']['mesh_bounds']
    inside = sum(all(box['min'][i] <= p[i] <= box['max'][i] for i in range(3)) for p in points) if box else 0
    models = Counter(e['properties'].get('model') for e in reference['spatial']['entities'] if e['classname'].startswith('prop_') and e['properties'].get('model', '').startswith('models/') and e['properties']['model'].endswith('.vmdl'))
    return {'name': name, 'map_source': reference['source'], 'nav_source': nav['source'],
            'measurements': {'meshes': reference['spatial']['mesh_count'], 'entities': len(reference['spatial']['entities']),
                             'materials': len(reference['spatial']['material_references']), 'nav_areas': len(areas),
                             'named_areas': graph['summary']['distinct_named_areas'], 'label_coverage_percent': graph['summary']['label_coverage_percent'],
                             'nav_center_x_span_units': round(high[0] - low[0], 2), 'nav_center_y_span_units': round(high[1] - low[1], 2),
                             'nav_center_z_span_units': round(high[2] - low[2], 2),
                             'nav_center_z_p10_p90_span_units': round(percentile(heights, .9) - percentile(heights, .1), 2),
                             'nav_centers_inside_mesh_extent_percent': round(inside / len(points) * 100, 2),
                             'ladders_not_modeled': nav['ladder_count'], 'directed_region_edges': len(graph['edges'])},
            'top_prop_models': [{'model': model, 'instances': count} for model, count in models.most_common(12)],
            'top_material_references': [{'material': model, 'references': count} for model, count in list(reference['spatial']['material_references'].items())[:12]],
            'named_areas': sorted({n['label'] for n in graph['nodes'] if n['label']}),
            'example_routes': graph['example_routes'], 'asset_resolution': reference['asset_audit']['counts']}


def report(profiles):
    lines = ['# Reference map comparison', '', 'Measured geometry, navigation, assets, and inferred area labels. These profiles prepare examples for a planner; they do not train a model or establish gameplay balance.', '',
             '| Measurement | ' + ' | '.join(p['name'] for p in profiles) + ' |', '| --- | ' + ' | '.join('---:' for p in profiles) + ' |']
    for key in profiles[0]['measurements']:
        lines.append('| ' + key + ' | ' + ' | '.join(str(p['measurements'][key]) for p in profiles) + ' |')
    lines.extend(['', 'Height spans measure NAV polygon centers in Hammer units. The 10th–90th percentile span reduces extreme outliers; it is not a count of floors. Extent alignment only checks a coarse box and does not prove navigation freshness.', ''])
    for p in profiles:
        lines.extend(['## ' + p['name'], '', '**Named areas:** ' + ', '.join(p['named_areas']), '', '**Most placed prop models:**', ''])
        lines.extend(f"- `{m['model']}`: {m['instances']}" for m in p['top_prop_models'][:5])
    lines.extend(['', '## Planner use', '', '- Match broad style requests to observed material and prop palettes.', '- Use recorded topology and spawn-to-objective examples as layout references.', '- Compare vertical extent and route branching across maps.', '- Keep source map/NAV provenance, unnamed regions, and unsupported ladders explicit.', '', 'Route distances use polygon centers and representative spawn-area polygons. No inference of player travel time, sightline quality, cover effectiveness, or tactical superiority is made.'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', nargs=4, action='append', required=True, metavar=('NAME', 'REFERENCE', 'NAV', 'GRAPH'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        parser.error('Choose new output files')
    profiles = []
    for name, ref_path, nav_path, graph_path in args.map:
        ref, nav, graph = [json.loads(Path(p).read_text(encoding='utf-8')) for p in (ref_path, nav_path, graph_path)]
        profiles.append(profile(name, ref, nav, graph))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'schema_version': 1, 'model_training_performed': False, 'profiles': profiles}, indent=2), encoding='utf-8')
    args.output.with_suffix('.md').write_text(report(profiles), encoding='utf-8')
    print(json.dumps([{'name': p['name'], **p['measurements']} for p in profiles]))


if __name__ == '__main__':
    main()
