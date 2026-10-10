"""Authored tactical backbone and continuous-space graybox experiment.

This deliberately does not claim learned generation from the weak context model.
NAV annotations inform the vocabulary; shape, links and widths are authored.
"""
import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import networkx as nx
from PIL import Image,ImageDraw,ImageFont
from connected_geometry import validate_floor
from export_macro_graybox import manifold_cells,draw_preview

SPACES=[
 ('TSpawn','attacker_spawn',[128,-2688],[[-320,-3072],[576,-3072],[640,-2816],[576,-2432],[-320,-2432]]),
 ('TStaging','attacker_distribution',[128,-1920],[[-384,-2240],[512,-2240],[640,-2112],[640,-1728],[384,-1664],[-384,-1728]]),
 ('ALobby','a_staging',[-1408,-1856],[[-1920,-2240],[-1152,-2240],[-1024,-2048],[-1024,-1600],[-1408,-1472],[-1920,-1472]]),
 ('AMain','a_approach',[-1728,-768],[[-2112,-1472],[-1536,-1472],[-1536,-960],[-1664,-960],[-1664,-448],[-2112,-448]]),
 ('AYard','a_battlefront',[-1792,576],[[-2496,-192],[-1536,-192],[-1536,64],[-1088,64],[-1088,960],[-1408,1088],[-2368,1088],[-2496,832]]),
 ('SiteA','objective_a',[-2048,1664],[[-2624,1280],[-1728,1280],[-1408,1536],[-1408,2112],[-1728,2240],[-2624,2240]]),
 ('BLobby','b_staging',[1664,-1920],[[1216,-2368],[1920,-2368],[2112,-2176],[2112,-1600],[1216,-1600]]),
 ('BMain','b_approach',[2048,-640],[[1792,-1536],[2432,-1536],[2432,-320],[1984,-320],[1984,-704],[1792,-704]]),
 ('BYard','b_battlefront',[1920,576],[[1216,64],[2368,64],[2624,320],[2624,1088],[1792,1088],[1792,896],[1216,896]]),
 ('SiteB','objective_b',[2368,1664],[[1856,1280],[2944,1280],[2944,2176],[2688,2304],[2112,2304],[1856,2048]]),
 ('MidApproach','central_approach',[64,-960],[[-192,-1472],[448,-1472],[448,-768],[256,-768],[256,-448],[-192,-448]]),
 ('Mid','central_battlefront',[0,448],[[-640,-256],[256,-256],[256,64],[640,64],[640,768],[384,896],[-448,896],[-640,640]]),
 ('MidGuard','defender_mid_access',[128,1280],[[-256,1088],[512,1088],[512,1408],[256,1536],[-256,1536]]),
 ('CTHub','defender_distribution',[256,2048],[[-192,1792],[640,1792],[768,1920],[768,2304],[-192,2304]]),
 ('CTSpawn','defender_spawn',[384,2816],[[0,2560],[768,2560],[768,3136],[128,3136],[0,3008]]),
 ('AAccess','defender_a_access',[-1152,1856],[[-1408,1536],[-768,1536],[-768,2112],[-1408,2112]]),
 ('BAccess','defender_b_access',[1280,1984],[[960,1600],[1600,1600],[1600,2240],[960,2240]]),
]

# Each link records a purpose. Widths are local, not a uniform corridor template.
LINKS=[
 ('TSpawn','TStaging',384,[[128,-2688],[128,-1920]],'spawn distribution'),
 ('TStaging','ALobby',384,[[128,-1920],[-1408,-1920],[-1408,-1856]],'A approach preparation'),
 ('TStaging','BLobby',448,[[128,-1920],[640,-1920],[640,-1984],[1664,-1984],[1664,-1920]],'B approach preparation'),
 ('TStaging','MidApproach',320,[[128,-1920],[128,-960],[64,-960]],'central attack direction'),
 ('ALobby','AMain',448,[[-1408,-1856],[-1728,-1856],[-1728,-768]],'main A attack'),
 ('AMain','AYard',192,[[-1728,-768],[-1728,-256],[-1920,-256],[-1920,576],[-1792,576]],'local A choke into battlefront'),
 ('AYard','SiteA',448,[[-1792,576],[-2048,576],[-2048,1664]],'A execute and withdrawal'),
 ('BLobby','BMain',448,[[1664,-1920],[2048,-1920],[2048,-640]],'main B attack'),
 ('BMain','BYard',256,[[2048,-640],[2048,-128],[2176,-128],[2176,576],[1920,576]],'local B choke into battlefront'),
 ('BYard','SiteB',384,[[1920,576],[2368,576],[2368,1664]],'B execute and withdrawal'),
 ('MidApproach','Mid',256,[[64,-960],[64,-320],[0,-320],[0,448]],'central choke and contest'),
 ('Mid','AYard',320,[[0,448],[-832,448],[-832,832],[-1792,832],[-1792,576]],'alternate A direction from central control'),
 ('Mid','BYard',384,[[0,448],[768,448],[768,192],[1920,192],[1920,576]],'alternate B direction from central control'),
 ('Mid','MidGuard',256,[[0,448],[0,1024],[128,1024],[128,1280]],'contested access toward defender distribution'),
 ('MidGuard','CTHub',320,[[128,1280],[128,2048],[256,2048]],'defender approach to central front'),
 ('CTSpawn','CTHub',448,[[384,2816],[384,2048],[256,2048]],'defender distribution'),
 ('CTHub','AAccess',384,[[256,2048],[-256,2048],[-256,1856],[-1152,1856]],'independent CT access to A'),
 ('AAccess','SiteA',384,[[-1152,1856],[-2048,1856],[-2048,1664]],'A defense and retake'),
 ('CTHub','BAccess',448,[[256,2048],[1280,2048],[1280,1984]],'independent CT access to B'),
 ('BAccess','SiteB',320,[[1280,1984],[2368,1984],[2368,1664]],'B defense and retake'),
]

def inside(x,y,polygon):
    hit=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit

def polygon_cells(polygon):
    return {(x,y) for x in range(math.floor(min(p[0] for p in polygon)/64),math.ceil(max(p[0] for p in polygon)/64))
            for y in range(math.floor(min(p[1] for p in polygon)/64),math.ceil(max(p[1] for p in polygon)/64))
            if inside(x*64+32,y*64+32,polygon)}

def link_cells(points,width):
    cells=set()
    for a,b in zip(points,points[1:]):
        if a[0]!=b[0] and a[1]!=b[1]:raise ValueError('Nonorthogonal street segment')
        x0,x1=min(a[0],b[0])-width/2,max(a[0],b[0])+width/2
        y0,y1=min(a[1],b[1])-width/2,max(a[1],b[1])+width/2
        cells|={(x,y) for x in range(math.floor(x0/64),math.ceil(x1/64)) for y in range(math.floor(y0/64),math.ceil(y1/64))}
    return cells

def route(cells,start,end,excluded=()):
    allowed=set(cells)-set(excluded);start=tuple(int(v//64) for v in start);end=tuple(int(v//64) for v in end)
    if start not in allowed or end not in allowed:return None
    parents={start:None};todo=deque([start])
    while todo:
        a=todo.popleft()
        if a==end:
            path=[]
            while a is not None:path.append(a);a=parents[a]
            return path[::-1]
        for n in [(a[0]-1,a[1]),(a[0]+1,a[1]),(a[0],a[1]-1),(a[0],a[1]+1)]:
            if n in allowed and n not in parents:parents[n]=a;todo.append(n)
    return None

def build():
    regions=[];footprints={};floor=set();net=nx.Graph()
    for key,role,center,polygon in SPACES:
        cells=polygon_cells(polygon);footprints[key]=cells;floor|=cells
        size=[max(p[i] for p in polygon)-min(p[i] for p in polygon) for i in range(2)]+[320]
        regions.append({'id':key,'role':role,'center':center+[0],'size':size,'footprint_polygon_xy':polygon})
        net.add_node(key,role=role)
    links=[];planned={frozenset((a,b)) for a,b,*_ in LINKS}
    for a,b,width,path,purpose in LINKS:
        floor|=link_cells(path,width);net.add_edge(a,b,purpose=purpose,weight=sum(math.dist(p,q) for p,q in zip(path,path[1:])))
        links.append({'source':a,'target':b,'width_units':width,'path_xy':path,'purpose':purpose})
    floor,repairs=manifold_cells(floor);validate_floor(floor,lambda x:0)
    # Inspect contacts between semantic footprints and unrelated streets.
    violations=[]
    for a,b,width,path,_ in LINKS:
        lane=link_cells(path,width)
        for name,footprint in footprints.items():
            if name not in (a,b) and lane&footprint:violations.append({'link':[a,b],'unrelated_space':name})
    region_floor=set().union(*footprints.values())
    streets=[(a,b,link_cells(path,width)-region_floor) for a,b,width,path,_ in LINKS]
    for i,(a,b,cells) in enumerate(streets):
        adjacent=cells|{(x+dx,y+dy) for x,y in cells for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]}
        for d,e,other in streets[i+1:]:
            if not {a,b}&{d,e} and adjacent&other:
                violations.append({'unrelated_links':[[a,b],[d,e]]})
    if violations:raise ValueError('Unintended street contacts: '+json.dumps(violations))
    for key in ['SiteA','SiteB']:
        other='SiteB' if key=='SiteA' else 'SiteA'
        if not nx.has_path(net.subgraph(set(net)-{other}),'CTSpawn',key):raise ValueError('CT access traverses other site')
    positions={r['id']:r['center'][:2] for r in regions};checks=[]
    for team,goal,excluded in [('CTSpawn','SiteA','SiteB'),('CTSpawn','SiteB','SiteA'),('TSpawn','SiteA','SiteB'),('TSpawn','SiteB','SiteA'),('SiteA','SiteB','TSpawn')]:
        path=route(floor,positions[team],positions[goal],footprints[excluded])
        if not path:raise ValueError('Built floor lacks intended route')
        checks.append({'start':team,'end':goal,'avoids':excluded,'floor_grid_length_units':(len(path)-1)*64,'status':'connected'})
    for cut in nx.articulation_points(net):
        pieces=list(nx.connected_components(net.subgraph(set(net)-{cut})))
        for part in pieces:
            if len(part)>1 and not part&{'SiteA','SiteB','TSpawn','CTSpawn'}:
                raise ValueError('Objective-free side component '+str(part))
    arrivals=[]
    for front in ['AYard','Mid','BYard']:
        lengths={team:(len(route(floor,positions[team],positions[front]))-1)*64 for team in ['TSpawn','CTSpawn']}
        arrivals.append({'front':front,'floor_distance_units':lengths,'interpretation':'Grid path distances only; not player timings or safety certification.'})
    plan={'task':'authored_gameplay_backbone_graybox','model_training_performed':False,'learned_generation':False,
          'preview_title':'HammerGPT: purposeful backbone prototype',
          'preview_subtitle':'Authored gameplay spaces and route purposes; continuous floor footprints and local access widths.',
          'preview_footer':'Structural prototype: timings, exposure, utility and tactical quality still need playtesting.',
          'design_choices':{'regions':regions,'connections':links,'corridor_width_units':320,'floor_cell_override':sorted(map(list,floor))},
          'geometry_audit':{'single_connected_floor':True,'corner_repairs':repairs,'unrelated_street_space_contacts':violations,'floor_route_checks':checks,'front_distance_diagnostics':arrivals},
          'limits':['This prototype is authored, not a prediction from the weak trained context encoder.',
                    'Polygon footprints represent continuous gameplay spaces, not NAV regions converted into rooms.',
                    'Floor is flat for the first structural comparison; no claim of trained natural elevation or art.',
                    'Shortest floor distances are not arrival timing, control or visibility tests.',
                    'Cover/utility and site balance remain prototype work.']}
    return plan,floor

def draw_backbone(plan,path):
    im=Image.new('RGB',(1350,1250),'#101a26');pen=ImageDraw.Draw(im)
    def font(size):return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    def xy(p):return 530+p[0]*.17,680-p[1]*.17
    regions={r['id']:r for r in plan['design_choices']['regions']}
    for e in plan['design_choices']['connections']:
        color='#d6a854' if e['source'].startswith('T') or e['source'] in ['ALobby','BLobby','AMain','BMain','MidApproach'] else '#73aecd'
        pen.line([xy(p) for p in e['path_xy']],fill=color,width=4)
    for r in regions.values():
        x,y=xy(r['center']);color='#e9ca5a' if 'battlefront' in r['role'] else '#bb8ecc' if r['id'].startswith('Site') else '#465563'
        box=pen.textbbox((0,0),r['id'],font=font(17));w=box[2]+20
        pen.rounded_rectangle((x-w/2,y-15,x+w/2,y+15),radius=5,fill=color,outline='#bbcbdc')
        pen.text((x-w/2+10,y-11),r['id'],font=font(17),fill='#101a26' if color=='#e9ca5a' else '#f4f6fa')
    pen.text((30,25),'Purposeful gameplay backbone',font=font(29),fill='#edf2fa')
    pen.text((30,70),'Three fronts; independent defender access; central alternatives and rear rotations.',font=font(18),fill='#becbda')
    notes=['Authored layout proposal','Yellow: encounter fronts','Purple: objective sites','Blue links: access / rotation','Gold links: attacker approaches',
           'A: bending main route + Mid access','B: wider route + staggered Mid access','CT reaches each site independently.','Rotation does not require T spawn.',
           'No branch or cycle quota used.','Geometry uses continuous footprints.','Not a trained layout prediction.']
    for i,n in enumerate(notes):pen.text((1000,185+i*60),n,font=font(17),fill='#becbda')
    im.save(path)

def run(output):
    if output.exists():raise ValueError('Use a new prototype directory')
    plan,cells=build();output.mkdir(parents=True)
    plan['planner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'proposal.json').write_text(json.dumps(plan,indent=2));draw_backbone(plan,output/'backbone.png')
    draw_preview(plan,cells,[],output/'geometry-preview.png')
    (output/'review.md').write_text('Authored gameplay-backbone prototype. Three fronts connect distinct T approaches to site yards and contested Mid. CT distribution reaches each site independently and provides a rear rotation. Mid links to both site yards to offer different attack directions and withdrawal paths. No arbitrary branch/cycle quota is imposed. Geometry is an explicit union of asymmetric footprints and variable-width links; source NAV groups are not rendered as rooms. Built-floor route checks pass with the other objective removed. This is structural evidence, not timing, sightline or tactical-quality validation. The weak learned context model was not used to choose the layout.\n')
    print(json.dumps({'spaces':len(SPACES),'links':len(LINKS),'floor_cells':len(cells),'audit':plan['geometry_audit']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output)
