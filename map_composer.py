"""Joint parcel/role/circulation search. No authored/P04 floorplan templates."""
import copy
import hashlib
import itertools
import math
import random
import networkx as nx
import numpy as np
from shapely.geometry import Polygon,LineString,Point,box
from shapely.affinity import translate
from shapely.ops import unary_union,linemerge
from playable_composition import compile_composition,DerivedNavigation,observed_openings
from semantic_pipeline import digest
from map_architecture_metrics import assess,targets
from radar_reference_rules import RULES
from nav_movement_rules import RULES as NAV_RULES
from route_composition import program as route_program,assemble as route_assemble,bind as bind_route_roles
from mid_architecture import compose as compose_mid_frontages
from map_design_spec import mid_strategy

VERSION='joint-parcel-composer-v8.2-distributed-mid'
CONFIG={'version':VERSION,'validator_version':'physical-and-specification-v1','cells':[5,5],'parcel_dimension_plan_units':[18,26],
 'placement_limit':32,'feasible_arrangement_shortlist':6,'path_options':5,'backtrack_limit':1600,'navigation_step':0.5,'contested_mid_cells':[6,6],
 'scale_HU_per_unit':32,'player_width_HU':32,'boundary_thickness':0.8,
 'full_height_HU':160,'low_cover_HU':48,
 'historical_cap':'P04 1536-HU external connector cap remains in frozen experiments. Here there are no separate spawn connectors; optional maximum_main_route_HU applies to complete main routes. No inherited recovery minima.',
 'mid_distance_ratio_warning':1.6,'mid_distance_ratio_gate':2.5,'nav_reference_rules':NAV_RULES,'reference_library':RULES['version'],'reference_library_sha256':RULES['observation_library_sha256'],'reference_motifs':['R14/R17 offset-frontage','R05/R09/R14/R15 shouldered-court','R02/R14/R18 continuous-expansion','R12/R17 folded-front','R04/R06/R09/R14 staggered-depth']}

class SearchFailure(ValueError):
    def __init__(self,message,log):super().__init__(message);self.log=log

def paths(graph,start,end,forbidden,limit,rng):
    h=graph.copy();h.remove_nodes_from(set(forbidden)-{start,end})
    # Seeded weights favor short traversals, vary architectural assembly, never
    # turn a graph edge into floor: all candidates are compiled afterward.
    for a,b in h.edges:h[a][b]['weight']=h[a][b].get('physical_distance',1)*(1+rng.random()*.15)
    try:return list(itertools.islice(nx.shortest_simple_paths(h,start,end,weight='weight'),limit))
    except (nx.NetworkXNoPath,nx.NodeNotFound):return []

def choose_network(graph,roles,spec,rng,log,mid_handoff_site=None):
    """Backtrack required edge purposes and earlier paths, not post-route repairs."""
    mid=spec['gameplay']['mid']=='contested';secondary=spec['gameplay']['secondary_access'];sites=[roles['A'],roles['B']]
    handoff_site=mid_handoff_site
    requirements=[('T-A-main','T','A'),('CT-A-deploy','CT','A'),('T-B-main','T','B'),('CT-B-deploy','CT','B')]
    # Sampling order revisits early paths when later assignments fail.
    rng.shuffle(requirements);budget=[CONFIG['backtrack_limit']]
    fixed=set(roles.values());solutions=[]
    def extend(index,chosen,used):
        if budget[0]<=0:return None
        if index==len(requirements):
            return secondaries(chosen,used)
        rid,a,b=requirements[index];start,end=roles[a],roles[b]
        blocked=(fixed-{start,end})|used
        for path in paths(graph,start,end,blocked,CONFIG['path_options'],rng):
            budget[0]-=1
            if len(path)<3:continue # actual staging/receiving before objective
            # Staged request requires two physical approach parcels, not labels.
            staged=spec['gameplay']['site_commitment']=='staged' or (spec['gameplay']['site_commitment']=='mixed' and b=='B')
            if a=='T' and staged and len(path)<4:continue
            trial={**chosen,rid:path};more=set(path[1:-1])
            result=extend(index+1,trial,used|more)
            if result:return result
        return None
    def secondaries(chosen,used):
        # Reconsider alternate approaches when their first feasible path takes
        # the wrong ingress face or prevents another required connection. The
        # former greedy first-path choice favored the aligned scaffold.
        tasks=[('Mid-spine','Mid','Mid2'),('T-Mid','T','Mid'),('CT-Mid','CT','Mid2'),('Mid-A','Mid','A'),('Mid-B','Mid2','B')] if mid else [('local-A',None,'A'),('local-B',None,'B')]
        def assign(index,extra,occupied):
            if index==len(tasks):
                if mid:
                    extra=dict(extra);spine=extra['Mid-spine'];extra['CT-Mid']=extra['CT-Mid']+list(reversed(spine))[1:];extra['Mid-B']=spine+extra['Mid-B'][1:]
                return {**chosen,**extra}
            rid,source,destination=tasks[index]
            main=chosen['T-'+destination+'-main'] if destination in ('A','B') else None
            early=not source and spec['soft_preferences'].get('route_complexity',.5)>=.7 and len(main)>=4
            start=roles[source] if source else main[-3] if early else main[-2]
            handoff=destination==handoff_site and rid.startswith('Mid-')
            end=main[-2] if handoff else roles[destination]
            opts=paths(graph,start,end,(fixed-{start,end})|occupied,CONFIG['path_options']+8,rng)
            for path in opts:
                budget[0]-=1
                if budget[0]<0:return None
                if destination in ('A','B'):
                    if len(path)<(3 if handoff else 4 if mid else 3):continue
                    previous={chosen['T-'+destination+'-main'][-2],chosen['CT-'+destination+'-deploy'][-2]}
                    if not handoff and path[-2] in previous:continue
                if handoff:path=path+[roles[destination]]
                result=assign(index+1,{**extra,rid:path},occupied|set(path[1:-1]))
                if result:return result
            return None
        return assign(0,{},set(used))
    result=extend(0,{},set())
    log.append(dict(stage='joint_path_search',roles={k:list(v) for k,v in roles.items()},visited_branch_count=CONFIG['backtrack_limit']-budget[0],success=result is not None,order=[r[0] for r in requirements]))
    return result

def generate(spec,seed):
    r=random.Random(seed);log=[];size=spec['hard_constraints']['max_extent_HU']/32
    mid=spec['gameplay']['mid']=='contested';count=6 if mid else 5
    plan=mid_strategy(spec,seed) if mid else None;organization=plan['organization'] if mid else None
    if mid:log.append(dict(stage='coordinate_free_mid_strategy',**plan))
    # Nonuniform architectural parcels; spacings chosen jointly with roles.
    span=min(size-8,(118 if mid else 104)+12*(1-spec['soft_preferences']['compactness']))
    def divisions():
        raw=[r.uniform(18,26) for _ in range(count)];return [4]+list(np.cumsum([v*span/sum(raw) for v in raw])+4)
    xs,ys=divisions(),divisions();cells={(x,y):box(xs[x],ys[y],xs[x+1],ys[y+1]) for x in range(count) for y in range(count)}
    centers={(x,y):((xs[x]+xs[x+1])/2,(ys[y]+ys[y+1])/2) for x,y in cells}
    graph=nx.grid_2d_graph(count,count);network=None;roles=None
    for a,b in graph.edges:graph[a][b]['physical_distance']=math.dist(centers[a],centers[b])
    feasible=[];distance_targets=targets(spec)
    mid=spec['gameplay']['mid']=='contested'
    # Choose a spatial organization before searching local route assignments.
    # Failure of its bounded search is recorded, never remapped to aligned sites.
    family=r.choice(['staggered-flanks','folded-front','open-flanks']) if spec['architecture']['site_separation']=='separated' else 'open-flanks'
    log.append(dict(stage='reference_arrangement',family=family,sources=['R12','R17'] if family=='folded-front' else ['R04','R06','R09','R14'] if family=='staggered-flanks' else ['R07','R18'],scope='Reuse spatial relationships, not source map geometry or inferred gameplay. Mid/adjacent retain supported flank reservation search.'))
    for placement in range(CONFIG['placement_limit']):
        # Relative flank positions sampled, not complete floorplan templates.
        separation=spec['architecture']['site_separation']
        rows=list(range(1,count-1));row_a=r.choice(rows) if mid else r.choices([1,2,3],weights=[1,3,1])[0];row_b=(r.choice(rows) if mid else r.choices([1,2,3],weights=[1,3,1])[0]) if r.random()<spec['soft_preferences']['asymmetry'] else row_a
        if family=='staggered-flanks':
            row_b=r.choice([v for v in rows if v!=row_a])
        a=(0 if separation=='separated' else 1,row_a);b=(count-1 if separation=='separated' else count-2,row_b)
        front=min(row_a,row_b);rear=max(row_a,row_b)
        t=(r.choice([1,2,3]),r.choice(list(range(max(1,front)))))
        ct=(r.choice(list(range(1,count-1))),r.choice(list(range(rear+1,count))))
        if family=='folded-front':
            # Adjacent exterior sides, diagonal separation, rear on the inside
            # corner. Main commitments and three site sectors still gate it.
            a=(0,r.choice([1,2]));b=(r.choice([2,3]),count-1)
            t=(r.choice([1,2,3]),0);ct=(2,r.choice([2,3]))
        roles={'T':t,'CT':ct,'A':a,'B':b}
        if mid:
            m=r.choice([(2,2),(2,3),(3,2),(3,3)]);roles['Mid']=m
            options=[n for n in cells if 1<=n[0]<count-1 and 1<=n[1]<count-1 and abs(n[0]-m[0])+abs(n[1]-m[1])==(1 if organization=='contested_street' else 2)]
            if organization=='linked_courts':options=[n for n in options if n[0]!=m[0] and n[1]!=m[1]]
            roles['Mid2']=r.choice(options)
        if len(set(roles.values()))!=len(roles):continue
        trial=choose_network(graph,roles,spec,r,log,plan['handoff_site'] if mid else None)
        if not trial:continue
        lengths={rid:sum(graph[u][v]['physical_distance'] for u,v in zip(path,path[1:]))*32 for rid,path in trial.items()}
        if mid:
            mid_ratio=max(lengths['T-Mid'],lengths['CT-Mid'])/min(lengths['T-Mid'],lengths['CT-Mid'])
            if mid_ratio>1.9:
                log.append(dict(stage='arrangement_rejection',reason='Mid centerline imbalance leaves insufficient margin for unchanged 2.5 physical-distance gate',estimated_ratio=mid_ratio))
                continue
        primary=max(lengths['T-A-main'],lengths['T-B-main'])
        secondary=max(lengths['T-Mid']+lengths['Mid-'+site] for site in ('A','B')) if mid else max(lengths['T-A-main']+lengths['local-A'],lengths['T-B-main']+lengths['local-B'])
        rotation=lengths['CT-A-deploy']+lengths['CT-B-deploy']
        terms=[primary/distance_targets['primary_approach_HU'],secondary/distance_targets['secondary_approach_HU'],rotation/distance_targets['complete_site_rotation_HU']]
        score=max(terms)+.25*sum(terms)
        feasible.append((score,roles.copy(),trial,lengths))
        log.append(dict(stage='arrangement_distance_candidate',placement=placement,roles={k:list(v) for k,v in roles.items()},estimated_complete_route_HU=lengths,estimated_site_rotation_HU=rotation,score=score,scope='Centerline estimates guide shared selection; actual ordered navigation is measured afterward.'))
        if len(feasible)>=CONFIG['feasible_arrangement_shortlist']:break
    if feasible:
        score,roles,network,estimate=min(feasible,key=lambda item:item[0])
        log.append(dict(stage='arrangement_selection',selected_roles={k:list(v) for k,v in roles.items()},feasible_options=len(feasible),score=score,reason='Minimize complete approach and rear rotation burden within bounded feasible placements, not connector length or graph complexity.'))
    if network is None:raise SearchFailure('Joint placement/circulation search exhausted; no rule or gate relaxed.',log)
    p=dict(schema='playable-space-mass-openings-v1',candidate='spec-'+str(seed),generator_version=VERSION,seed=seed,specification_sha256=digest(spec),
           engine_scale=dict(source_units_per_plan_unit=32,standing_eye_source_units=64,crouched_eye_source_units=46),boundary_thickness=.8,
           reference_influences=RULES,nav_reference_influences=NAV_RULES,envelope=[[0,0],[size,0],[size,size],[0,size]],spaces=[],openings=[],internal_masses=[],annotations={},objective_zones={},site_spaces={},defender_positions={},
           strategic_network={k:[list(c) for c in path] for k,path in network.items()},decision_log=log,space_program={},route_contracts={},physical_route_waypoints={},physical_route_leg_spaces={})
    if mid:p['mid_organization']=organization;p['mid_handoffs']=[site for site in ('A','B') if network['Mid-'+site][-2]==network['T-'+site+'-main'][-2]]
    selected=set(n for route in network.values() for n in route);edges=set(tuple(sorted((a,b))) for path in network.values() for a,b in zip(path,path[1:]));site_nodes={v:k for k,v in roles.items() if k in ('A','B')}
    if mid:p['geometric_precision_plan_units']=1e-8
    # The partition is a building reservation scaffold, not a grid of rooms.
    # Allocate actual circulation width and receiving/encounter space together.
    neighbor={n:[] for n in selected}
    for u,v in edges:neighbor[u].append(v);neighbor[v].append(u)
    important=set(roles.values());investment_nodes={}
    for site in ('A','B'):
        important.update([network['T-'+site+'-main'][-2],network['CT-'+site+'-deploy'][-2],network[('Mid-' if mid else 'local-')+site][-2]])
        if spec['gameplay']['site_commitment']=='staged' or (spec['gameplay']['site_commitment']=='mixed' and site=='B'):
            investment_nodes[network['T-'+site+'-main'][-3]]=site;important.add(network['T-'+site+'-main'][-3])
    episodes,sequences=route_program(network,roles,spec,seed)
    if mid:
        episodes={}
        for sequence in sequences.values():sequence['profile']='joint-offset-street-frontages';sequence['episode_nodes']=[]
    important.update(episodes)
    footprints={};episode_parts={};episode_openings={}
    p['architectural_buildings']=[]
    # Image-space motifs set dimensionless proportions. HU sizes remain our
    # provisional authored scale, not reverse-engineered radar measurements.
    proportion=r.choice([(18,10),(16,12),(19,11)])
    aisle=r.choice([7.5,9.0])
    log.append(dict(stage='reference_local_rules',sources=['R14','R17','R18'],room_aspect=proportion[0]/proportion[1],aisle_to_short_room_ratio=aisle/proportion[1],scope='Adaptable rule ranges informed by coarse image samples; not exact extracted dimensions.',court_shoulder_sources=['R05','R09','R14','R15']))
    # Long uninterrupted runs get a single building-defined offset passage,
    # only when a whole circulation run has sufficient aspect and a usable bay.
    # Short/ordinary straight runs remain straight (Cache support evidence).
    straight={n for n in selected-important if len(neighbor[n])==2 and (neighbor[n][0][0]-n[0],neighbor[n][0][1]-n[1])==(-(neighbor[n][1][0]-n[0]),-(neighbor[n][1][1]-n[1]))}
    runs=nx.Graph();runs.add_nodes_from(straight)
    for u,v in edges:
        if u in straight and v in straight:runs.add_edge(u,v)
    building_turns={};routing_centers={k:list(v) for k,v in centers.items()}
    mid_shapes={}
    if mid:
        mid_shapes,positions,decisions=compose_mid_frontages(cells,centers,neighbor,roles,aisle,seed,organization)
        routing_centers.update(positions)
        log.append(dict(stage='joint_mid_architecture',decisions=decisions,reason='Court frontages and street mouths placed together; reservation grid no longer sets rectangular room cores or centred lane mouths.'))
    for component in nx.connected_components(runs):
        ordered=sorted(component);horizontal=len({n[1] for n in ordered})==1
        length=sum((cells[n].bounds[2]-cells[n].bounds[0]) if horizontal else (cells[n].bounds[3]-cells[n].bounds[1]) for n in ordered)
        if len(ordered)<2 or length/aisle<NAV_RULES['authored_choices']['long_run_aspect_trigger']:continue
        node=ordered[len(ordered)//2];building_turns[node]=horizontal
        log.append(dict(stage='movement_frontage_turn',node=list(node),run=[list(n) for n in ordered],aspect=length/aisle,nav_patterns=['dust2-space-0','cache-space-4','train-space-1'],radar_sources=['R14','R17','R18'],scope='Observed support turns around exclusions; authored one attached facade and opposite passing bay on a long reserved run. Not copied source coordinates.'))
    for node in sorted(selected):
        area=cells[node];x0,y0,x1,y1=area.bounds;cx,cy=centers[node]
        if mid:
            footprints[node]=mid_shapes[node];continue
        if node in site_nodes:footprints[node]=area;continue
        role=next((k for k,v in roles.items() if v==node),None)
        faces={(q[0]-node[0],q[1]-node[1]) for q in neighbor[node]}
        if role in ('T','CT'):
            horizontal=sum(abs(v[0]) for v in faces)>=sum(abs(v[1]) for v in faces)
            wx,wy=proportion if horizontal else tuple(reversed(proportion))
        elif role=='Mid':wx,wy=18,18
        elif node in important:
            # Chamber proportions follow assigned site frontage, not a common
            # square with identical arms. Holding occurs beside actual passage.
            near=min(site_nodes,key=lambda site:math.dist(centers[site],centers[node]))
            horizontal=abs(near[0]-node[0])>abs(near[1]-node[1])
            wx,wy=proportion if horizontal else tuple(reversed(proportion))
        else:wx,wy=(aisle+3,aisle+3) if len(faces)==2 and not any((-v[0],-v[1]) in faces for v in faces) else (aisle,aisle)
        wx=min(wx,x1-x0-1.2);wy=min(wy,y1-y0-1.2)
        # Offset holding footprints toward the used fronts, while keeping the
        # canonical routing point inside. This moves surrounding solid masses
        # along with the room, rather than dropping a prop in an empty corner.
        dx=sum(v[0] for v in faces)*1.2 if node in important else 0
        dy=sum(v[1] for v in faces)*1.2 if node in important else 0
        rx0,ry0,rx1,ry1=cx+dx-wx/2,cy+dy-wy/2,cx+dx+wx/2,cy+dy+wy/2
        rx0,ry0,rx1,ry1=max(x0,rx0),max(y0,ry0),min(x1,rx1),min(y1,ry1)
        # Fill the assigned frontage rather than adding a symmetric neck on
        # every face. Through rooms are elongated receiving/clearing spaces;
        # turn rooms reach only their actual two door frontages.
        if node in important and role not in ('T','CT','Mid'):
            # A receiving/holding chamber fills its objective frontage, but
            # its approach from travel territory widens continuously into it.
            front=min(neighbor[node],key=lambda q:math.dist(centers[q],centers[near]))
            if front[0]<node[0]:rx0=x0
            if front[0]>node[0]:rx1=x1
            if front[1]<node[1]:ry0=y0
            if front[1]>node[1]:ry1=y1
        room=box(rx0,ry0,rx1,ry1)
        # Entry/exit socket widths widen continuously into the chamber.
        # Closed faces and surrounding masses are composed at the same time;
        # no independent random corner notches or ornamental bevels.
        pieces=[room]
        half=aisle/2
        # Straight travel remains constant-width; only actual holding/receiving
        # chambers expand. Do not create a repeating flare at every reservation.
        # Through rooms use flush joins; a turning court may open continuously.
        # Other enclosed holding spaces receive offset real thresholds, not a
        # universal symmetric tapered neck.
        opposed=any((-v[0],-v[1]) in faces for v in faces)
        transition='continuous-court' if role=='Mid' else 'flush' if opposed or role in ('T','CT') else 'offset-threshold'
        spread_x=half;spread_y=half
        log.append(dict(stage='transition_context',node=list(node),type=transition,nav_patterns=['cache-space-1'] if transition=='flush' else ['dust2-space-0','cache-space-4'],radar_sources=['R14','R17','R18']))
        for q in neighbor[node]:
            # Width change occurs along travel direction beside a building
            # frontage. Important rooms already extend to used shared faces.
            if q[0]>node[0]:pieces.append(Polygon([(cx,cy-spread_y),(x1,cy-half),(x1,cy+half),(cx,cy+spread_y)]))
            elif q[0]<node[0]:pieces.append(Polygon([(x0,cy-half),(cx,cy-spread_y),(cx,cy+spread_y),(x0,cy+half)]))
            elif q[1]>node[1]:pieces.append(Polygon([(cx-spread_x,cy),(cx+spread_x,cy),(cx+half,y1),(cx-half,y1)]))
            else:pieces.append(Polygon([(cx-half,y0),(cx+half,y0),(cx+spread_x,cy),(cx-spread_x,cy)]))
        # On non-decision travel parcels, an elbow expands at its actual turn.
        # The gallery union consumes that space continuously without fake doors.
        shape=unary_union(pieces)
        if node in building_turns:
            # Both bank footprint and passing bay are defined together. One
            # bank projects across the previous axis; the free bay carries the
            # walking route past its end, retaining the original end sockets.
            horizontal=building_turns[node]
            if horizontal:
                bay=box(max(x0+.8,cx-8),max(y0+.8,cy-half-5),min(x1-.8,cx+8),cy+half)
                bank=box(cx-4,cy-2.5,cx+4,cy+half+.5)
                routing_centers[node]=[cx,cy-4]
            else:
                bay=box(max(x0+.8,cx-half-5),max(y0+.8,cy-8),cx+half,min(y1-.8,cy+8))
                bank=box(cx-2.5,cy-4,cx+half+.5,cy+4)
                routing_centers[node]=[cx-4,cy]
            shape=shape.union(bay).difference(bank)
        if node in episodes:
            parts,joins,position,building=route_assemble(episodes[node],area,faces,[cx,cy],aisle)
            episode_parts[node]=parts;episode_openings[node]=joins
            shape=unary_union([part for _,part in parts]);routing_centers[node]=position
            if building is not None:p['architectural_buildings'].append(dict(node=list(node),boundary=list(building.exterior.coords)[:-1],purpose='Jointly generated footprint bounds intermediate approach circulation',profile=episodes[node]['profile']))
            log.append(dict(stage='route_assembly',node=list(node),**episodes[node],spatial_parts=[name for name,g in parts],source_scope='Adaptable architectural assembly informed by NAV support and independent radar context; no source polygon copying.'))
        footprints[node]=shape
    # Merge traversed, non-decision parcels into continuous architectural aisles.
    # Avoid arbitrary doors at planning-grid boundaries.
    merge_graph=nx.Graph();merge_graph.add_nodes_from(selected-important)
    street_nodes=set(network['Mid-spine']) if mid and organization=='contested_street' else set()
    merge_graph.add_nodes_from(street_nodes)
    for u,v in edges:
        if u in merge_graph and v in merge_graph and ((u in street_nodes)==(v in street_nodes)):merge_graph.add_edge(u,v)
    groups={};merged_shapes={}
    for i,nodes in enumerate(nx.connected_components(merge_graph)):
        gid='mid_street' if nodes<=street_nodes else 'circulation_gallery_'+str(i);merged_shapes[gid]=unary_union([footprints[n] for n in nodes])
        for n in nodes:groups[n]=gid
    node_spaces={};site_settings={s:spec['architecture']['site_setting'] for s in ('A','B')};plant_cover_candidates={}
    if site_settings['A']=='mixed':site_settings={'A':'courtyard','B':'interior'}
    def add_space(sid,shape,kind,purpose):
        p['spaces'].append(dict(id=sid,boundary=list(shape.exterior.coords)[:-1],holes=[list(r.coords)[:-1] for r in shape.interiors],kind=kind,purpose=purpose));p['space_program'][sid]=dict(kind=kind,purpose=purpose)
    def mass(sid,shape,height,purpose):p['internal_masses'].append(dict(id=sid,boundary=list(shape.exterior.coords)[:-1],height_source_units=height,purpose=purpose))
    for node in sorted(selected):
        shape=footprints[node];sid='parcel_'+str(node[0])+'_'+str(node[1]);parts=[]
        if node in groups:
            gid=groups[node];g=merged_shapes[gid]
            if gid not in p['space_program']:add_space(gid,g,'courtyard' if gid=='mid_street' else 'circulation','Continuous contested street with distributed approach mouths' if gid=='mid_street' else 'Continuous architectural aisle; unused reservation becomes solid building mass')
            if gid=='mid_street':
                for role in ('Mid','Mid2'):
                    if roles[role]==node:p['annotations'][role]=dict(point=routing_centers[node])
            node_spaces[node]=[(gid,g)];continue
        if node in episode_parts:
            for label,g in episode_parts[node]:
                eid=sid+'_'+label;kind='interior' if episodes[node]['profile']=='building-wrap' else 'courtyard'
                add_space(eid,g,kind,'Intermediate main approach: '+episodes[node]['profile']);parts.append((eid,g))
            node_spaces[node]=parts
            if node in investment_nodes:p['annotations'][investment_nodes[node]+'_investment']=dict(point=routing_centers[node])
            for first,last,line in episode_openings[node]:
                w=spec['hard_constraints']['minimum_door_width_HU']/32
                if line.length<w+1.6:raise SearchFailure('Building-wrap circulation lacks declared opening/turning frontage',log)
                aperture=LineString([line.interpolate((line.length-w)/2),line.interpolate((line.length+w)/2)])
                p['openings'].append(dict(id=sid+'_'+first+'_'+last,spaces=[sid+'_'+first,sid+'_'+last],aperture=list(aperture.coords),transition='continuous-shared-circulation',purpose='Connected passage around a coherent building footprint; local retreat/exposure alternative, not a new site attack route'))
            continue
        if node in site_nodes:
            site=site_nodes[node];sid=site+'_objective';x0,y0,x1,y1=shape.bounds
            # A projecting shoulder on an UNUSED face subdivides the court.
            # Its sloped frontage carries a building footprint into the court;
            # it is not an isolated corner block or a random bevel. Keep the
            # northern plant band and all three actual ingress faces intact.
            faces={(q[0]-node[0],q[1]-node[1]) for q in neighbor[node]}
            main=network['T-'+site+'-main'][-2];alt=network[('Mid-' if mid else 'local-')+site][-2]
            main_face=(main[0]-node[0],main[1]-node[1]);alt_face=(alt[0]-node[0],alt[1]-node[1])
            opposed_attack=main_face==(-alt_face[0],-alt_face[1])
            depth=3+2*spec['soft_preferences']['sightline_breaks']
            facade=None
            if not opposed_attack:
                if (-1,0) not in faces:facade=box(x0,y0+5,x0+depth,y1-8)
                elif (1,0) not in faces:facade=box(x1-depth,y0+5,x1,y1-8)
                elif (0,-1) not in faces:facade=box(x0+5,y0,x1-5,y0+depth)
                # Keep upper plant band intact when the unused face is north.
                # No sloped shoulder is required just because a court exists.
            if facade is not None and not facade.is_empty:shape=shape.difference(facade)
            log.append(dict(stage='court_frontage',site=site,type='flush-court' if facade is None else 'attached-building-bank',nav_patterns=['cache-space-1','train-space-1'],radar_sources=['R14','R17','R18'],boundary=list(facade.exterior.coords)[:-1] if facade is not None else None,purpose='Architecture follows actual approach sectors; no repeated angled shoulder formula.'))
            if site_settings[site]=='interior':
                # Interior architecture changes actual boundaries, doors and
                # sightlines: an internal vestibule, not a courtyard relabel.
                # Keep the objective majority and an entry vestibule six units
                # wide. A center split bisected every nine-unit arrival frontage
                # and left neither half wide enough for the requested doorway.
                cut=x1-6
                pieces=[(sid,shape.intersection(box(x0,y0,cut,y1))),(site+'_vestibule',shape.intersection(box(cut,y0,x1,y1)))]
                for i,g in pieces:add_space(i,g,'interior','Interior objective/entry clearing compartment');parts.append((i,g))
                yy=(y0+y1)/2+3;w=spec['hard_constraints']['minimum_door_width_HU']/32
                p['openings'].append(dict(id=site+'_interior_threshold',spaces=[sid,site+'_vestibule'],aperture=[[cut,yy-w/2],[cut,yy+w/2]],purpose='Clear vestibule before objective; full-height internal partition'))
            else:
                add_space(sid,shape,'courtyard','Open-air combat court bounded by attached building frontage');parts=[(sid,shape)]
            # Door sockets will avoid this attached footprint below.
            # Full-height notch is represented by the footprint boundary and
            # surrounding solid envelope, not an isolated corner fixture.
            objective=parts[0][1];ox0,oy0,ox1,oy1=objective.bounds
            plant=box(ox0+1.5,oy1-8,ox1-1.5,oy1-2)
            p['objective_zones'][site]=list(plant.exterior.coords)[:-1];p['site_spaces'][site]=sid
            # Keep labels/plant/holding away from low and full-height solids.
            point=[(ox0+ox1)/2,oy1-4];p['annotations'][site]=dict(point=point)
            plant_cover_candidates[site]=[box((ox0+ox1)/2-3,oy1-10,(ox0+ox1)/2-1,oy1-8),box(ox1-6,oy1-8,ox1-4,oy1-6),box(ox0+1,oy1-10,ox0+3,oy1-8)]
            p['defender_positions'][site]=[ox1-2,oy1-3]
        else:
            role=next((k for k,v in roles.items() if v==node),None)
            kind='deployment' if role in ('T','CT') else 'courtyard' if role in ('Mid','Mid2') else 'interior' if node in investment_nodes else 'circulation'
            add_space(sid,shape,kind,'Deployment assignments diverge' if kind=='deployment' else 'Shared contest' if role=='Mid' else 'Staged investment threshold/territory' if node in investment_nodes else 'Purposeful approach/receiving parcel');parts=[(sid,shape)]
            cx,cy=routing_centers[node]
            if role:p['annotations'][role]=dict(point=[cx,cy])
            if node in investment_nodes:p['annotations'][investment_nodes[node]+'_investment']=dict(point=[cx,cy])
        node_spaces[node]=parts
    # All doors are placed on actual architectural shared boundaries. If local
    # partitions split a frontage, choose its longest physical aperture region.
    for i,(a,b) in enumerate(sorted(edges)):
        candidates=[]
        for sa,ga in node_spaces[a]:
            for sb,gb in node_spaces[b]:
                if sa==sb:continue
                shared=ga.boundary.intersection(gb.boundary)
                if shared.geom_type=='MultiLineString':shared=linemerge(shared)
                shared_parts=list(shared.geoms) if hasattr(shared,'geoms') else [shared]
                for part in shared_parts:
                    if isinstance(part,LineString):candidates.append((part.length,sa,sb,part))
        if not candidates:
            if node_spaces[a][0][0]==node_spaces[b][0][0]:continue
            raise SearchFailure('No shared frontage for selected circulation edge '+str((a,b)),log)
        width=max(spec['hard_constraints']['minimum_door_width_HU']/32,4)
        primary_court=any(node in site_nodes and site_settings[site_nodes[node]]=='courtyard' and other==network['T-'+site_nodes[node]+'-main'][-2] for node,other in [(a,b),(b,a)])
        transition='continuous-court' if primary_court else 'offset-threshold' if (a in important or b in important) and (a in site_nodes or b in site_nodes) else 'flush'
        if primary_court:width=max(width,min(7,max(length for length,_,_,_ in candidates)-2))
        fractions=[.35,.65,.5,.25,.75] if transition=='offset-threshold' else [.5,.65,.35,.75,.25]
        # Entry location adapts to usable frontage after partitions/attached masses.
        fixtures=unary_union([Polygon(m['boundary']) for m in p['internal_masses']]).buffer(.9)
        chosen=None
        for _,sa,sb,line in sorted(candidates,key=lambda x:-x[0]):
            for f in fractions:
                center=line.length*f
                if center-width/2<1 or center+width/2>line.length-1:continue
                aperture=LineString([line.interpolate(center-width/2),line.interpolate(center+width/2)])
                if not aperture.intersects(fixtures):chosen=aperture;break
            if chosen is not None:break
        if chosen is None:raise SearchFailure('No clear aperture on jointly chosen frontage',log)
        purposes=[rid for rid,path in network.items() if any(set((x,y))==set((a,b)) for x,y in zip(path,path[1:]))]
        p['openings'].append(dict(id='opening_'+str(i),spaces=[sa,sb],aperture=list(chosen.coords),transition=transition,purpose=' / '.join(purposes)))
    # Choose plant-edge cover AFTER the real entrances. The old common western
    # cover location could leave a nominally clear door but trap player movement
    # immediately behind it. Keep a full turning/approach envelope clear.
    for site,candidates in plant_cover_candidates.items():
        complex_ids={site+'_objective',site+'_vestibule'}
        protected=unary_union([LineString(o['aperture']).buffer(3.5,cap_style=2) for o in p['openings'] if set(o['spaces'])&complex_ids])
        objective=next(g for sid,g in node_spaces[roles[site]] if sid==site+'_objective')
        chosen=None
        for option in candidates:
            if not objective.buffer(-.8,join_style=2).covers(option) or option.intersects(protected):continue
            if any(option.distance(Point(q))<1.2 for q in [p['annotations'][site]['point'],p['defender_positions'][site]]):continue
            chosen=option;break
        if chosen is not None:mass(site+'_low_cover',chosen,48,'Plant-edge crouched protection; selected outside actual entry/turning envelopes, does not block standing visibility')
        log.append(dict(stage='plant_cover',site=site,placed=chosen is not None,boundary=list(chosen.exterior.coords)[:-1] if chosen is not None else None,purpose='Plant protection with 112-HU aperture turning envelope; omitted if no safe shared-rule choice.'))
    def center(node):
        return list(routing_centers[node])
    for site in ('A','B'):
        main=network['T-'+site+'-main'];defense=network['CT-'+site+'-deploy'];alt=network[('Mid-' if mid else 'local-')+site]
        p['annotations'][site+'_staging']=dict(point=center(main[-2]));p['annotations'][site+'_receiving']=dict(point=center(defense[-2]));p['annotations'][site+'_secondary']=dict(point=center(alt[-2]));p['annotations'][site+'_split']=dict(point=center(alt[0]))
        p['route_contracts']['T-'+site+'-main']=['T']+([site+'_investment'] if site+'_investment' in p['annotations'] else [])+[site+'_staging',site]
        if mid:p['annotations'][site+'_transfer']=dict(point=center(alt[-3]))
        p['route_contracts']['T-'+site+'-secondary']=['T','Mid' if mid else site+'_split']+([site+'_transfer'] if mid else [])+[site+'_secondary',site]
        p['route_contracts']['CT-'+site+'-deploy']=['CT',site+'_receiving',site]
        p['route_contracts'][site+'-retreat']=[site,site+'_receiving','CT']
    p['route_contracts']['CT-rotate']=['A','CT' if spec['gameplay']['defender_rotation']=='rear' else 'Mid','B']
    if mid:p['route_contracts'].update({'T-Mid':['T','Mid'],'CT-Mid':['CT','Mid']})
    # Route intents traverse declared architectural territory, rather than a
    # shortest path that could enter an objective before its staging waypoint.
    # Actual geometry still establishes each leg; centers never create floor.
    for site in ('A','B'):
        main=network['T-'+site+'-main'];defense=network['CT-'+site+'-deploy'];alt=network[('Mid-' if mid else 'local-')+site]
        alt_full=network['T-Mid'][:-1]+alt if mid else main[:main.index(alt[0])]+alt
        for rid,nodes in [('T-'+site+'-main',main),('T-'+site+'-secondary',alt_full),('CT-'+site+'-deploy',defense),(site+'-retreat',list(reversed(defense)))]:
            q=[center(n) for n in nodes];q[0]=p['annotations']['T' if rid.startswith('T') else 'CT' if rid.startswith('CT') else site]['point'];q[-1]=p['annotations']['CT' if rid.endswith('retreat') else site]['point'];p['physical_route_waypoints'][rid]=q
            p['physical_route_leg_spaces'][rid]=[sorted({sid for n in (u,v) for sid,g in node_spaces[n]}) for u,v in zip(nodes,nodes[1:])]
    for team in ('T','CT'):
        if mid:
            p['physical_route_waypoints'][team+'-Mid']=[center(n) for n in network[team+'-Mid']]
            p['physical_route_leg_spaces'][team+'-Mid']=[sorted({sid for n in (u,v) for sid,g in node_spaces[n]}) for u,v in zip(network[team+'-Mid'],network[team+'-Mid'][1:])]
    if spec['gameplay']['defender_rotation']=='rear':
        rotation=list(reversed(network['CT-A-deploy']))+network['CT-B-deploy'][1:]
    else:rotation=list(reversed(network['Mid-A']))+network['Mid-B'][1:]
    p['physical_route_waypoints']['CT-rotate']=[center(n) for n in rotation];p['physical_route_waypoints']['CT-rotate'][0]=p['annotations']['A']['point'];p['physical_route_waypoints']['CT-rotate'][-1]=p['annotations']['B']['point']
    p['physical_route_leg_spaces']['CT-rotate']=[sorted({sid for n in (u,v) for sid,g in node_spaces[n]}) for u,v in zip(rotation,rotation[1:])]
    bind_route_roles(p,network,roles,node_spaces,sequences)
    if mid:
        spine=network['Mid-spine'];p['mid_spaces']=sorted({sid for n in spine for sid,g in node_spaces[n]})
        p['mid_program']=dict(organization=organization,territory_nodes=[list(n) for n in spine],branches={site:dict(branch_node=list(roles['Mid'] if site=='A' else roles['Mid2']),transfer_node=list(network['Mid-'+site][-3]),entry_preparation_node=list(network['Mid-'+site][-2]),mode='approach_handoff' if site in p['mid_handoffs'] else 'separate_entry',purpose='Transfer into primary preparation; shares final entry, not a new independent attack entrance' if site in p['mid_handoffs'] else 'Control unlocks committed transfer territory before a separate site entrance') for site in ('A','B')},scope='Distributed Mid exits; no immediate objective adjacency. Timing/control not established by labels.')
        p['role_bindings'].append(dict(id='Mid-contest',kind='first_contest',purpose='Shared contested territory; independent team access with distributed approach exits',spaces=p['mid_spaces']))
    p['decision_log'].append(dict(stage='composition',parcels_dimensions=dict(x=xs,y=ys),role_cells={k:list(v) for k,v in roles.items()},selected_edges=[[list(a),list(b)] for a,b in sorted(edges)],site_settings=site_settings,continuous_galleries=list(merged_shapes),width_rules=dict(aisle_HU=aisle*32,receiving_staging_dimensions_HU=[v*32 for v in proportion],deployment_dimensions_HU=[v*32 for v in proportion],Mid_dimensions_HU=[576,576],note='Flush/offset actual openings, broad court mouth and one attached bank/passing bay per qualifying long run; no universal tapered shoulder.'),unused_parcels='Inaccessible building masses; not auto-connected',backtracking='Earlier main/defender assignments and role placement revisited before local architecture.'))
    return p

def validate(spec,p,c):
    physical=[];adherence=[];warnings=[];a={k:v['point'] for k,v in p['annotations'].items()}
    raw=DerivedNavigation(c);clear=dict(c,walkable=c['walkable'].buffer(-.5,join_style=2));nav=DerivedNavigation(clear)
    if (len(c['walkable'].geoms) if hasattr(c['walkable'],'geoms') else 1)!=1:physical.append('Disconnected walkable components')
    audit=observed_openings(p,c)
    if audit['unintended_openings']:physical.append('Undeclared passable opening')
    widths=[]
    for o in p['openings']:
        line=LineString(o['aperture']);v=np.array(o['aperture'][1])-o['aperture'][0];v=v/np.linalg.norm(v);n=np.array([-v[1],v[0]])*.8
        measured=line.intersection(c['walkable']).intersection(translate(c['walkable'],xoff=n[0],yoff=n[1])).intersection(translate(c['walkable'],xoff=-n[0],yoff=-n[1])).length*32
        widths.append(dict(id=o['id'],nominal_HU=line.length*32,actual_HU=measured))
        if abs(measured-line.length*32)>1e-5:physical.append('Aperture interference: '+o['id'])
        if measured<spec['hard_constraints']['minimum_door_width_HU']-1e-5:physical.append('Opening below requested width: '+o['id'])
    routes={};leg_navs={}
    for rid,places in p['route_contracts'].items():
        points=[];length=0;valid=True
        intended=p['physical_route_waypoints'][rid]
        for index,(first,last) in enumerate(zip(intended,intended[1:])):
            ids=tuple(p['physical_route_leg_spaces'][rid][index])
            if ids not in leg_navs:
                allowed=unary_union([c['spaces'][sid] for sid in ids]);leg_navs[ids]=DerivedNavigation(dict(c,walkable=clear['walkable'].intersection(allowed)))
            path=leg_navs[ids].path(first,last)
            if not path:valid=False;break
            points.extend(path['points'] if not points else path['points'][1:]);length+=path['length']
        shortest=nav.path(a[places[0]],a[places[-1]])
        routes[rid]=dict(places=places,path=dict(points=points,length_HU=length*32) if valid else None,
                        scope='Ordered architectural intent in the declared adjacent rooms/galleries on each leg; unrestricted shortest travel reported separately. This does not constrain player choice.',
                        unrestricted_shortest_length_HU=shortest['length']*32 if shortest else None,unrestricted_path=shortest)
        if not valid:physical.append('Required player-clear route unreachable: '+rid)
    for k,point in {**a,**p['defender_positions']}.items():
        if not clear['walkable'].covers(Point(point)):physical.append('Role/holding marker lacks player clearance: '+k)
    main_cap=spec['hard_constraints']['maximum_main_route_HU']
    if main_cap:
        for rid in ['T-A-main','T-B-main']:
            path=routes[rid]['path']
            if path and path['length_HU']>main_cap:adherence.append('Main route exceeds requested cap: '+rid)
    # Gate independently checks network structure AND actual floor connections.
    graph=nx.Graph()
    for path in p['strategic_network'].values():graph.add_edges_from(zip(map(tuple,path),map(tuple,path[1:])))
    roles={k:tuple(v) for k,v in p['decision_log'][-1]['role_cells'].items()}
    blocked_sites=unary_union([Polygon(s['boundary']) for s in p['spaces'] if s['id'].startswith(('A_objective','A_vestibule','B_objective','B_vestibule'))])
    bypass=DerivedNavigation(c,blocked=blocked_sites).path(a['T'],a['CT'])
    mid=spec['gameplay']['mid']=='contested'
    mainA=set(map(tuple,p['strategic_network']['T-A-main'][1:-1]));mainB=set(map(tuple,p['strategic_network']['T-B-main'][1:-1]))
    if mainA&mainB:adherence.append('Main commitments converge before sites')
    if not mid and bypass:adherence.append('No-Mid attacker site-free access to CT circulation')
    if mid:
        m=roles['Mid']
        for team in ('T','CT'):
            g=graph.copy();g.remove_nodes_from([roles['A'],roles['B'],roles['CT' if team=='T' else 'T']])
            if not nx.has_path(g,roles[team],m):adherence.append(team+' lacks independent Mid access')
        mid_space=unary_union([c['spaces'][sid] for sid in p['mid_spaces']]) if p.get('mid_spaces') else c['spaces']['parcel_'+str(m[0])+'_'+str(m[1])]
        physical_mid_bypass=DerivedNavigation(c,blocked=blocked_sites.union(mid_space)).path(a['T'],a['CT'])
        if physical_mid_bypass:adherence.append('Unintended site-free bypass around contested Mid')
        for site in ('A','B'):
            alt=p['strategic_network']['Mid-'+site]
            shared=set(map(tuple,alt[1:-1]))&set(map(tuple,p['strategic_network']['T-'+site+'-main'][1:-1]))
            expected=set()
            if site in p.get('mid_handoffs',[]):
                main_path=p['strategic_network']['T-'+site+'-main']
                declared=p.get('mid_program',{}).get('branches',{}).get(site,{}).get('handoff_node') or main_path[-2]
                expected={tuple(n) for n in main_path[main_path.index(declared):-1]}
            if shared!=expected:adherence.append('Undeclared Mid approach merge before '+site)
            if p.get('mid_program'):
                branch=tuple(p['mid_program']['branches'][site]['branch_node']);tail=alt[alt.index(list(branch)):]
                if len(tail)<4:adherence.append('Mid exit lacks intermediate transfer and entry preparation: '+site)
                if tuple(alt[-3]) in (roles['Mid'],roles.get('Mid2')):adherence.append('Mid transfer collapsed into central contest: '+site)
        t=routes['T-Mid']['path'];ct=routes['CT-Mid']['path']
        if t and ct:
            ratio=max(t['length_HU'],ct['length_HU'])/min(t['length_HU'],ct['length_HU'])
            if ratio>1.6:warnings.append('Mid arrival distances differ by ratio '+str(round(ratio,2))+'; no calibrated timing.')
            if ratio>CONFIG['mid_distance_ratio_gate']:adherence.append('Mid distance feasibility screen exceeds 2.5:1; does not establish contestability')
    sectors={};actual_ingresses={};handoff_junctions={}
    for site in ('A','B'):
        primary=p['strategic_network']['T-'+site+'-main'];secondary=p['strategic_network'][('Mid-' if mid else 'local-')+site];defense=p['strategic_network']['CT-'+site+'-deploy']
        free=p.get('free_node_positions')
        def position(q):return np.array(free[str(tuple(q))]) if free else np.array(q)
        vectors=[position(route[-1])-position(route[-2]) for route in (primary,secondary,defense)]
        if p.get('measure_entry_faces'):
            # Site-complex opening orientation is measured from the actual
            # aperture face. A room centroid vector is a poor proxy when
            # preparation and the objective occupy substantial L-shaped spaces.
            measured=[]
            complex_ids={site+'_objective',site+'_vestibule'}
            for rid in ['T-'+site+'-main','T-'+site+'-secondary','CT-'+site+'-deploy']:
                path=routes[rid]['path'];found=[]
                if path:
                    movement=LineString(path['points'])
                    for opening in p['openings']:
                        if len(set(opening['spaces'])&complex_ids)!=1:continue
                        face=LineString(opening['aperture']);cut=movement.intersection(face)
                        if cut.is_empty:continue
                        tangent=np.array(face.coords[-1])-face.coords[0];normal=np.array([-tangent[1],tangent[0]])
                        interior=np.array(c['spaces'][next(s for s in opening['spaces'] if s in complex_ids)].representative_point().coords[0])
                        if np.dot(normal,interior-np.array(face.centroid.coords[0]))<0:normal=-normal
                        found.append((movement.project(cut.centroid),normal))
                measured.append(min(found,key=lambda x:x[0])[1] if found else None)
            if all(x is not None for x in measured):vectors=measured
        angles=[math.degrees(math.acos(float(np.clip(np.dot(vectors[0],v)/np.linalg.norm(vectors[0])/np.linalg.norm(v),-1,1)))) for v in vectors[1:]]
        sectors[site]=dict(secondary_angle=angles[0],defensive_angle=angles[1],scope='Actual aperture-face orientation; interior clearing threshold is separate.' if p.get('measure_entry_faces') else 'Physical external site-complex opening sector; interior clearing threshold is separate.')
        handoff=site in p.get('mid_handoffs',[])
        if (angles[1] if handoff else min(angles))<60:adherence.append('Equivalent site-complex ingress: '+site)
        complex_spaces={s['id'] for s in p['spaces'] if s['id'] in (site+'_objective',site+'_vestibule')}
        ingresses=[]
        for rid in ['T-'+site+'-main','T-'+site+'-secondary','CT-'+site+'-deploy']:
            path=routes[rid]['path'];found=None
            if path:
                points=path['points'];line=LineString(points);candidates=[]
                for opening in p['openings']:
                    pair=set(opening['spaces'])
                    if len(pair&complex_spaces)!=1:continue
                    aperture=LineString(opening['aperture']);cross=line.intersection(aperture)
                    if not cross.is_empty:candidates.append((line.project(cross.centroid),opening))
                if candidates:
                    _,o=min(candidates,key=lambda item:item[0]);found=o['id']
            ingresses.append(found)
            if not found:adherence.append('Cannot observe actual site-complex ingress: '+rid)
        actual_ingresses[site]=dict(primary=ingresses[0],secondary=ingresses[1],defense=ingresses[2])
        if ingresses[0] is not None and ingresses[0]==ingresses[1] and not handoff:adherence.append('Strategically equivalent actual primary/secondary site entrance: '+site)
        if handoff:
            if ingresses[0]!=ingresses[1]:adherence.append('Declared approach handoff does not use shared final entrance: '+site)
            main=p['strategic_network']['T-'+site+'-main'];alt=p['strategic_network']['Mid-'+site]
            declared=p.get('mid_program',{}).get('branches',{}).get(site,{}).get('handoff_node') or main[-2]
            before_main=main[:main.index(declared)];before_alt=alt[:alt.index(declared)]
            if set(map(tuple,before_main))&set(map(tuple,before_alt)):adherence.append('Handoff arrivals collapse before declared junction: '+site)
            junction=next((sid for sid,g in c['spaces'].items() if g.covers(Point(a[site+'_staging']))),None);incoming=[]
            for rid in ['T-'+site+'-main','T-'+site+'-secondary']:
                path=routes[rid]['path'];seen=[]
                if path:
                    line=LineString(path['points'])
                    for opening in p['openings']:
                        pair=set(opening['spaces'])
                        if junction not in pair or pair&complex_spaces:continue
                        cross=line.intersection(LineString(opening['aperture']))
                        if not cross.is_empty:seen.append((line.project(cross.centroid),opening['id']))
                incoming.append(min(seen)[1] if seen else None)
            handoff_junctions[site]=dict(space=junction,primary_arrival=incoming[0],mid_arrival=incoming[1],shared_site_entry=ingresses[0],counted_final_entries=1)
            if None in incoming or incoming[0]==incoming[1]:adherence.append('Handoff lacks distinct physical arrival openings: '+site)
            warnings.append(site+' Mid approach joins primary preparation: one final site entry, not two distinct attack entries. Information/control and tactical value unresolved.')
    if not mid:
        ct_space=c['spaces']['parcel_'+str(roles['CT'][0])+'_'+str(roles['CT'][1])]
        shortest=nav.path(a['A_receiving'],a['B_receiving'])
        if shortest and LineString(shortest['points']).intersection(ct_space).length<=1:adherence.append('Shortest rear receiving rotation bypasses deployment')
    if mid and spec['gameplay']['defender_rotation']=='rear':
        # Contested Mid inherently offers another rotation; flag rather than
        # pretend its absence can be geometrically enforced.
        warnings.append('Mid permits an alternative control-dependent rotation; rear is an assigned safe-side route, not the only physical path.')
    if mid and p.get('mid_program'):
        requested=spec['gameplay'].get('mid_access_mode','auto');wanted=1 if requested=='one_approach_handoff' else 0
        if len(p.get('mid_handoffs',[]))!=wanted:adherence.append('Mid handoff count does not match requested mode')
    role_checks=[]
    opening_graph=nx.Graph();opening_graph.add_nodes_from(c['spaces']);opening_graph.add_edges_from(o['spaces'] for o in p['openings'])
    for binding in p.get('role_bindings',[]):
        ids=binding['spaces'];connected=bool(ids) and nx.is_connected(opening_graph.subgraph(ids))
        role_checks.append(dict(id=binding['id'],spaces=ids,connected_support=connected,purpose=binding['purpose']))
        if not connected:adherence.append('Disconnected or empty gameplay role support: '+binding['id'])
    # Local architecture must not create a gateway into another commitment.
    # Existing no-Mid site-blocked T/CT gate and independent main reservations
    # remain in force; role metadata cannot authorize additional shortcuts.
    sep=math.dist(a['A'],a['B'])*32
    setting=p['decision_log'][-1]['site_settings'];preference=dict(site_setting=setting,site_separation_HU=sep)
    expected=spec['architecture']['site_setting'];expected={'A':'courtyard','B':'interior'} if expected=='mixed' else {'A':expected,'B':expected}
    if setting!=expected:adherence.append('Actual site architecture does not match resolved request')
    for site,declared in setting.items():
        partition=[o for o in p['openings'] if o['id']==site+'_interior_threshold']
        has_vestibule=site+'_vestibule' in c['spaces']
        if declared=='interior' and (not partition or not has_vestibule):adherence.append('Interior preference lacks physical vestibule and threshold: '+site)
        if declared=='courtyard' and has_vestibule:adherence.append('Courtyard preference unexpectedly partitioned as interior: '+site)
    if spec['gameplay']['site_commitment'] in ('staged','mixed'):
        for site in ('A','B'):
            if spec['gameplay']['site_commitment']=='mixed' and site=='A':continue
            if len(p['strategic_network']['T-'+site+'-main'])<4:adherence.append('Staged access lacks pre-entry investment: '+site)
            if site+'_investment' not in a:adherence.append('Staged access lacks physical investment room: '+site)
    if spec['architecture']['site_separation']=='separated' and sep<2300:adherence.append('Sites not physically separated enough for declared rule (2300 HU)')
    if spec['architecture']['site_separation']=='adjacent' and sep>2400:adherence.append('Sites too far for adjacent rule (2400 HU)')
    warnings.append('Timing, utility, encounter control, balance, retake safety and 3D runtime collision remain unverified.')
    result=dict(physical_violations=list(dict.fromkeys(physical)),adherence_violations=list(dict.fromkeys(adherence)),warnings=warnings,
                physical_pass=not physical,request_pass=not adherence,routes=routes,opening_widths=widths,opening_audit=audit,entry_sectors=sectors,
                site_free_T_CT_path=bypass,architecture_evidence=preference,actual_site_ingresses=actual_ingresses,handoff_junctions=handoff_junctions,role_support_checks=role_checks,
                soft_preference_observations=dict(walkable_fraction=c['walkable'].area/c['envelope'].area,
                  requested=spec['soft_preferences'],scope='Preferences influence span, building depth and placement sampling; no quality score or guaranteed satisfaction.'),
                gameplay_accepted=False,visually_accepted=False,stage4_authorized=False,
                timing_verified=False)
    result['compactness']=assess(spec,p,c,result)
    if not result['compactness']['achieved']:result['warnings'].append('Compact preference not fully achieved; see complete-route targets. Physical/request gates unchanged.')
    return result
