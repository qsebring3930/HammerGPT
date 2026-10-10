"""Prepare a human-reviewable tactical interpretation of approved Dust2 NAV.

Place-name membership and directed link witnesses are evidence. Gameplay roles
are hypotheses until reviewed; the resulting draft is not a training dataset.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import networkx as nx
from PIL import Image, ImageDraw, ImageFont


ZONE_SPECS = [
    ('t_spawn','T spawn',['TSpawn'],['attacker_distribution'],'Source spawn anchors establish team association.'),
    ('t_ramp','T ramp',['TRamp'],['attacker_approach'],'Transition toward tunnels; do not interpret every NAV region as a room.'),
    ('long_staging','Outside Long',['OutsideLong'],['staging_candidate'],'Proposed preparation/distribution space before Long doors; safety and utility unverified.'),
    ('long_entry','Long doors',['LongDoors'],['choke_candidate','initial_contest_candidate'],'Proposed Long battlefront around the exit, not the entire labeled zone.'),
    ('long_lane','A Long',['LongA'],['main_approach'],'Continuous A approach, not a chain of separately authored rooms.'),
    ('long_positions','Pit / side',['Pit','Side'],['holding_position_candidate'],'Local positioning opportunity; sightlines, power and escape options unverified.'),
    ('mid_top','Top Mid',['TopofMid'],['attacker_distribution','initial_contest_candidate'],'Proposed central front; exact encounter location depends on arrival and sightlines.'),
    ('mid_lane','Middle',['Middle'],['contested_connector'],'Connects central approaches; control and exposure require review.'),
    ('a_short','Catwalk / Short',['Catwalk','ShortStairs'],['alternate_a_approach'],'Separate A attack direction and connection to mid; not a secret route.'),
    ('b_staging','Outside tunnels',['OutsideTunnel'],['staging_candidate'],'Proposed B-side preparation space; grenade and sound behavior unverified.'),
    ('upper_tunnel','Upper tunnels',['UpperTunnel'],['main_b_approach','choke_candidate','initial_contest_candidate'],'B exit is a candidate front. The whole tunnel is not being labeled a chokepoint.'),
    ('lower_link','Lower tunnel / stairs',['LowerTunnel','TunnelStairs'],['repositioning_connector'],'Connects tunnel-side play to mid; route trace must support this interpretation.'),
    ('ct_distribution','CT / Under A',['CTSpawn','UnderA'],['defender_distribution','rotation_candidate'],'Candidate defender backbone; only CTSpawn regions contain spawn anchor evidence.'),
    ('a_access','A ramp / extended',['ARamp','ExtendedA'],['site_access','retake_candidate'],'A access role varies by subregion; mixed attacker/defender use requires finer review.'),
    ('b_access','B doors / window',['BDoors','Hole'],['defender_b_access','retake_candidate'],'Door/window access is a hypothesis based on place names and graph paths; elevation and sightlines differ.'),
    ('site_a','A site',['BombsiteA'],['objective','postplant_candidate'],'Objective anchor establishes A association via NAV place name; labeled area exceeds the plant volume.'),
    ('site_b','B site',['BombsiteB'],['objective','postplant_candidate'],'Objective anchor establishes B association via NAV place name; labeled area exceeds the plant volume.'),
]


def representative(nodes, ids):
    if not ids:raise ValueError('Missing endpoint regions')
    return max(ids,key=lambda n:(len(nodes[n]['nav_area_ids']),n))


def trace_route(graph, start, end, allowed_labels, required_labels=()):
    nodes={n['id']:n for n in graph['nodes']}
    permitted={n for n,r in nodes.items() if r['label'] in allowed_labels or r['label'] is None}
    net=nx.DiGraph();net.add_nodes_from(permitted);evidence={}
    for edge in graph['edges']:
        a,b=edge['source'],edge['target']
        if a in permitted and b in permitted:
            net.add_edge(a,b,weight=math.dist(nodes[a]['position'],nodes[b]['position']))
            evidence[a,b]=edge
    if start not in permitted or end not in permitted or not nx.has_path(net,start,end):
        return {'status':'unresolved','reason':'No directed path in the proposed place-name route corridor.'}
    path=nx.shortest_path(net,start,end,weight='weight')
    labels=[nodes[n]['label'] for n in path]
    missing=set(required_labels)-set(labels)
    if missing:return {'status':'unresolved','reason':f'Path misses intended route labels: {sorted(missing)}','candidate_region_path':path}
    links=[]
    for a,b in zip(path,path[1:]):
        witnesses=evidence[a,b]['witnesses']
        if not witnesses:raise ValueError('Route edge has no NAV witness')
        links.append({'source':a,'target':b,'recorded_nav_witness':witnesses[0],
                      'reverse_edge_exists':evidence[a,b]['reverse_edge_exists']})
    return {'status':'recorded_directed_route','region_path':path,'place_labels':labels,
            'positions':[nodes[n]['position'] for n in path], 'links':links,
            'region_centroid_distance_proxy_units':sum(net[a][b]['weight'] for a,b in zip(path,path[1:])),
            'unlabeled_regions':[n for n in path if nodes[n]['label'] is None],
            'distance_limit':'Sum of coarse-region centroid separations; not actual walking distance, timing or player clearance.'}


def annotate(graph):
    if graph['map']!='Dust2' or graph['dataset_role']!='training':raise ValueError('This first annotation supports approved training Dust2 only')
    nodes={n['id']:n for n in graph['nodes']};zones=[];membership={}
    for key,title,labels,roles,reason in ZONE_SPECS:
        ids=[n for n,r in nodes.items() if r['label'] in labels]
        if not ids:raise ValueError('Expected source place names missing: '+title)
        for n in ids:
            if n in membership:raise ValueError('Duplicate zone membership')
            membership[n]=key
        anchors=[a['id'] for a in graph['anchors'] if set(a['region_ids'])&set(ids)]
        zones.append({'id':key,'title':title,'source_place_labels':labels,'region_ids':ids,
            'nav_area_ids':sorted(a for n in ids for a in nodes[n]['nav_area_ids']),
            'roles_proposed':roles,'interpretation':reason,'review_status':'pending',
            'evidence':{'membership_basis':'Extracted coarse NAV place labels; not architectural boundaries.',
                        'intersecting_anchor_ids':anchors},
            'height_range_of_region_centroids':[min(nodes[n]['position'][2] for n in ids),max(nodes[n]['position'][2] for n in ids)]})
    def team(classname):
        counts=Counter(n for a in graph['anchors'] if a['classname']==classname for n in a['region_ids'])
        return counts.most_common(1)[0][0]
    t,ct=team('info_player_terrorist'),team('info_player_counterterrorist')
    objectives={}
    for anchor in graph['anchors']:
        if anchor['classname']!='func_bomb_target':continue
        labels={nodes[n]['label'] for n in anchor['region_ids']}
        site='A' if 'BombsiteA' in labels else ('B' if 'BombsiteB' in labels else None)
        if site is None:raise ValueError('Objective place association unresolved')
        objectives[site]={'anchor_id':anchor['id'],'region':representative(nodes,anchor['region_ids']),
                          'region_ids':anchor['region_ids'],'bounds':anchor['bounds'],
                          'basis':'VMAP objective volume association plus NAV place-name label; not game auto-designation verification.'}
    if set(objectives)!=set('AB'):raise ValueError('Expected distinct A/B anchors')
    a,b=objectives['A']['region'],objectives['B']['region']
    route_specs=[
        ('t_a_long','T -> A via Long',t,a,['TSpawn','TRamp','OutsideLong','LongDoors','LongA','Pit','Side','ARamp','BombsiteA'],['LongDoors','LongA'], 'Main attacker approach'),
        ('t_a_short','T -> A via Short',t,a,['TSpawn','TopofMid','Middle','Catwalk','ShortStairs','ExtendedA','BombsiteA'],['Catwalk','ShortStairs'],'Alternate attacker approach'),
        ('t_b_tunnel','T -> B via tunnels',t,b,['TSpawn','TRamp','OutsideTunnel','UpperTunnel','BombsiteB'],['UpperTunnel'],'Main attacker approach'),
        ('ct_a','CT -> A access',ct,a,['CTSpawn','UnderA','ARamp','ExtendedA','BombsiteA'],[],'Defender access without traversing B'),
        ('ct_b','CT -> B via doors',ct,b,['CTSpawn','MidDoors','BDoors','Hole','BombsiteB'],['BDoors'],'Defender access without traversing A'),
        ('a_b_rotation','A -> B via CT-side route',a,b,['BombsiteA','ARamp','ExtendedA','UnderA','CTSpawn','MidDoors','BDoors','Hole','BombsiteB'],['CTSpawn'],'Candidate defender rotation'),
        ('t_b_mid','T -> B via Mid',t,b,['TSpawn','TopofMid','Middle','MidDoors','BDoors','Hole','BombsiteB'],['MidDoors','BDoors'],'Control-dependent alternate B approach'),
        ('lower_mid','Lower tunnels -> Mid',representative(nodes,[n for n,r in nodes.items() if r['label']=='LowerTunnel']),representative(nodes,[n for n,r in nodes.items() if r['label']=='Middle']),['LowerTunnel','TunnelStairs','Middle','MidDoors','TopofMid'],[],'Repositioning connector, not a disconnected decorative loop'),
    ]
    routes=[]
    for key,title,start,end,allowed,required,purpose in route_specs:
        routes.append({'id':key,'title':title,'purpose_proposed':purpose,'review_status':'pending',
                       'allowed_place_labels':allowed,**trace_route(graph,start,end,allowed,required)})
    # MidDoors is its own meaningful transition, not an unclassified remainder.
    ids=[n for n,r in nodes.items() if r['label']=='MidDoors']
    for n in ids:membership[n]='mid_doors'
    zones.append({'id':'mid_doors','title':'Mid doors','source_place_labels':['MidDoors'],'region_ids':ids,
        'nav_area_ids':sorted(a for n in ids for a in nodes[n]['nav_area_ids']),
        'roles_proposed':['choke_candidate','contested_connector'],'review_status':'pending',
        'interpretation':'Lower-mid transition into CT/B-side access; exact front depends on control and timings.',
        'evidence':{'membership_basis':'Extracted coarse NAV place labels; not architectural boundaries.','intersecting_anchor_ids':[]}})
    unresolved=[n for n in nodes if n not in membership]
    interfaces=[]
    for edge in graph['edges']:
        s,t=membership.get(edge['source']),membership.get(edge['target'])
        if s and t and s!=t:interfaces.append({'source_zone':s,'target_zone':t,'source_region':edge['source'],
            'target_region':edge['target'],'witness_count':len(edge['witnesses']),
            'reverse_edge_exists':edge['reverse_edge_exists']})
    return {'schema_version':1,'map':'Dust2','dataset_role':'training','annotation_status':'draft_pending_user_review',
        'training_eligible':False,'source_provenance':graph['provenance'],'coarse_provenance':graph['coarse_provenance'],
        'zones':zones,'region_zone_membership':membership,'unresolved_region_ids':unresolved,
        'objective_evidence':objectives,'routes':routes,'directed_zone_interfaces':interfaces,
        'front_hypotheses':[{'id':'long_front','location':'Long doors exit / Long-Pit interaction','status':'unverified'},
                            {'id':'mid_front','location':'Mid sightline and access decisions','status':'unverified'},
                            {'id':'b_front','location':'Upper-tunnel B exit','status':'unverified'}],
        'limits':['Gameplay roles and fronts are proposals; place labels and witnesses do not establish control, timing, safety or tactical utility.',
                  'Many NAV regions can form one continuous space. An interface may be open ground rather than a doorway/choke.',
                  'XY diagram projects different heights together; it does not certify visibility, collision, or NAV freshness.',
                  'Exact choke footprints, arrival timings, sightlines, grenade use and post-plant positions remain unannotated.',
                  'This draft must not be loaded as approved training labels. No model training or map modification occurs.']}


def draw_annotation(graph,annotation,output):
    colors=['#eeaa67','#e7bd91','#ee8a51','#e2b653','#c89543','#b17f51','#7ccab6','#559eaa',
            '#66b9e4','#c790db','#a776bd','#8787d0','#72a6ed','#a4c4ea','#77b57d','#dfa4a0','#d8b778','#498895']
    zone_colors={z['id']:colors[i] for i,z in enumerate(annotation['zones'])}
    vertices=[p for polygon in graph['nav_polygons'] for p in polygon['corners']]
    x0,x1=min(p[0] for p in vertices),max(p[0] for p in vertices)
    y0,y1=min(p[1] for p in vertices),max(p[1] for p in vertices)
    scale=min(1000/(x1-x0),1000/(y1-y0))
    image=Image.new('RGB',(1660,1220),'#111925');draw=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    def xy(p):return (45+(p[0]-x0)*scale,140+(y1-p[1])*scale)
    reviewed=annotation.get('annotation_status')=='reviewed_first_pass'
    draw.text((35,22),'Dust2: reviewed gameplay-role groups' if reviewed else 'Dust2: gameplay-role annotation for review',font=font(30),fill='#edf2fa')
    draw.text((35,68),'Source NAV footprint. Roles reviewed; exact meeting-area and choke boundaries remain separate targets.' if reviewed else 'Actual source NAV footprint. Colors group place names; gameplay roles are proposed, not approved labels.',font=font(19),fill='#cbd4df')
    for polygon in graph['nav_polygons']:
        zone=annotation['region_zone_membership'].get(polygon['region_id'])
        draw.polygon([xy(p) for p in polygon['corners']],fill=zone_colors.get(zone,'#59616d'))
    nodes={n['id']:n for n in graph['nodes']}
    for number,zone in enumerate(annotation['zones'],1):
        core=representative(nodes,zone['region_ids']);x,y=xy(nodes[core]['position'])
        draw.ellipse((x-13,y-13,x+13,y+13),fill='#111925',outline='#eef2f7',width=2)
        label=str(number);draw.text((x-(5 if number<10 else 10),y-10),label,fill='#eef2f7',font=font(16))
        yrow=145+(number-1)*48
        draw.rectangle((1100,yrow+3,1117,yrow+20),fill=zone_colors[zone['id']])
        draw.text((1126,yrow),f"{number}. {zone['title']}",font=font(18),fill='#eaf0f7')
        draw.text((1126,yrow+22),' / '.join(zone['roles_proposed'][:2]).replace('_',' '),font=font(13),fill='#b9c7d8')
    yrow=1050
    for text in ['Review: Long, Mid, and B-exit front hypotheses.',
                 'CT access to each site traced separately.',
                 'Grey patches: unresolved place membership.',
                 'Projected heights overlap; this is not a sightline map.']:
        draw.text((1090,yrow),text,font=font(16),fill='#cbd4df');yrow+=28
    draw.text((35,1178),'First-pass role review recorded. Source maps untouched; no new model training.' if reviewed else 'DRAFT: user review required before training. Source maps untouched; no new model training.',font=font(20),fill='#f2bf77')
    image.save(output)


def run(source,output):
    if output.exists():raise ValueError('Use a new annotation directory')
    raw=source.read_bytes();graph=json.loads(raw);annotation=annotate(graph)
    annotation['source_graph_sha256']=hashlib.sha256(raw).hexdigest()
    annotation['annotator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True);(output/'annotation.json').write_text(json.dumps(annotation,indent=2))
    draw_annotation(graph,annotation,output/'overview.png')
    lines=['# Dust2 gameplay-role draft','',
        'This is a draft for review, not approved training labels. Source NAV/VMAP facts are distinguished from proposed tactical interpretations. No model training or map edits occurred.', '',
        '## Review priorities','',
        '1. Are Outside Long / Outside tunnels useful staging interpretations?',
        '2. Are Long entry, Mid interaction and B tunnel exit a useful first-pass division of initial contest areas?',
        '3. Are CT-side access and Lower-tunnel/Mid connector interpretations appropriate?',
        '4. Which zones need splitting or merging? Names are source place-name groups, not rooms.', '',
        '## Proposed areas','', '| Area | Proposed role | Caveat |','|---|---|---|']
    for z in annotation['zones']:lines.append(f"| {z['title']} | {', '.join(z['roles_proposed'])} | {z['interpretation']} |")
    lines+=['','## Directed reference routes','','| Route | Recorded? | Purpose proposed |','|---|---|---|']
    for r in annotation['routes']:lines.append(f"| {r['title']} | {r['status']} | {r['purpose_proposed']} |")
    lines+=['',f"Unresolved membership: {len(annotation['unresolved_region_ids'])} of {len(graph['nodes'])} coarse regions.",
            'All traced links retain a directed NAV-area witness in annotation.json. Route positions are region centroids and may cross walls visually; they are not certified traversable centerlines.', '',
            '## Missing targets','',
            'Exact choke boundaries, safe utility areas, timing fronts, visibility/exposure, saving positions and post-plant/retake cover require further evidence and review.',
            'The 0.001-unit objective-volume association tolerance and known source/NAV limitations remain recorded in source provenance.', '',
            'A positive review approves the stated interpretation only; it does not validate omitted gameplay properties or train a model automatically.']
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'map':annotation['map'],'status':annotation['annotation_status'],
        'zones':len(annotation['zones']),'unresolved_regions':len(annotation['unresolved_region_ids']),
        'routes':[{k:r[k] for k in ('id','status')} for r in annotation['routes']], 'training_eligible':False},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
