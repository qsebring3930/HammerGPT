"""Build a continuous grid-aligned floor union with walls on its outer boundary."""
import copy
import math
from collections import defaultdict

from hammergpt import fresh_copy, get, make_box, positions, set_value, vector, walk


GRID = 64


def floor_cells(plan):
    design=plan['design_choices']; rooms={r['id']:r for r in design['regions']}
    if 'floor_cell_override' in design:
        values=design['floor_cell_override']
        if not values or len(values)>100000 or any(len(c)!=2 or any(type(v)!=int or abs(v)>2048 for v in c) for c in values):
            raise ValueError('Invalid reference study floor cells')
        return {tuple(c) for c in values}
    cells=set()
    def rectangle(x0,y0,x1,y1):
        for x in range(math.floor(x0/GRID), math.ceil(x1/GRID)):
            for y in range(math.floor(y0/GRID), math.ceil(y1/GRID)):
                cells.add((x,y))
    for room in rooms.values():
        x,y,_=room['center']; w,d,_=room['size']
        rectangle(x-w/2,y-d/2,x+w/2,y+d/2)
    width=design['corridor_width_units']
    for edge in design['connections']:
        if 'path_xy' in edge:
            points=edge['path_xy']
            if len(points)<2:raise ValueError('Explicit corridor needs at least two points')
            for (x0,y0),(x1,y1) in zip(points,points[1:]):
                if x0!=x1 and y0!=y1:raise ValueError('Grid corridor segments must be axis aligned')
                rectangle(min(x0,x1)-width/2,min(y0,y1)-width/2,max(x0,x1)+width/2,max(y0,y1)+width/2)
            continue
        a,b=rooms[edge['source']],rooms[edge['target']]
        x0,y0,_=a['center']; x1,y1,_=b['center']
        # Route via an axis-aligned elbow and overlap both room interiors.
        rectangle(min(x0,x1)-width/2,y0-width/2,max(x0,x1)+width/2,y0+width/2)
        rectangle(x1-width/2,min(y0,y1)-width/2,x1+width/2,max(y0,y1)+width/2)
    return cells


def elevation(plan,cells):
    if 'floor_vertex_heights' in plan['design_choices']:
        values=plan['design_choices']['floor_vertex_heights']
        lookup={(int(x),int(y)):float(z) for x,y,z in values}
        expected={(x+dx,y+dy) for x,y in cells for dx,dy in ((0,0),(1,0),(1,1),(0,1))}
        if set(lookup)!=expected or any(not math.isfinite(z) for z in lookup.values()):raise ValueError('Invalid floor vertex height field')
        def field(x,y=None):
            if y is None:raise ValueError('Height-field elevation requires XY')
            return lookup[round(x/GRID),round(y/GRID)]
        field.xy=True
        return field
    raised=[r for r in plan['design_choices']['regions'] if r['center'][2]!=0]
    if len(raised)>1:
        raise ValueError('This connected prototype supports one raised site')
    if not raised:
        return lambda x:0
    room=raised[0]; x=room['center'][0]; half=room['size'][0]/2; height=room['center'][2]
    if height<0:
        raise ValueError('Negative raised-site heights are unsupported')
    low=math.floor((x-half)/GRID)*GRID; high=math.ceil((x+half)/GRID)*GRID
    run=math.ceil(max(height*4,GRID)/GRID)*GRID
    def z(x):
        return height*max(0,min(1,(x-(low-run))/run,((high+run)-x)/run))
    return z


def validate_floor(cells,z):
    if not cells:
        raise ValueError('No floor cells')
    reached={next(iter(cells))}; todo=list(reached)
    while todo:
        x,y=todo.pop()
        for neighbor in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if neighbor in cells and neighbor not in reached:
                reached.add(neighbor); todo.append(neighbor)
    if reached!=cells:
        raise ValueError('Floor contains disconnected islands')
    for x,y in cells:
        if getattr(z,'xy',False):
            for a,b in (((x,y),(x+1,y)),((x+1,y),(x+1,y+1)),((x+1,y+1),(x,y+1)),((x,y+1),(x,y))):
                if abs(z(b[0]*GRID,b[1]*GRID)-z(a[0]*GRID,a[1]*GRID))/GRID>.125+1e-6:raise ValueError('Height field slope exceeds configured per-axis limit')
            continue
        if abs(z((x+1)*GRID)-z(x*GRID))/GRID>.25+1e-6:
            raise ValueError('Floor slope exceeds 1:4')
    return {'connected_floor_cells':len(cells),'floor_components':1,'maximum_slope':.25,
            'join_method':'Adjacent floor strips share identical edge positions and elevations'}


def create_connected_blockout(roots,plan):
    cells=floor_cells(plan); z=elevation(plan,cells); validation=validate_floor(cells,z)
    result=copy.deepcopy(roots); root=next(r for r in result if r.kind=='CMapRootElement'); world=get(root,'world')
    templates=list(walk(world)); cube=next(n for n in templates if n.kind=='CMapMesh')
    light=next(n for n in templates if n.kind=='CMapEntity' and get(get(n,'entity_properties'),'classname')=='light_omni2')
    first=max(int(get(n,'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs)+1
    children=[]; manifest=[]
    def brush(center,size,label,slope=0):
        mesh=make_box(cube,first+len(children),center,size)
        if slope:
            stream=positions(mesh)
            set_value(stream,'data',[vector((x,y,v+slope*x)) for x,y,v in (map(float,p.split()) for p in get(stream,'data'))])
            for element in walk(mesh):
                if 'semanticName' in element.attrs and get(element,'semanticName')=='normal':
                    values=[]
                    for value in get(element,'data'):
                        x,y,v=map(float,value.split()); x-=slope*v; length=math.sqrt(x*x+y*y+v*v)
                        values.append(vector((x/length,y/length,v/length)))
                    set_value(element,'data',values)
        children.append(mesh)
        manifest.append({'label':label,'node_id':get(mesh,'nodeID'),'center':center,'size':size,'yaw':0,'slope':slope})
    columns=defaultdict(list)
    for x,y in cells:
        columns[x].append(y)
    for x,ys in sorted(columns.items()):
        ys=sorted(ys); start=last=ys[0]
        runs=[]
        for y in ys[1:]:
            if y!=last+1:
                runs.append((start,last)); start=y
            last=y
        runs.append((start,last))
        left,right=x*GRID,(x+1)*GRID; slope=(z(right)-z(left))/GRID
        for a,b in runs:
            brush([(left+right)/2,(a+b+1)*GRID/2,(z(left)+z(right))/2-8],
                  [GRID,(b-a+1)*GRID,16],'continuous_floor',slope)
    # Wall footprint is outside the union, so passage openings cannot be blocked by room walls.
    for x,y in sorted(cells):
        left,right=x*GRID,(x+1)*GRID; bottom,top=y*GRID,(y+1)*GRID
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
            if (x+dx,y+dy) in cells:
                continue
            if dx:
                edge=left if dx<0 else right
                brush([edge+dx*8,(bottom+top)/2,z(edge)+128],[16,GRID,256],'boundary_wall')
            else:
                edge=bottom if dy<0 else top; slope=(z(right)-z(left))/GRID
                brush([(left+right)/2,edge+dy*8,(z(left)+z(right))/2+128],
                      [GRID,16,256],'boundary_wall',slope)
    for room in plan['design_choices']['regions']:
        lamp=fresh_copy(light,first+len(children)); x,y,_=room['center']
        set_value(lamp,'origin',vector((x,y,z(x)+192)))
        props=get(lamp,'entity_properties'); set_value(props,'targetname','hammergpt_'+room['id']); set_value(props,'range','1400')
        children.append(lamp)
    set_value(world,'children',children)
    camera=get(root,'defaultcamera'); set_value(camera,'position','0 -1600 1800'); set_value(camera,'lookat','0 0 0')
    validation['wall_segments']=sum(m['label']=='boundary_wall' for m in manifest)
    return result,manifest,validation
