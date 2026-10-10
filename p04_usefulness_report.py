"""Append the current revision and transparent budget proposals to review."""

def append_report(p,r,out):
    m=r['spatial_usefulness'];lines=['# P04 frozen architecture — B aperture correction','',
        'Stage 4 and batch generation remain paused. P04 strategy hash, separate attacker commitments, absence of Mid and rear-deployment defender rotation remain unchanged.',
        '',f'![Clean scaled plan]({(out/"plan-clean.png").as_posix()})','',f'![Focused encounter overlay]({(out/"plan-encounters.png").as_posix()})','',
        'Overall architecture is frozen. This revision changes only B main: its aperture runs from plan x=114 to x=118 at y=74, matching the unchanged partition edge. Intended and measured clear width are both 128 HU, with 96 HU of player-centre span under the assumed 32-HU footprint. The prior declaration was 224 HU with only 128 HU actually clear. Pre-fix files are preserved in aperture-before.',
        '', '### Before / after decisions','',
        '| Space | Change and purpose |','|---|---|']
    for pocket in p['pocket_review']:lines.append(f"| {pocket['location']} | {pocket['action']}: {pocket['purpose']} |")
    lines+=['',
        'A departure loses its unused lower slab and becomes a building-edge lane that widens at staging. B loses its blind lobby stub. Commitments still leave opposite sides of T deployment and share no new Mid. B side adds a threshold into a sheltered landing followed by a perpendicular site entry; this is a place to stop/retreat and prepare, not an extra route or decorative zigzag.',
        '', '### Provisional engine scale and clearance','',
        'Chosen scale: **1 plan unit = 32 Source/Hammer units (HU)**. Player marker: 32×32 HU. Assumed standing height 72, standing eye 64, crouched eye 46 HU; walls/full-height masses 160 HU, low cover 48 HU. These are authored planning assumptions, not verified CS2 hull/eye values. [Valve SDK view/hull definitions](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/shareddefs.h) are game-specific and do not establish current CS2 values.',
        '', 'Every route is rechecked for an axis-aligned 32-HU square footprint in eroded free space. This is a static 2D clearance check, not physics, movement, crouching, jump, crowd, weapon or ceiling validation.',
        '', '| Opening | Nominal width HU | Actual collision-free width HU | Player widths | Player-centre span HU |','|---|---:|---:|---:|---:|']
    for d in m['doorways']:lines.append(f"| {d['opening']} | {d['nominal_source_units']:.0f} | {d['clear_source_units']:.0f} | {d['player_widths']:.1f} | {d['player_centre_span_source_units']:.0f} |")
    lines+=['', 'B main intended aperture and actual finite-depth clear width now agree at 128 HU. Other architecture and cover footprints are unchanged. No aperture is certified for dynamic player passing or runtime tolerances.',
        '', '| Key route | Measured length HU |','|---|---:|']
    for d in m['key_distances']:lines.append(f"| {d['route']} | {d['source_units']:.0f} |")
    lines+=['', '| First contact | Before HU at same assumed scale | Revised HU |','|---|---:|---:|']
    for d in m['deployment_to_first_contact']:lines.append(f"| {d['site']} | {d['before_first_contact_source_units_at_same_provisional_scale']:.0f} | {d['to_first_contact_source_units']:.0f} |")
    lines+=['', f"Routes failing the provisional player-footprint check: {len(m['remaining_clearance_problems'])}.",
        'Even with no disconnected routes, two-player passing/turning at the narrower thresholds, collision tolerances and dynamic fights remain unverified. No distance is converted to timing.',
        '', '### Site entry-clearing and plant space','']
    for name,sequence in p['encounter_sequences'].items():lines.append(f"- **{name}:** {' → '.join(sequence['steps'])}. {sequence['purpose']} These are checks, not a requirement to walk into every corner.")
    lines+=['', 'The outlined plant envelopes exclude cover footprints from usable planting area. Engine bomb-trigger rules, vertical planting and jumpable cover are not implemented.',
        '', '| Site | Collision-free plant area HU² | Provisional player-centre plant area HU² |','|---|---:|---:|']
    for s in m['plant_areas']:lines.append(f"| {s['site']} | {s['collision_free_area_source_units_squared']:.0f} | {s['player_centre_plant_area_source_units_squared']:.0f} |")
    lines+=['', 'Low cover remains solid to walking navigation but is omitted from standing-eye occlusion. At the authored 48-HU height it blocks the assumed 46-HU crouched-eye rays. In the A-main-to-plant example, standing visibility is '+str(m['A_low_cover_example']['standing'])+' and crouched visibility is '+str(m['A_low_cover_example']['crouched'])+'. This is a flat constant-eye-height test, not 3D collision or bullet penetration.',
        '', '### Proposed budget revisions — not accepted','',
        'Original allocation rectangles and budgets remain unchanged in composition.json. Current allocation annotations use the separately recorded existing-space regions. Measurements below do not silently approve their proposed budgets. They are authored review proposals, not trained or calibrated thresholds.',
        '', 'Area budgets below are plan units squared (multiply by 1024 for HU²). They are not engine-calibrated requirements.',
        '', '| Role | Original area budget | Proposed area budget | Actual walkable allocation | Reason |','|---|---|---|---:|---|']
    for row in m['proposed_area_allocations']:
        old=next(a for a in p['allocations'] if a['role']==row['role'])
        lines.append(f"| {row['role']} | {old['area_budget']} | {row['area_budget']} | {row['walkable_area']:.1f} | {row['reason']} |")
    for row in p['distance_revision_proposals']:
        actual=next(d for d in r['distance_allocations'] if d['route']==row['route'])
        lines+=['',f"{row['route']}: original {p['distance_budgets'][row['route']]} plan units; proposed {row['budget']}; measured {actual['travel_length']:.2f}. {row['reason']}"]
    lines+=['','### Allocation history reconciled','',
        'Archived failures remain in their snapshot files. Intersecting an obsolete rectangle with current walkable space is reported as a legacy diagnostic, not the usable area of the current allocation annotation. Current annotations are checked against the unchanged original budget and separately against the unapproved proposal.',
        '', '| Role | Original snapshot area | Pre-fix obsolete rectangle area | Same old rectangle on current geometry | Current annotation area | Original budget result | Proposed budget result |',
        '|---|---:|---:|---:|---:|---|---|']
    for row in r['allocation_reconciliation']['rows']:
        lines.append(f"| {row['role']} | {row['original_snapshot_area']:.2f} | {row['pre_aperture_legacy_rectangle_area']:.2f} | {row['legacy_rectangle_intersection_with_current_space']:.2f} | {row['current_annotation_area']:.2f} | {'within' if row['passes_original_budget'] else 'MISS'} | {'within, unapproved' if row['passes_proposed_budget'] else 'MISS'} |")
    lines+=['', '### Remaining review concerns','',
        '- B main interference is corrected; simultaneous player movement, runtime tolerances and doorway/headroom behavior still need engine inspection.',
        '- Close A holds have escape routes, but safe escape and useful encounter timing are not proved. The removed recesses reduce clearing burden; they do not establish balance.',
        '- Site-cover heights and eye/hull assumptions need later CS2 verification. The macro shape remains a separated-site P04, and the revised recovery proposals require explicit review.',
        '- No final visual acceptance, automatic generation, diversity batch or Stage 4 authorization. Stop after this single revision.','']
    lines+=['','### Inspected reference decisions','', '| Change | References | Applied decision |','|---|---|---|']
    for item in p['reference_guidance'][-3:]:
        refs=', '.join(f'[{s.split("/")[2]}]({(out.parents[1]/s).as_posix()})' for s in item['references'])
        lines.append(f"| {item['change']} | {refs} | {item['use']} |")
    lines+=['', 'Radar references guide local arrangements and qualitative proportions only; they do not determine the authored heights, player dimensions, timing or balance.',
        '', '### Current results against original budgets','']
    for issue in r['issues']:lines.append('- '+str(issue))
    lines+=['',f"Strategic angle violations: {len(r['violations'])}; undeclared opening samples: {len(r['opening_audit']['unintended_openings'])}; service-to-CT route avoiding both sites: {'present' if not r['architecture_audit']['service_shortcut_removed'] else 'absent'}.",
        '', f'[Concrete isolated graybox proposal — pending approval]({(out/"graybox-proposal.md").as_posix()}). This proposal creates no engine geometry and does not count as automatic generation or diversity evidence.',
        '', 'Static clearance is implementation evidence, not candidate acceptance. No calibrated timing, balanced contest, automatic composition sampler, final visual acceptance or diversity result is claimed.','']
    (out/'review.md').write_text('\n'.join(lines),encoding='utf-8')
