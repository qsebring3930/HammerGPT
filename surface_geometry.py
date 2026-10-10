"""Editable, welded Hammer surface topology with explicit boundary half edges."""
import copy
import math

from connected_geometry import GRID, elevation, floor_cells, validate_floor
from hammergpt import fresh_copy, get, set_value, vector, walk


def cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def unit(v):
    length=math.sqrt(sum(x*x for x in v))
    if length<1e-8:
        raise ValueError('Degenerate surface face')
    return [x/length for x in v]


def make_surface(template,node_id,polygons):
    mesh=fresh_copy(template,node_id); data=get(mesh,'meshData')
    vertices=[]; lookup={}; faces=[]
    for polygon in polygons:
        face=[]
        for point in polygon:
            key=tuple(point)
            if key not in lookup:
                lookup[key]=len(vertices); vertices.append(key)
            face.append(lookup[key])
        if len(set(face))!=len(face):
            raise ValueError('Repeated face vertex')
        faces.append(face)
    ends=[]; opposites=[]; nexts=[]; edge_faces=[]; edge_data=[]; outgoing=[-1]*len(vertices)
    directed={}; face_starts=[]; bases=[]
    for fi,face in enumerate(faces):
        p,q,r=[vertices[v] for v in face[:3]]
        u=unit([q[i]-p[i] for i in range(3)])
        n=unit(cross(u,[r[i]-q[i] for i in range(3)])); v=cross(n,u); bases.append((u,v,n))
        loop=[]
        for a,b in zip(face,face[1:]+face[:1]):
            if (a,b) not in directed:
                e=len(ends); directed[a,b]=e; directed[b,a]=e+1
                ends.extend((b,a)); opposites.extend((e+1,e)); nexts.extend((-1,-1)); edge_faces.extend((-1,-1)); edge_data.extend((e//2,e//2))
            e=directed[a,b]
            if edge_faces[e]!=-1:
                raise ValueError('Nonmanifold or inconsistent face winding')
            edge_faces[e]=fi; outgoing[a]=e; loop.append(e)
        for a,b in zip(loop,loop[1:]+loop[:1]):
            nexts[a]=b
        face_starts.append(loop[0])
    boundary={}
    for e,fi in enumerate(edge_faces):
        if fi==-1:
            start=ends[opposites[e]]
            if start in boundary:
                raise ValueError('Nonmanifold boundary vertex')
            boundary[start]=e
    for e,fi in enumerate(edge_faces):
        if fi==-1:
            nexts[e]=boundary[ends[e]]
    arrays={'vertexEdgeIndices':outgoing,'vertexDataIndices':list(range(len(vertices))),
            'edgeVertexIndices':ends,'edgeOppositeIndices':opposites,'edgeNextIndices':nexts,
            'edgeFaceIndices':edge_faces,'edgeDataIndices':edge_data,
            'edgeVertexDataIndices':list(range(len(ends))),
            'faceEdgeIndices':face_starts,'faceDataIndices':list(range(len(faces)))}
    for key,values in arrays.items():
        set_value(data,key,list(map(str,values)))
    counts={'vertexData':len(vertices),'faceVertexData':len(ends),'edgeData':len(ends)//2,'faceData':len(faces)}
    for key,count in counts.items():
        group=get(data,key); set_value(group,'size',str(count))
        for stream in get(group,'streams'):
            semantic=get(stream,'semanticName'); typ=stream.attrs['data'][0]
            values=[]
            for index in range(count):
                if key=='vertexData' and semantic=='position':
                    value=vector(vertices[index])
                elif key=='faceVertexData':
                    fi=edge_faces[index] if edge_faces[index]>=0 else edge_faces[opposites[index]]
                    u,v,n=bases[fi]; point=vertices[ends[index]]
                    if semantic=='texcoord': value=vector((sum(a*b for a,b in zip(point,u))/128,sum(a*b for a,b in zip(point,v))/128))
                    elif semantic=='normal': value=vector(n)
                    elif semantic=='tangent': value=vector((*u,1))
                    else: raise ValueError('Unsupported corner stream: '+semantic)
                elif key=='faceData' and semantic=='textureAxisU': value=vector((*bases[index][0],0))
                elif key=='faceData' and semantic=='textureAxisV': value=vector((*bases[index][1],0))
                else:
                    old=get(stream,'data'); value=old[0] if old else ('0' if typ=='int_array' else '')
                values.append(value)
            set_value(stream,'data',values)
    subdiv=get(data,'subdivisionData'); set_value(subdiv,'subdivisionLevels',['0']*len(ends)); set_value(subdiv,'streams',[])
    set_value(mesh,'origin','0 0 0'); set_value(mesh,'angles','0 0 0'); set_value(mesh,'scales','1 1 1')
    validate_topology(mesh)
    return mesh


def validate_topology(mesh):
    data=get(mesh,'meshData')
    arrays={k:list(map(int,get(data,k))) for k in ('edgeVertexIndices','edgeOppositeIndices','edgeNextIndices','edgeFaceIndices','faceEdgeIndices')}
    ends,opp,nxt,face,starts=(arrays[k] for k in arrays)
    vertices=int(get(get(data,'vertexData'),'size'))
    for e in range(len(ends)):
        if not (0<=ends[e]<vertices and 0<=opp[e]<len(ends) and 0<=nxt[e]<len(ends)):
            raise ValueError('Topology index out of bounds')
        if opp[opp[e]]!=e or ends[opp[nxt[e]]]!=ends[e] or face[nxt[e]]!=face[e]:
            raise ValueError('Broken half-edge connectivity')
    covered=set()
    for fi,start in enumerate(starts):
        e=start; loop=set()
        while e not in loop:
            if face[e]!=fi: raise ValueError('Face owns wrong edge')
            loop.add(e); e=nxt[e]
        if e!=start or len(loop)<3: raise ValueError('Invalid face loop')
        covered.update(loop)
    if covered!={e for e,f in enumerate(face) if f>=0}: raise ValueError('Unreferenced face edges')
    for key in ('vertexData','faceVertexData','edgeData','faceData'):
        group=get(data,key); count=int(get(group,'size'))
        if any(len(get(s,'data'))!=count for s in get(group,'streams')): raise ValueError('Stream size mismatch')
    return {'vertices':vertices,'faces':len(starts),'half_edges':len(ends),'boundary_half_edges':sum(f<0 for f in face)}


def create_surface_blockout(roots,plan):
    cells=floor_cells(plan); z=elevation(plan,cells); validation=validate_floor(cells,z); polygons=[]
    outline=plan['design_choices'].get('floor_polygon_override')
    if outline is not None:
        from simplify_section import triangulate
        if any(r['center'][2]!=0 for r in plan['design_choices']['regions']):
            raise ValueError('Simplified polygon mode currently supports flat studies only')
        points=[(p[0],p[1],0) for p in outline]
        polygons.extend([[points[i] for i in triangle] for triangle in triangulate(outline)])
        for a,c in zip(points,points[1:]+points[:1]):
            polygons.append([c,a,(a[0],a[1],256),(c[0],c[1],256)])
        validation['floor_validation_basis']='Simple polygon and area-matched triangulation; cell connectivity describes input study only'
    for x,y in ([] if outline is not None else sorted(cells)):
        l,r=x*GRID,(x+1)*GRID; b,t=y*GRID,(y+1)*GRID
        height=lambda x,y:z(x,y) if getattr(z,'xy',False) else z(x)
        corners=[(l,b,height(l,b)),(r,b,height(r,b)),(r,t,height(r,t)),(l,t,height(l,t))]
        if getattr(z,'xy',False):
            polygons.extend(([corners[0],corners[1],corners[2]],[corners[0],corners[2],corners[3]]))
        else:polygons.append(corners)
        for neighbor,a,c in [((x,y-1),corners[0],corners[1]),((x+1,y),corners[1],corners[2]),
                             ((x,y+1),corners[2],corners[3]),((x-1,y),corners[3],corners[0])]:
            if neighbor not in cells:
                polygons.append([c,a,(a[0],a[1],a[2]+256),(c[0],c[1],c[2]+256)])
    result=copy.deepcopy(roots); root=next(r for r in result if r.kind=='CMapRootElement'); world=get(root,'world')
    templates=list(walk(world)); cube=next(n for n in templates if n.kind=='CMapMesh')
    light=next(n for n in templates if n.kind=='CMapEntity' and get(get(n,'entity_properties'),'classname')=='light_omni2')
    first=max(int(get(n,'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs)+1
    surface=make_surface(cube,first,polygons); children=[surface]; validation.update(validate_topology(surface))
    for room in plan['design_choices']['regions']:
        lamp=fresh_copy(light,first+len(children)); x,y,_=room['center']
        set_value(lamp,'origin',vector((x,y,(z(x,y) if getattr(z,'xy',False) else z(x))+192))); props=get(lamp,'entity_properties')
        set_value(props,'targetname','hammergpt_'+room['id']); set_value(props,'range','1400'); children.append(lamp)
    set_value(world,'children',children); camera=get(root,'defaultcamera')
    set_value(camera,'position','0 -1600 1800'); set_value(camera,'lookat','0 0 0')
    return result,[{'label':'welded_gameplay_surfaces','node_id':get(surface,'nodeID')}],validation
