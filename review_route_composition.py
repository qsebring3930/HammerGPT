"""Read-only review of the predeclared route-composition experiment."""
import json,copy
from pathlib import Path
from PIL import Image,ImageDraw
from shapely.geometry import box
from map_layout import render,font
from playable_composition import compile_composition
from inspect_planar_paths import inspect

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def run():
 root=ROOT/'output/route-composition-001';out=root/'review';out.mkdir(exist_ok=False)
 folders=[ROOT/'output/nav-radar-integration-001/after-r1/seed-927611']+[root/'after-r1'/('seed-'+str(s)) for s in (927611,962117,962331)]
 candidates=[(read(f/'composition.json'),read(f/'validation.json')) for f in folders]
 compiled=[compile_composition(p) for p,v in candidates]
 bounds=[c['envelope'].bounds for c in compiled];extent=max(max(b[2]-b[0],b[3]-b[1]) for b in bounds)
 sheets=[];rows=[]
 for index,((p,v),c,f) in enumerate(zip(candidates,compiled,folders)):
  x0,y0,_,_=c['envelope'].bounds;c['envelope']=box(x0,y0,x0+extent,y0+extent)
  im=render(p,c,v,False);label=('BEFORE ' if index==0 else 'AFTER ')+str(p['seed']);d=ImageDraw.Draw(im);d.rectangle((0,0,1600,145),fill='#101923');d.text((65,30),label,font=font(38),fill='white');d.text((65,85),'Common scale: 32 HU / plan unit. Architecture and gameplay unaccepted.',font=font(21),fill='#b9cbd4');im.save(out/(('before' if index==0 else str(p['seed']))+'-clean.png'));sheets.append(im)
  if index:
   roles=im.copy();dr=ImageDraw.Draw(roles);scale=1300/extent
   def xy(q):return 150+(q[0]-x0)*scale,1450-(q[1]-y0)*scale
   # White outlines are architectural partitions, not one wall per role.
   for sid,g in c['spaces'].items():
    dr.line([xy(q) for q in g.exterior.coords],fill='#a5c4d2',width=1)
   colors={'main_approach':'#ffd47c','staging':'#ffbbdd','execute_preparation':'#ffbbdd','split_point':'#c3a7ff','first_contest':'#ff8e85','connector':'#9cdeb6','flank':'#9cdeb6','fallback':'#8caaf4','rotation_junction':'#8caaf4'}
   grouped={}
   for binding in p['role_bindings']:
    # Label each supporting space once with all its semantic purposes.
    for sid in binding['spaces']:grouped.setdefault(sid,[]).append(binding)
   legend=[]
   for n,(sid,bindings) in enumerate(grouped.items(),1):
    point=c['spaces'][sid].representative_point();pt=xy(point.coords[0]);dr.text(pt,str(n),font=font(19),fill=colors[bindings[0]['kind']],stroke_width=2,stroke_fill='#101923');legend.append({'number':n,'actual_space':sid,'roles':[r['id'] for r in bindings],'purposes':[r['purpose'] for r in bindings]})
   roles.save(out/(str(p['seed'])+'-roles.png'))
   (out/(str(p['seed'])+'-role-key.json')).write_text(json.dumps(legend,indent=2))
  inspect(f,out/(('before' if index==0 else str(p['seed']))+'-unrestricted'),True)
  rows.append({'label':label,'seed':p['seed'],'physical_pass':v['physical_pass'],'request_pass':v['request_pass'],'compactness_achieved':v['compactness']['achieved'],'spaces':len(p['spaces']),'profiles':p.get('route_sequences',{}),'routes':[{'route':rid,'ordered_HU':r['path']['length_HU'] if r['path'] else None,'unrestricted_HU':r['unrestricted_shortest_length_HU']} for rid,r in v['routes'].items()],'role_support':v.get('role_support_checks',[]),'opening_widths':v['opening_widths'],'violations':v['physical_violations']+v['adherence_violations']})
 for name,indices in [('matched',[0,1]),('new-seeds',[2,3])]:
  sheet=Image.new('RGB',(2400,1200),'#101923')
  for col,i in enumerate(indices):sheet.paste(sheets[i].resize((1200,1200)),(col*1200,0))
  sheet.save(out/(name+'.png'))
 (out/'measurements.json').write_text(json.dumps(rows,indent=2))
 print(json.dumps([{k:r[k] for k in ('label','physical_pass','request_pass','compactness_achieved','spaces')} for r in rows]))
if __name__=='__main__':run()
