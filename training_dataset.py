"""Build map-separated, masked NAV footprint examples for a local training pilot."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


SPLITS={'train':['Dust2','Cobblestone','Anubis','Tuscan','Cache','Train'],
        'validation':['Office'],'test':['Vertigo']}
SIZE=32
CELL=64


def raster(polygons,cx,cy,height):
    result=np.zeros((SIZE,SIZE),dtype=np.float32)
    xs=cx+(np.arange(SIZE)-SIZE/2+.5)*CELL
    ys=cy+(np.arange(SIZE)-SIZE/2+.5)*CELL
    for polygon in polygons:
        points=np.asarray(polygon,dtype=float)
        if abs(points[:,2].mean()-height)>48: continue
        xi=np.where((xs>=points[:,0].min()) & (xs<=points[:,0].max()))[0]
        yi=np.where((ys>=points[:,1].min()) & (ys<=points[:,1].max()))[0]
        if not len(xi) or not len(yi): continue
        xx,yy=np.meshgrid(xs[xi],ys[yi]); contained=np.zeros(xx.shape,dtype=bool)
        for a,b in zip(points,np.roll(points,-1,axis=0)):
            if abs(b[1]-a[1])<1e-9: continue
            contained^=((a[1]>yy)!=(b[1]>yy)) & (xx<(b[0]-a[0])*(yy-a[1])/(b[1]-a[1])+a[0])
        result[np.ix_(yi,xi)]=np.maximum(result[np.ix_(yi,xi)],contained)
    return result


def masked(footprint):
    known=np.zeros_like(footprint); known[:,:SIZE//2]=1
    return np.stack((footprint*known,known))


def build(corpus_path,output,samples=256,seed=20261008):
    if output.exists(): raise ValueError('Choose a new dataset directory')
    corpus=json.loads(corpus_path.read_text()); approved={r['name']:r for r in corpus['maps'] if r['user_approved']}
    flattened=[name for names in SPLITS.values() for name in names]
    if len(set(flattened))!=len(flattened): raise ValueError('Map appears in multiple splits')
    output.mkdir(parents=True); rng=np.random.default_rng(seed); records=[]; source_hashes={}; excluded=[]; used_hashes=set()
    for split,names in SPLITS.items():
        inputs=[]; targets=[]
        for name in names:
            if name not in approved or not approved[name]['nav_available']: raise ValueError('Unapproved or unavailable source: '+name)
            if approved[name].get('dataset_role')=='evaluation_only':
                raise ValueError('Reserved evaluation map cannot enter the development pilot: '+name)
            navpath=corpus_path.parent/(name.lower()+'-nav.json'); raw=navpath.read_bytes(); nav=json.loads(raw)
            source_hashes[name]={'nav_source':nav['source'],'map_source':approved[name]['source'],'nav_export_sha256':hashlib.sha256(raw).hexdigest()}
            areas=[a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff]
            polygons=[a['corners'] for a in areas]; count=0; attempts=0
            while count<samples and attempts<samples*30:
                attempts+=1; area=areas[int(rng.integers(len(areas)))]; center=np.asarray(area['corners']).mean(axis=0)
                jitter=rng.integers(-4,5,size=2)*CELL; rotation=int(rng.integers(4))
                target=np.rot90(raster(polygons,center[0]+jitter[0],center[1]+jitter[1],center[2]),rotation).copy()
                if target[:,:16].sum()<16 or target[:,16:].sum()<16 or target.mean()>.85: continue
                fingerprint=hashlib.sha256(target.astype(np.uint8).tobytes()).hexdigest()
                # Remove exact footprint duplicates across all splits; whole maps remain disjoint.
                if fingerprint in used_hashes: continue
                used_hashes.add(fingerprint); index=len(inputs)
                inputs.append(masked(target)); targets.append(target[None])
                records.append({'split':split,'array_index':index,'map':name,'nav_seed_area':area['id'],
                                'world_center':[float(center[0]+jitter[0]),float(center[1]+jitter[1]),float(center[2])],
                                'rotation_quarter_turns':rotation,'footprint_sha256':fingerprint})
                count+=1
            if count<samples: raise ValueError(f'Only {count} valid samples for {name}')
            print(f'{split}: {name}: {count} examples',flush=True)
        np.savez_compressed(output/(split+'.npz'),x=np.asarray(inputs,dtype=np.float32),y=np.asarray(targets,dtype=np.float32))
    for name,row in approved.items():
        if name not in flattened: excluded.append({'map':name,'reason':'No NAV available for this task' if not row['nav_available'] else 'Not selected for pilot'})
    manifest={'schema_version':1,'task':'predict hidden right half of local NAV footprint from visible left half',
              'seed':seed,'size':SIZE,'cell_units':CELL,'height_band_units':48,'splits':SPLITS,
              'counts':{split:sum(r['split']==split for r in records) for split in SPLITS},
              'sources':source_hashes,'excluded_maps':excluded,'examples':records,
              'archive_sha256':{s:hashlib.sha256((output/(s+'.npz')).read_bytes()).hexdigest() for s in SPLITS},
              'limits':['Examples from each map overlap and are correlated, not independent maps.',
                        'Only eight maps supply NAV; one validation map and one test map provide a preliminary evaluation.',
                        'Footprints project NAV polygons whose mean heights lie within 48 units of a seed; vertical layers can alias.',
                        'No architectural wall geometry, props, ladders, traversal flags, text prompts, or balance targets.',
                        'Masked context contains no target pixels from the hidden half; source IDs are metadata only.']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)); return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--corpus',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--samples-per-map',type=int,default=256)
    args=parser.parse_args()
    if args.samples_per_map<1: parser.error('Positive samples per map required')
    result=build(args.corpus,args.output,args.samples_per_map); print(json.dumps(result['counts']))


if __name__=='__main__': main()
