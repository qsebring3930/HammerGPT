"""Read-only reference/rejected-set analysis. Never embeds or creates floors."""
from collections import Counter
import itertools
import json
from pathlib import Path

import networkx as nx

from semantic_pipeline import StrategicPlanner,GameplayValidator,FACTS,fact,digest,blueprint,compare_outcomes

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/semantic-validation-v1'


def save(path,value):path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def rejected_plan(candidate,source):
    places=[];mid=candidate['mid']
    for node in candidate['nodes']:
        kind={'T':'T_spawn','CT':'CT_spawn','A':'A_site','B':'B_site'}.get(node['role'],'connector')
        if node['id']==mid:kind='mid_candidate'
        places.append({'id':str(node['id']),'name':node['role'] if node['role']!='connector' else f"junction {node['id']}",
                       'kind':kind,'role_evidence':fact()})
    relations=[]
    for edge in candidate['edges']:
        u,v=map(str,edge['places'])
        for a,b in ((u,v),(v,u)):
            relations.append({'id':f'{a}>{b}','from':a,'to':b,'purpose':'connector_access','team':'both','phase':'any',
                'why':'Legacy link selected by spatial proximity and connectivity; no tactical outcome defined.',
                'purpose_evidence':fact()})
    routes=[]
    for record in candidate['routes']:
        path=list(map(str,record['places']));outcome={k:fact() for k in FACTS}
        outcome['destination']=fact(record['target'],'observed',source)
        outcome['elevation']=fact(0,'observed',source)
        time=record['seconds_centerline_proxy'];outcome['timing']=fact([time,time],'proxy',source)
        purpose='primary_attack' if record['team']=='T' and record['id'].endswith('-1') else 'secondary_attack' if record['team']=='T' else 'defensive_access'
        row={'id':record['id'],'team':record['team'],'phase':record['phase'],'purpose':purpose,
             'places':path,'relationships':[f'{a}>{b}' for a,b in zip(path,path[1:])],
             'outcome':outcome,'purpose_evidence':fact()}
        if purpose=='secondary_attack':row['alternative_to']=record['id'][:-1]+'1'
        routes.append(row)
    return StrategicPlanner().plan({'name':f"Rejected radar {source.parent.name}",'places':places,'relationships':relations,
        'routes':routes,'sites':[],'deployments':[],'mid_claims':[],'cycles':[]})


def generator_signature(candidate):
    points={n['id']:n['center'] for n in candidate['nodes']}
    graph=nx.Graph();graph.add_edges_from(e['places'] for e in candidate['edges'])
    extrema={n['role']:n['center'][1] for n in candidate['nodes'] if n['role'] in ('T','CT')}
    span=max(p[1] for p in points.values())-min(p[1] for p in points.values())
    lengths=[];ratios=[]
    for edge in candidate['edges']:
        from shapely.geometry import LineString
        length=LineString(edge['centerline']).length;lengths.append(length);ratios.append(length/edge['width'])
    return {'T_and_CT_forced_to_Y_extrema':extrema['T']==min(p[1] for p in points.values()) and extrema['CT']==max(p[1] for p in points.values()),
        'site_complexes_defined':False,'site_selection':'near CT, far from T, separated from each other',
        'mid_claim_basis':'nearest nonterminal point to coordinate origin',
        'median_corridor_length_width_ratio':sorted(ratios)[len(ratios)//2],
        'max_corridor_length_width_ratio':max(ratios),'y_span_units':span,
        'cycle_basis_diagnostic_count':len(nx.cycle_basis(graph)),
        'cycle_tactical_purposes_defined':False,
        'selection_score':'max attacker shortest-route time; then coarse preference features',
        'causal_pipeline':'position sampling → nearby planar links → minimum connectivity tests → role tags → corridor buffers',
        'alternate_route_outcomes_measured':['destination','flat elevation'],
        'not_measured':['defender exposure','information','retreat options','rotation options','engagement range','branch-local benefit']}


def reference_analysis(name):
    path=ROOT/f'output/gameplay-route-targets-v4/{name}.json';data=json.loads(path.read_text())
    ledger=json.loads((ROOT/'route-purpose-reviews.json').read_text())['reviews']
    rows=[]
    for group in data['route_sets']:
        for source in group['routes']:
            evidence=f'{path.relative_to(ROOT)}:{source["id"]}'
            pathhash=digest(source['path'])
            review=next((r for r in ledger if r['map']==name and r['source_nav_sha256']==data['nav_sha256'] and r['ordered_nav_path_sha256']==pathhash),None)
            events=[{'id':e['id'],'kind':e['kind'],'title':e['title']} for e in source['reviewed_events']]
            outcome={k:fact() for k in FACTS}
            outcome['destination']=fact(group['to'],'observed',evidence)
            # A reviewed static encounter/choke opportunity is not measured combat.
            if events:
                outcome['engagement']=fact([e['id'] for e in events],'observed',evidence+'; reviewed NAV/context intersections')
            outcome['timing']=fact([source['cost_units']/250]*2,'proxy',evidence+'; centroid-distance proxy')
            rows.append({'id':source['id'],'team':group['from'],'target':group['to'],
                'phase':'conditional_later_flank' if review else 'tactical_role_unknown',
                'condition':review.get('condition') if review else None,
                'place_sequence':source['place_sequence'],'reviewed_events':events,'outcome':outcome,
                'ordered_path_sha256':pathhash,'opening_role_validated':False})
    comparisons=[]
    for a,b in itertools.combinations(rows,2):
        if (a['team'],a['target'],a['phase'])!=(b['team'],b['target'],b['phase']):continue
        comparisons.append({'routes':[a['id'],b['id']],**compare_outcomes(a['outcome'],b['outcome'])})
    # Identity uses typed context incidence, not map names/coordinates. Diagnostic
    # observations still do not establish complete strategic identity or quality.
    context_graph=nx.Graph()
    for row in rows:
        rid='route:'+row['id'];context_graph.add_node(rid,kind=f"{row['team']}:{row['target']}:{row['phase']}")
        for i,event in enumerate(row['reviewed_events']):
            cid='context:'+event['id'];context_graph.add_node(cid,kind=event['kind'])
            between=f'{rid}:{i}';context_graph.add_node(between,kind='ordered_event:'+str(i))
            context_graph.add_edge(rid,between);context_graph.add_edge(between,cid)
    return {'name':name,'evidence_scope':'Existing approved source routes and reviewed context locations only.',
        'source_sha256':digest(data),'routes':rows,'comparisons':comparisons,
        'observed_context_signature':nx.weisfeiler_lehman_graph_hash(context_graph,node_attr='kind'),
        'distinct_context_opportunity_pairs':sum(c['status']=='distinct' for c in comparisons),
        'unverified_pairs':sum(c['status']=='unverified' for c in comparisons),
        'geometry_authorized':False,
        'missing':['deployment assignments','full site phase systems','timed first contests','sightlines/exposure',
                   'information/retreat/rotation outcome equivalence','validated Mid control pressure','cycle-local purposes'],
        'reference_is_not_rejected':'Incomplete extracted supervision is not evidence that the real reference map is invalid.'}


def reference_plan(reference):
    """Use the same contract validator; do not invent unobserved site phases."""
    places={key:{'id':key,'name':key,'kind':kind} for key,kind in
            [('T','T_spawn'),('CT','CT_spawn'),('A','A_site'),('B','B_site')]}
    relations=[];routes=[]
    for row in reference['routes']:
        actor=row['team'] if row['team'] in ('T','CT') else 'unknown'
        purpose='flank' if row['phase']=='conditional_later_flank' else 'rotation' if row['team'] in ('A','B') else 'connector_access'
        seq=[row['team']]
        for event in row['reviewed_events']:
            key='context:'+event['id']
            places[key]={'id':key,'name':event['title'],'kind':'chokepoint' if event['kind']=='choke_transition' else 'encounter_space',
                         'role_evidence':fact(event['title'],'reviewed',reference['name']+':approved context annotation')}
            seq.append(key)
        seq.append(row['target']);witnesses=[]
        for index,(a,b) in enumerate(zip(seq,seq[1:])):
            rid=f"{row['id']}:observed_context:{index}";witnesses.append(rid)
            relations.append({'id':rid,'from':a,'to':b,'team':actor,'phase':row['phase'],'purpose':'connector_access',
                'why':'Source NAV route visits these reviewed contexts in order; tactical use remains partially known.',
                'purpose_evidence':fact()})
        route={'id':row['id'],'team':actor,'phase':row['phase'],'purpose':purpose,'places':seq,
               'relationships':witnesses,'outcome':row['outcome'],'purpose_evidence':fact()}
        if row['condition']:
            route['condition']=row['condition'];route['purpose_evidence']=fact(row['condition'],'reviewed','route-purpose-reviews.json')
        routes.append(route)
    deployments=[]
    for team in ('T','CT'):
        assignments=[]
        for goal in ('A','B'):
            route=next((r for r in reference['routes'] if r['team']==team and r['target']==goal),None)
            if route:assignments.append({'intent':f'observed access to {goal}; tactical assignment unknown','route':route['id']})
        deployments.append({'team':team,'area':team,'assignments':assignments})
    return StrategicPlanner().plan({'name':reference['name']+' incomplete source observation',
        'places':list(places.values()),'relationships':relations,'routes':routes,'deployments':deployments,
        'sites':[{'id':s,'objective':s} for s in ('A','B')],'cycles':[],'mid_claims':[]})


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rejected=ROOT/'output/preference-round-002'
    manifest=json.loads((rejected/'manifest.json').read_text())
    manifest['review_status']='rejected_generation_set'
    manifest['user_rejection_reason']='Shared semantic generator signature; do not improve geometry or generate another floorplan.'
    save(rejected/'manifest.json',manifest)
    lines=['# Semantic validation benchmark', '',
        'Floorplan generation and geometry edits are paused. This run is read-only analysis of existing geometry.', '',
        '## Why the five radars share a signature', '',
        'Positions are sampled first. T/CT are forced to opposite Y extrema; sites are selected near CT and away from T. Nearby planar links precede any gameplay assignments. The resulting spawns/sites are role-marked regions, not deployment/site systems. Mid is the nonterminal nearest the origin. Minimum degree, connectivity and cycle limits shape a reconnecting network but do not establish tactical purpose. Long center-to-center bands remain the dominant geometry.', '',
        'The scorer sees aggregate timings, sharing, sizes and counts. It cannot invent missing engagement, information, phase or deployment relationships. Its fitted preference weights change selection within that same family.', '',
        'Node/edge/cycle counts below are diagnostics only. No complexity score is used by the semantic validator.', '',
        '## Rejected radars', '']
    summaries=[]
    for i in range(1,6):
        source=rejected/f'candidate-{i}/layout.json';candidate=json.loads(source.read_text())
        plan=rejected_plan(candidate,source);report=GameplayValidator().validate(plan)
        folder=OUT/f'rejected-radar-{i}';folder.mkdir(exist_ok=True)
        save(folder/'strategic-plan.json',plan);save(folder/'validation.json',report)
        save(folder/'generator-signature.json',generator_signature(candidate))
        (folder/'blueprint.md').write_text(blueprint(plan,report),encoding='utf-8')
        codes=Counter(v['code'] for v in report['issues'])
        summaries.append({'radar':i,'passed':report['passed'],'blocking_codes':dict(codes)})
        lines.append(f"- Radar {i}: BLOCKED. Missing deployment/site systems, unsupported Mid, unsupported connection purposes, unproven alternatives, and {codes['unjustified_reconnecting_cycle']} uncertified independent cycles.")
    lines+=['','Every geometric alternate remains unverified rather than being falsely declared equivalent. Missing tactical facts are a reason to block production, not proof that two fights are identical.', '', '## Approved reference identities and evidence gaps','']
    references=[]
    for name in ('dust2','anubis','cache','train','cobblestone'):
        reference=reference_analysis(name);references.append(reference)
        folder=OUT/name;folder.mkdir(exist_ok=True);save(folder/'reference-evidence.json',reference)
        observed_plan=reference_plan(reference);observed_report=GameplayValidator().validate(observed_plan)
        observed_report['interpretation']='Incomplete source observation, not rejection of this approved real map.'
        save(folder/'strategic-plan.json',observed_plan);save(folder/'validation.json',observed_report)
        text=[f'# Reference strategic observations: {name}', '',
              'These are source-backed opportunities, not a newly certified full strategic plan. No embedding or geometry.', '',
              '## Routes / convergence contexts','']
        for row in reference['routes']:
            text.append(f"- {row['id']} ({row['phase']}): "+' → '.join(row['place_sequence'])+
                        '; reviewed contexts: '+', '.join(e['title'] for e in row['reviewed_events'])+
                        (f"; condition: {row['condition']}" if row['condition'] else ''))
        text+=['','## Missing tactical evidence','',*['- '+s for s in reference['missing']]]
        (folder/'blueprint.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
        examples=sorted({e['title'] for r in reference['routes'] for e in r['reviewed_events']})
        lines.append(f"- {name}: {reference['distinct_context_opportunity_pairs']} route-pair differences supported by reviewed encounter/choke opportunities. Examples: "+'; '.join(examples[:5])+'. Full semantic validation remains incomplete.')
    lines+=['', 'The five context-incidence fingerprints are diagnostic evidence of different observed route organizations, not five certified tactical-quality scores. Unknown purpose/arrival/visibility is retained. Train’s reviewed Ivy-to-CT-to-B route stays a conditional later flank, never promoted to opening attack.', '',
        '## Four-stage boundary', '',
        '1. StrategicPlanner compiles typed, coordinate-free gameplay contracts.',
        '2. GameplayValidator checks deployment, site phases, Mid, route effects/equivalence and branch-local cycle purpose.',
        '3. SpatialEmbedder solves relative position/elevation only for the exact validated plan; vertical intent is explicit.',
        '4. GeometryGenerator is gated by both prior passes and the persistent generation pause. The legacy sampler is disabled.', '',
        '## Remaining limitation', '',
        'Static source data cannot certify information, combat exposure, range or real arrival timing. The validator handles those as unknown. Passing planned contracts does not prove actual gameplay; eventual embedding/geometry checks must verify the contracts against physical data. Geometry remains paused in this turn.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(OUT/'summary.json',{'rejected':summaries,'references':[{'name':r['name'],'signature':r['observed_context_signature'],
         'distinct_context_opportunity_pairs':r['distinct_context_opportunity_pairs'],'geometry_authorized':False} for r in references],
         'geometry_generated':False,'training_performed':False,'generation_paused':True})
    print(json.dumps({'rejected_passes':sum(r['passed'] for r in summaries),
         'reference_context_signatures':len({r['observed_context_signature'] for r in references}),
         'output':str(OUT),'geometry_generated':False}))


if __name__=='__main__':main()
