"""Offline prototype: retrieve map references and propose a reviewable blockout."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path


STYLE_WORDS = {
    'Dust2': {'desert', 'dust', 'sand', 'sandy', 'warm', 'courtyard'},
    'Cobblestone': {'castle', 'medieval', 'stone', 'fortress', 'cobblestone'},
    'Vertigo': {'industrial', 'construction', 'rooftop', 'skyscraper', 'vertigo'},
}


def propose(prompt, profiles):
    if not prompt.strip() or not profiles:
        raise ValueError('A nonempty prompt and reference profiles are required')
    words = set(re.findall(r'[a-z0-9]+', prompt.lower()))
    ranked = []
    for profile in profiles:
        matches = sorted(words & STYLE_WORDS.get(profile['name'], set()))
        score = len(matches) * 3
        height = profile['measurements']['nav_center_z_p10_p90_span_units']
        if words & {'vertical', 'stacked', 'multilevel'}:
            score += height / 100
        footprint = profile['measurements']['nav_center_x_span_units'] * profile['measurements']['nav_center_y_span_units']
        if words & {'compact', 'small'}:
            score += 10000000 / max(footprint, 1)
        ranked.append((score, profile['name'], matches, profile))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    chosen = ranked[0][3]
    compact = bool(words & {'compact', 'small'})
    # Dimensions and adjacency below are authored prototype choices, not learned measurements.
    scale = .75 if compact else 1
    raised = bool(words & {'vertical', 'stacked', 'multilevel'})
    definitions = [
        ('TSpawn', 0, -1400, 0, 640, 384),
        ('CTSpawn', 0, 1400, 0, 640, 384),
        ('BombsiteA', -1100, 700, 128 if raised else 0, 768, 640),
        ('BombsiteB', 1100, 700, 0, 768, 640),
        ('Mid', 0, 0, 0, 512, 640),
        ('ApproachA', -1100, -450, 0, 384, 640),
        ('ApproachB', 1100, -450, 0, 384, 640),
        ('ConnectorA', -550, -150, 0, 320, 384),
        ('ConnectorB', 550, -150, 0, 320, 384),
    ]
    regions = [{'id': name, 'center': [round(x*scale), round(y*scale), z],
                'size': [round(w*scale), round(d*scale), 256], 'purpose': name}
               for name, x, y, z, w, d in definitions]
    pairs = [('TSpawn','ApproachA'), ('TSpawn','Mid'), ('TSpawn','ApproachB'),
             ('ApproachA','BombsiteA'), ('ApproachB','BombsiteB'),
             ('Mid','ConnectorA'), ('Mid','ConnectorB'),
             ('ConnectorA','BombsiteA'), ('ConnectorB','BombsiteB'),
             ('BombsiteA','CTSpawn'), ('BombsiteB','CTSpawn')]
    props = [p for p in chosen['top_prop_models'] if p['model'].startswith('models/') and p['model'].endswith('.vmdl')]
    return {'schema_version': 1, 'prompt': prompt, 'method': 'offline_rules_and_reference_retrieval',
            'model_training_performed': False, 'status': 'proposal',
            'reference_ranking': [{'name': name, 'score': round(score, 3), 'matched_words': matches} for score, name, matches, _ in ranked],
            'selected_reference': {'name': chosen['name'], 'map_source': chosen['map_source'], 'nav_source': chosen['nav_source']},
            'reference_evidence': {'measurements': chosen['measurements'], 'recorded_example_routes': chosen['example_routes']},
            'asset_candidates': {'props': props[:8], 'materials': chosen['top_material_references'][:8]},
            'design_choices': {'mode': 'two-site defusal blockout', 'compact': compact, 'raised_site_A': raised,
                               'corridor_width_units': 192, 'regions': regions,
                               'connections': [{'source': a, 'target': b, 'direction': 'bidirectional', 'evidence': 'proposed_design'} for a,b in pairs]},
            'assumptions': ['Two bombsites and three attack approaches are default prototype choices.',
                            'Region sizes, adjacency, and elevations are newly authored; reference routes are evidence only.',
                            'Asset candidates are observed paths; suitability and dimensions require checking before placement.',
                            'Only style keywords, compactness, and verticality are interpreted; other prompt constraints remain unimplemented.'],
            'validation_needed': ['Corridors, ramps, spawn entities, objectives, and cover must be built before playtesting.',
                                  'Compile and regenerate NAV, then check traversal, sightlines, timings, and balance.']}


def preview(plan):
    nodes = {n['id']: n for n in plan['design_choices']['regions']}
    def xy(node):
        x,y,_ = node['center']
        return 500+x*.22, 440-y*.22
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="900" viewBox="0 0 1000 900">',
             '<rect width="1000" height="900" fill="#101827"/>',
             '<g font-family="Arial" fill="#e5edf7">',
             '<text x="35" y="40" font-size="25">HammerGPT — proposed blockout</text>',
             f'<text x="35" y="70" font-size="15">Reference: {html.escape(plan["selected_reference"]["name"])} · authored layout · Hammer units</text>']
    for edge in plan['design_choices']['connections']:
        x1,y1=xy(nodes[edge['source']]); x2,y2=xy(nodes[edge['target']])
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#677b96" stroke-width="16"/>')
    for node in nodes.values():
        x,y=xy(node); w,d,_=node['size']; w*=.22; d*=.22
        color='#b67b36' if node['id'].startswith('Bombsite') else '#284d6d'
        parts.append(f'<rect x="{x-w/2}" y="{y-d/2}" width="{w}" height="{d}" fill="{color}" stroke="#bad0e8"/>')
        parts.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-size="14">{node["id"]}</text>')
        parts.append(f'<text x="{x}" y="{y+20}" text-anchor="middle" font-size="12">z={node["center"][2]}</text>')
    parts.extend(['<text x="35" y="855" font-size="14">Lines propose connections; corridor and ramp geometry has not been generated.</text>', '</g></svg>'])
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    outputs=[args.output, args.output.with_suffix('.svg')]
    if args.output.suffix != '.json' or any(p.exists() for p in outputs):
        parser.error('Choose a new .json output path')
    raw=args.references.read_bytes()
    plan=propose(args.prompt, json.loads(raw)['profiles'])
    plan['reference_profile_sha256']=hashlib.sha256(raw).hexdigest()
    plan['reference_profile_file']=str(args.references.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2), encoding='utf-8')
    args.output.with_suffix('.svg').write_text(preview(plan), encoding='utf-8')
    print(json.dumps({'proposal': str(args.output), 'preview': str(args.output.with_suffix('.svg')), 'reference': plan['selected_reference']['name']}))


if __name__ == '__main__':
    main()
