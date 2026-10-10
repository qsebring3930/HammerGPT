"""Prepare declarative inspection-build proposal only. Does not export geometry."""
import json
from pathlib import Path
from shapely.geometry import Point
from playable_composition import compile_composition
from semantic_pipeline import digest

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'output/p04-playable-composition-001'


def run():
    p=json.loads((OUT/'composition.json').read_text());r=json.loads((OUT/'validation.json').read_text())
    c=compile_composition(p);scale=p['engine_scale']['source_units_per_plan_unit'];offset=p['annotations']['T']['point']
    centre=c['walkable'].buffer(-.5,join_style=2);spawns=[]
    for team,classname,points,yaw in (
        ('T','info_player_terrorist',[[62,16],[64,16],[66,16],[62,19],[64,19]],90),
        ('CT','info_player_counterterrorist',[[67,109],[69,109],[71,109],[67,112],[69,112]],270)):
        for i,point in enumerate(points):
            if not centre.covers(Point(point)):raise ValueError('Proposed spawn fails provisional footprint clearance.')
            spawns.append({'team':team,'classname':classname,'name':f'hg_p04_{team}_{i}',
                'plan_position':point,'source_origin':[(point[j]-offset[j])*scale for j in (0,1)]+[8],
                'yaw':yaw,'provisional_footprint_clear':True})
    cs2=Path('C:/Program Files (x86)/Steam/steamapps/common/Counter-Strike Global Offensive')
    target=cs2/'content/csgo_addons/aitesting/maps/hg_p04_inspection_001.vmap'
    spec={'schema':'p04-inspection-graybox-proposal-v1','status':'awaiting_user_approval_no_geometry_created',
        'composition_sha256':digest(p),'strategy_sha256':r['plan_sha256'],
        'source':str((OUT/'composition.json').resolve()),'purpose':'Inspect movement, proportions, entry clearing and sightlines in a private playable graybox.',
        'stage4_authorized':False,'batch_authorized':False,'generator_evidence':False,'diversity_evidence':False,
        'destination':str(target),'destination_currently_exists':target.exists(),
        'reference_read_only':str(cs2/'content/csgo_addons/aitesting/maps/aitesting.vmap'),
        'coordinate_transform':{'source_xy':'32 * (plan_xy - T_annotation_xy)','origin_plan_xy':offset,'floor_top_z':0,'spawn_z':8},
        'floors':{'footprint':'union of the declared architectural spaces, including underneath walls/cover','z_range':[-16,0],'material':'neutral development material resolved from installed assets'},
        'full_height_geometry':{'footprint':'compiled solid space minus low-cover footprints, bounded by the existing envelope','z_range':[0,160],
            'boundary_thickness':25.6,'apertures':'all declared openings, floor to 160 HU; B main exactly 128 HU clear',
            'ceiling':'open sky; no new roof or headroom obstacles'},
        'low_cover':[{'id':m['id'],'plan_footprint':m['boundary'],'z_range':[0,m['height_source_units']]} for m in p['internal_masses'] if m.get('height_class')=='low_cover'],
        'escape_control':'Player clip above full-height masses to Z=512 to prevent roof/outer-boundary escapes; low cover remains available for jump/standing/crouch inspection. No new floor connections.',
        'spawns':spawns,
        'bombsites':[{'name':site,'classname':'func_bomb_target','plan_envelope':outline,
            'trigger_footprint':'envelope intersected with walkable space, excluding cover footprints','z_range':[0,32],
            'designation':site,'schema_check':'Confirm installed CS2 A/B designation property before export; do not reuse the legacy exporter value for both sites.'} for site,outline in p['objective_zones'].items()],
        'lighting':'Reuse verified sandbox global lighting/settings with neutral dev surfaces; resolve required installed CS2 entities/materials before export. No additional play spaces.',
        'implementation':'A dedicated polygon-to-VMAP adapter is required. Existing legacy grid exporter must not reshape this composition or invent cover.',
        'checks_after_approval':['Verify composition/strategy hashes and refuse overwrites.',
            'Export matching polygon floors/full-height solids/low cover and ten spawns/two bomb targets.',
            'Roundtrip VMAP and verify mesh topology, coordinates, heights, aperture width and entity identities.',
            'Compile only the new inspection map with installed CS2 Workshop Tools; report actual compile result.',
            'Load a private local session, verify spawning and separately designated A/B planting.',
            'Walk both primary/secondary entries, rear rotation and recovery; inspect B main width, side landing and A close hold.',
            'Inspect low cover when standing/crouched, jumping onto it, plant eligibility and boundary escape prevention.',
            'Record observed issues without changing architecture; stop for user review.'],
        'excluded':['No batch, automatic composition sampling, training update, diversity score, balance certification or publication.',
            'Do not overwrite existing VMAPs, reference maps, learned datasets or addon settings.',
            'Approval of this inspection build does not accept proposed recovery budgets or enable general Stage 4 generation.']}
    if spec['destination_currently_exists']:raise ValueError('Inspection stem already exists; choose another in the proposal before approval.')
    (OUT/'graybox-proposal.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    lines=['# Proposal: isolated playable P04 inspection graybox','',
        '**Pending approval. No VMAP, engine geometry or compiled map has been created by this proposal. Stage 4 and batch generation remain paused.**','',
        'Purpose: inspect movement, proportions, entry clearing and standing/crouched sightlines in the single authored composition. This is not balance certification, automatic-generator evidence or the diversity milestone.',
        '',f'Frozen composition SHA-256: `{spec["composition_sha256"]}`. The strategy hash is also bound in graybox-proposal.json.',
        '',f'New map only: `{target}`. The destination was checked and does not exist. The existing aitesting.vmap is a read-only serialization/lighting reference; no existing map or addon settings will be overwritten.',
        '', '## Exact proposed contents','',
        '- Scale: 32 HU per plan unit, translated so the T annotation is XY=(0,0). Floor top Z=0, floor slab down to Z=-16.',
        '- Floors follow the union of the frozen architectural spaces. Full-height solids/walls follow the compiled mass/opening representation, Z=0–160; walls retain 25.6-HU thickness. Declared openings stay clear to 160 HU; B main is 128 HU wide.',
        '- Two existing low-cover pieces retain their declared footprints and Z=0–48 HU. Open sky, neutral development materials, verified sandbox lighting. No new stairs, roofs, props or corridors.',
        '- Five T and five CT spawns, individually checked against the provisional 32-HU square footprint. Proposed origins and facing directions are listed below.',
        '- Two separately designated A/B func_bomb_target entities use the existing plant envelopes minus cover footprints, with intended ground-level triggers Z=0–32. Verify installed designation properties and actual planting behavior before calling the map playable.',
        '- Player clipping extends above full-height masses to Z=512 to prevent unintended roof/outer escapes. Low cover remains testable for standing, crouching and jumping; its effect on planting will be observed rather than assumed.',
        '', '| Spawn | Proposed HU origin | Yaw |','|---|---|---:|']
    for s in spawns:lines.append(f"| {s['name']} | {s['source_origin']} | {s['yaw']} |")
    lines+=['', '## Build and inspection sequence after approval','']
    lines += [f'{i}. {step}' for i,step in enumerate(spec['checks_after_approval'],1)]
    lines+=['', 'Existing VMAP serialization/entity helpers and dmxconvert are available. The installed converter and sandbox reference were checked. A dedicated adapter for the space/mass/opening representation still needs implementation; the legacy grid exporter cannot be used unchanged.',
        '', 'Engine hull/eye values, headroom, dynamic player passing, bullet behavior and planting rules are not yet verified. The inspection is intended to expose those issues. If compilation or loading fails, preserve the new artifact and report the exact failure; do not report a playable result prematurely.',
        '', '**Requested approval scope:** implement and export this one frozen inspection composition, compile its new map stem and inspect it locally. This does not approve recovery-budget proposals, publication, batch generation or automatic composition generation. Stop after inspection for review.','']
    (OUT/'graybox-proposal.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'proposal_ready':True,'engine_geometry_created':False,'stage4_authorized':False,'batch_authorized':False,'spawns_planned':len(spawns)}))


if __name__=='__main__':run()
