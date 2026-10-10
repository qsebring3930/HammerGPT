"""Measured review of round-1 winner plus one explicitly authored subtraction."""
import json
import math
import networkx as nx
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from strategic_floorplan import ROOT,realize,audit_saved,render,save


def analyze(candidate):
    graph=nx.Graph();graph.add_edges_from(e['places'] for e in candidate['edges'])
    nodes={n['id']:n for n in candidate['nodes']}
    ct=next(n['id'] for n in nodes.values() if n['role']=='CT')
    result={'CT_exit_count':graph.degree(ct),
        'CT_exit_destinations':[{'place':i,'degree':graph.degree(i),'roles':nodes[i]['strategic_roles']}
                                for i in graph.neighbors(ct)],'site_alternatives':{}}
    for site in ('A','B'):
        routes=[r for r in candidate['routes'] if r['team']=='T' and r['target']==site]
        target=next(n for n in nodes.values() if n['role']==site)
        bearings=[]
        for route in routes:
            previous=route['places'][-2]
            dx=nodes[previous]['center'][0]-target['center'][0]
            dy=nodes[previous]['center'][1]-target['center'][1]
            bearings.append(math.degrees(math.atan2(dy,dx)))
        diff=abs((bearings[0]-bearings[1]+180)%360-180)
        result['site_alternatives'][site]={
            'entry_predecessors':[r['places'][-2] for r in routes],
            'approach_bearing_difference_deg_proxy':round(diff,1),
            'centerline_seconds_proxy':[r['seconds_centerline_proxy'] for r in routes],
            'shared_internal_places':sorted(set(routes[0]['places'][1:-1])&set(routes[1]['places'][1:-1])),
            'limits':'Different entry predecessors/bearings do not prove different defender exposure or useful fights.'}
    return result


def main():
    from semantic_pipeline import check_generation_policy
    check_generation_policy(legacy=True)
    folder=ROOT/'output/preference-round-001/radar-3-revision';folder.mkdir(exist_ok=True)
    original=json.loads((folder.parent/'candidate-3/layout.json').read_text())
    revised,_=realize(original['seed'],removed_edges=[(2,11)])
    revised['intervention_provenance']={
        'source_layout':'output/preference-round-001/candidate-3/layout.json',
        'change':'Remove A-side secondary cross-link 2–11; CT exit remains connected to A and lower mid.',
        'basis':'User requested reduced CT/mid redundancy while preserving distinct site approaches.',
        'learned_geometry_change':False,'cover':'Recomputed by the same deterministic protected-path placement.'}
    save(folder/'layout.json',revised);save(folder/'audit.json',audit_saved(revised))
    save(folder/'before-after-diagnostics.json',{'before':analyze(original),'after':analyze(revised)})
    render(revised,folder/'radar.png');render(revised,folder/'routes.png',True)
    canvas=Image.new('RGB',(2000,1080),'#080f18');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',28)
    for i,(label,path) in enumerate([('Original radar 3',folder.parent/'candidate-3/radar.png'),
                                    ('Revision: one A-side link removed',folder/'radar.png')]):
        canvas.paste(Image.open(path).resize((960,960),Image.Resampling.LANCZOS),(i*1000+20,70))
        draw.text((i*1000+35,20),label,font=font,fill='#e3edf4')
    draw.text((35,1030),'Human-guided geometry edit · both site approaches retained · flat proposal, not engine-tested',font=font,fill='#bbccdd')
    canvas.save(folder/'comparison.png')
    print(json.dumps(json.loads((folder/'before-after-diagnostics.json').read_text()),indent=2))


if __name__=='__main__':main()
