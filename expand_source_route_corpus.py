"""Reuse approved VMAP/NAV reports; no reconstruction, compilation or annotation."""
import argparse
import json
from pathlib import Path
import shutil
from whole_map_layout import extract as spatial_extract
from coarse_layout import coarsen
from extract_gameplay_routes import extract,apply_purpose_reviews,digest
from train_route_organization import encode,N


def run(root,output):
    output.mkdir(parents=True,exist_ok=False)
    corpus=json.loads((root/'output/reference-corpus-status.json').read_text())
    approved={r['name'].lower():r for r in corpus['maps'] if r.get('user_approved') and r.get('dataset_role')!='evaluation_only'}
    fitting=['dust2','anubis','cache'];records=[]
    for name in ('dust2','anubis','cache','cobblestone','train'):
        source=root/f'output/gameplay-route-targets-v5/{name}.json'
        shutil.copyfile(source,output/f'{name}.json')
    reviews=json.loads((root/'route-purpose-reviews.json').read_text())['reviews']
    for name in ('tuscan','vertigo'):
        row=approved[name]
        if not row['nav_available']:raise ValueError('No existing NAV')
        original=root/f'output/coarse-layout-v1/{name}.json'
        if not original.exists():
            navpath=root/f'output/{name}-nav.json';refpath=root/'output'/row['reference_report']
            nav=json.loads(navpath.read_text());reference=json.loads(refpath.read_text())
            if reference['source']!=row['source']:raise ValueError('Approved source mismatch')
            graph=spatial_extract(nav,reference);graph['map']=row['name'];graph['dataset_role']='training'
            graph['provenance']={'nav_export':str(navpath.resolve()),'nav_export_sha256':digest(navpath),
                                 'nav_source':nav['source'],'vmap_report':str(refpath.resolve()),'vmap_report_sha256':digest(refpath),
                                 'vmap_source':row['source'],'vmap_source_sha256':digest(Path(row['source']))}
            spatial=output/f'{name}-spatial.json';spatial.write_text(json.dumps(graph,indent=2),encoding='utf-8')
            coarse=coarsen(graph);coarse['coarse_provenance']={'source_graph':str(spatial.resolve()),'source_sha256':digest(spatial)}
            original=output/f'{name}-coarse.json';original.write_text(json.dumps(coarse,indent=2),encoding='utf-8')
        try:
            result,areas,centers,net=extract(root,name,source_graph=original)
            apply_purpose_reviews(result,reviews)
            destination=output/f'{name}.json';destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
            record=encode(root,name,output)
            fitting.append(name);records.append({'map':name,'status':'fitting_eligible','supplied_areas':int(record['valid'].sum()),
                'recorded_directed_links':int(record['y'].sum()),'annotated_contexts':len(result['meeting_contexts'])+len(result['choke_contexts'])})
        except ValueError as error:
            records.append({'map':name,'status':'excluded_pending_data_issue','reason':str(error)})
        print(json.dumps(records[-1]),flush=True)
    manifest={'training_maps':fitting,'validation_map':'cobblestone','test_map':'train','reserved_maps_loaded':False,
              'no_map_reconstruction_or_compile':True,'new_layout_annotations_requested':False,'records':records,
              'capacity':N,'files':[{'map':n,'file':f'{n}.json','sha256':digest(output/f'{n}.json')} for n in [*fitting,'cobblestone','train']]}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'training_maps':fitting,'source_only_ingestion':True}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(Path(__file__).resolve().parent,args.output)
