"""Separate snapshot measurements, obsolete rectangles and current annotations."""
import json


def reconcile(p,r,out):
    legacy=r['area_allocations'];r['legacy_area_allocations_on_current_space']=legacy
    original=json.loads((out/'before/validation.json').read_text())
    pre_fix=json.loads((out/'aperture-before/validation.json').read_text())
    rows=[];current=[]
    r['issues']=[x for x in r['issues'] if x['code']!='recovery_area_budget']
    for annotation in r['spatial_usefulness']['proposed_area_allocations']:
        role=annotation['role'];budget=next(a['area_budget'] for a in p['allocations'] if a['role']==role)
        area=annotation['walkable_area'];ok=budget[0]<=area<=budget[1]
        current.append({'role':role,'walkable_area':area,'budget':budget,'preserved':ok,
            'boundary':annotation['boundary'],'measurement_source':'current existing-space allocation annotation; proposed budget not approved'})
        if not ok:r['issues'].append({'code':'recovery_area_budget','role':role,'area':area,'budget':budget,
            'measurement_source':'current allocation annotation; not an archived or obsolete rectangle measurement'})
        rows.append({'role':role,'original_budget':budget,
            'original_snapshot_area':next(a['walkable_area'] for a in original['area_allocations'] if a['role']==role),
            'pre_aperture_legacy_rectangle_area':next(a['walkable_area'] for a in pre_fix['area_allocations'] if a['role']==role),
            'legacy_rectangle_intersection_with_current_space':next(a['walkable_area'] for a in legacy if a['role']==role),
            'current_annotation_area':area,'passes_original_budget':ok,
            'proposed_budget':annotation['area_budget'],'passes_proposed_budget':annotation['within_proposed_budget'],
            'proposed_budget_approved':False})
    r['area_allocations']=current
    r['allocation_reconciliation']={'rows':rows,
        'snapshot_sources':{'original':'before/validation.json','pre_aperture':'aperture-before/validation.json'},
        'semantics':'Original allocation rectangles are historical. Current annotations identify parts of existing rear spaces; accepting their proposed numeric budgets is a separate decision.',
        'archived_issue_codes':[x['code'] for x in pre_fix['issues']]}
    r['physical_checks_passed']=not r['issues'] and not r['violations']
