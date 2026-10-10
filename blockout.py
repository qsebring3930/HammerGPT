"""Generate an open platform blockout from a planner proposal, without overwriting maps."""
import argparse
import copy
import json
import math
from pathlib import Path
import tempfile

from hammergpt import convert, fresh_copy, get, make_box, parse, positions, serialize, set_value, vector, walk
from connected_geometry import create_connected_blockout
from surface_geometry import create_surface_blockout, validate_topology


def corridor(a, b):
    dx, dy = (b['center'][i]-a['center'][i] for i in range(2))
    length=math.hypot(dx,dy)
    if not length:
        raise ValueError('Connected regions must have distinct XY centers')
    ux,uy=dx/length,dy/length
    def inset(node):
        return min(node['size'][0]/2/abs(ux) if ux else math.inf,
                   node['size'][1]/2/abs(uy) if uy else math.inf)
    start=inset(a); end=length-inset(b)
    if end-start < 32:
        raise ValueError('Connected rooms overlap or leave insufficient corridor space')
    p=[a['center'][0]+ux*start,a['center'][1]+uy*start,a['center'][2]]
    q=[a['center'][0]+ux*end,a['center'][1]+uy*end,b['center'][2]]
    slope=(q[2]-p[2])/(end-start)
    if abs(slope)>.5:
        raise ValueError('Ramp is too steep for this prototype (maximum rise/run 0.5)')
    return p,q,end-start,math.degrees(math.atan2(dy,dx)),slope


def create_blockout(roots, plan):
    design=plan['design_choices']; regions=design['regions']
    nodes={r['id']:r for r in regions}
    if len(nodes)!=len(regions):
        raise ValueError('Duplicate region IDs')
    width=design['corridor_width_units']
    if not math.isfinite(width) or width<64 or width>1024:
        raise ValueError('Invalid corridor width')
    for r in regions:
        if len(r['center'])!=3 or len(r['size'])!=3 or any(not math.isfinite(v) for v in r['center']+r['size']) or any(v<=0 for v in r['size']):
            raise ValueError('Invalid region dimensions')
    result=copy.deepcopy(roots)
    root=next(r for r in result if r.kind=='CMapRootElement'); world=get(root,'world')
    templates=list(walk(world))
    cube=next(n for n in templates if n.kind=='CMapMesh')
    light=next(n for n in templates if n.kind=='CMapEntity' and get(get(n,'entity_properties'),'classname')=='light_omni2')
    first=max(int(get(n,'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs)+1
    children=[]; manifest=[]
    def slab(center,size,label,yaw=0,slope=0):
        mesh=make_box(cube,first+len(children),center,size)
        if slope:
            stream=positions(mesh)
            points=[list(map(float,p.split())) for p in get(stream,'data')]
            set_value(stream,'data',[vector((x,y,z+slope*x)) for x,y,z in points])
            for element in walk(mesh):
                if 'semanticName' in element.attrs and get(element,'semanticName')=='normal':
                    normals=[]
                    for value in get(element,'data'):
                        x,y,z=map(float,value.split()); x-=slope*z
                        norm=math.sqrt(x*x+y*y+z*z)
                        normals.append(vector((x/norm,y/norm,z/norm)))
                    set_value(element,'data',normals)
        set_value(mesh,'angles',vector((0,yaw,0)))
        children.append(mesh)
        manifest.append({'label':label,'node_id':get(mesh,'nodeID'),'center':center,'size':size,'yaw':yaw,'slope':slope})
    for r in regions:
        x,y,z=r['center']; w,d,_=r['size']
        slab([x,y,z-8],[w,d,16],r['id'])
    for edge in design['connections']:
        a,b=nodes[edge['source']],nodes[edge['target']]
        p,q,length,yaw,slope=corridor(a,b)
        slab([(p[0]+q[0])/2,(p[1]+q[1])/2,(p[2]+q[2])/2-8],
             [length,width,16],edge['source']+' -> '+edge['target'],yaw,slope)
    for r in regions:
        lamp=fresh_copy(light,first+len(children))
        set_value(lamp,'origin',vector((r['center'][0],r['center'][1],r['center'][2]+192)))
        props=get(lamp,'entity_properties')
        set_value(props,'targetname','hammergpt_'+r['id'])
        set_value(props,'range','1200')
        children.append(lamp)
    set_value(world,'children',children)
    camera=get(root,'defaultcamera')
    set_value(camera,'position','0 -1600 1400'); set_value(camera,'lookat','0 0 0')
    return result,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2',required=True,type=Path)
    parser.add_argument('--reference',required=True,type=Path)
    parser.add_argument('--proposal',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--connected',action='store_true',help='Continuous floors and outer walls with open passage entrances')
    parser.add_argument('--surfaces',action='store_true',help='Welded floor/ramp/wall faces with no hidden box faces')
    args=parser.parse_args()
    output=args.output.resolve(); manifest_path=output.with_suffix('.blockout.json')
    if output.suffix!='.vmap' or output.exists() or manifest_path.exists():
        parser.error('Choose a new .vmap output path')
    exe=args.cs2/'game/bin/win64/dmxconvert.exe'
    with tempfile.TemporaryDirectory(prefix='hammergpt-blockout-') as folder:
        folder=Path(folder); source=folder/'source.txt'; text=folder/'blockout.txt'; binary=folder/'blockout.vmap'; check=folder/'check.txt'
        convert(exe,args.reference,source,'keyvalues2')
        header,roots=parse(source.read_text(encoding='utf-8-sig'))
        plan=json.loads(args.proposal.read_text(encoding='utf-8'))
        if args.surfaces:
            result,manifest,validation=create_surface_blockout(roots,plan)
        elif args.connected:
            result,manifest,validation=create_connected_blockout(roots,plan)
        else:
            result,manifest=create_blockout(roots,plan)
            validation={}
        text.write_text(serialize(header,result),encoding='utf-8')
        convert(exe,text,binary,'binary'); convert(exe,binary,check,'keyvalues2')
        _,checked=parse(check.read_text(encoding='utf-8-sig'))
        expected=[n for r in result for n in walk(r) if n.kind=='CMapMesh']
        actual=[n for r in checked for n in walk(r) if n.kind=='CMapMesh']
        if len(expected)!=len(actual):
            raise RuntimeError('Converter changed mesh count')
        for a,b in zip(expected,actual):
            if args.surfaces:
                validate_topology(b)
                da,db=get(a,'meshData'),get(b,'meshData')
                for key in ('vertexEdgeIndices','vertexDataIndices','edgeVertexIndices','edgeOppositeIndices','edgeNextIndices','edgeFaceIndices','edgeDataIndices','edgeVertexDataIndices','faceEdgeIndices','faceDataIndices'):
                    if get(da,key)!=get(db,key):
                        raise RuntimeError('Converter changed surface topology')
            for key in ('origin','angles'):
                if any(abs(x-y)>.001 for x,y in zip(map(float,get(a,key).split()),map(float,get(b,key).split()))):
                    raise RuntimeError('Converter changed mesh transform')
            pa,pb=get(positions(a),'data'),get(positions(b),'data')
            if len(pa)!=len(pb) or any(abs(x-y)>.001 for u,v in zip(pa,pb) for x,y in zip(map(float,u.split()),map(float,v.split()))):
                raise RuntimeError('Converter changed mesh vertices')
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('xb') as destination:
            destination.write(binary.read_bytes())
        manifest_path.write_text(json.dumps({'proposal':str(args.proposal.resolve()),'meshes':manifest,'validation':validation,
            'limits':['No ceiling, cover, spawns, or objective entities; perimeter walls require --connected or --surfaces.',
                      'Surface mode has open, inward-facing walls and upward-facing floors; collision and editor rendering still require validation in Hammer.',
                      'Connected mode uses grid-aligned elbow passages and shared elevation bands around the raised site; nearby rooms may also slope.',
                      'Corridor intersections may introduce extra routes. No compile, NAV, or gameplay validation yet.']},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(output),'meshes':len(manifest),'lights':len(plan['design_choices']['regions'])}))


if __name__=='__main__':
    main()
