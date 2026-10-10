"""Apply this session's explicit Dust2 role review, preserving the original draft."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from annotate_layout import draw_annotation


def reviewed(annotation):
    result=copy.deepcopy(annotation)
    zones={z['id']:z for z in result['zones']}
    # The user corrected the mid contest area from Top Mid to Middle.
    zones['mid_top']['roles_proposed']=['attacker_distribution']
    zones['mid_top']['interpretation']='Attacker distribution above the Middle contest area.'
    zones['mid_lane']['roles_proposed']=['contested_connector','initial_contest_candidate']
    zones['mid_lane']['interpretation']='User places the central meeting/contest area in Middle; exact boundary and timing remain unmeasured.'
    zones['long_entry']['title']='A-doors / Long doors'
    zones['long_entry']['interpretation']='User identifies A-doors as an initial contest context. The narrow door transition and surrounding meeting area are distinct.'
    zones['upper_tunnel']['interpretation']='User identifies Upper tunnels as an initial contest context. The tunnel exit choke is distinct from the surrounding meeting area.'
    first,second=zones['b_access'],zones['mid_doors']
    first['subareas']=[copy.deepcopy(first),copy.deepcopy(second)]
    first['id']='outside_b';first['title']='Outside B'
    for field in ('source_place_labels','region_ids','nav_area_ids'):
        first[field]=sorted(set(first[field]+second[field]))
    first['roles_proposed']=list(dict.fromkeys(first['roles_proposed']+second['roles_proposed']))
    first['interpretation']='User suggested one Outside B area for original groups 15/18; door/window and Mid-door transitions retained as subareas.'
    result['zones']=[z for z in result['zones'] if z['id']!='mid_doors']
    for region,zone in list(result['region_zone_membership'].items()):
        if zone in ('b_access','mid_doors'):result['region_zone_membership'][region]='outside_b'
    interfaces=[];internal=[]
    for interface in result['directed_zone_interfaces']:
        for field in ('source_zone','target_zone'):
            if interface[field] in ('b_access','mid_doors'):interface[field]='outside_b'
        (internal if interface['source_zone']==interface['target_zone'] else interfaces).append(interface)
    result['directed_zone_interfaces']=interfaces
    result['newly_internal_interfaces']=internal
    for z in result['zones']:z['review_status']='reviewed_first_pass_roles'
    for r in result['routes']:r['review_status']='reviewed_first_pass_purpose'
    result['front_hypotheses']=[{'id':key,'location':location,'zone_id':zone,'status':'user_reviewed_location',
        'exact_boundary_annotated':False,'timing_measured':False}
        for key,location,zone in [('long_front','A-doors','long_entry'),('mid_front','Middle','mid_lane'),('b_front','Upper tunnels','upper_tunnel')]]
    result.update(annotation_status='reviewed_first_pass',training_eligible=True,
        eligible_target_scope='Reviewed zone grouping and first-pass role context only; not exact choke, meeting boundary, exposure, safety or timing labels.',
        user_review={'feedback':['Contest Areas happen at A-doors, Middle, and Upper tunnels',
                    'Most if not all of your interpretations are exactly correct',
                    'All the zones are good, I might connect zones 15/18 into one outside B area'],
                    'merge_interpretation':'Applied suggested grouping reversibly with original subareas retained.'})
    result['limits'][-1]='Only first-pass role context is reviewed. Spatial choke/meeting-area labels remain unannotated. No new model training occurred.'
    return result


def role_targets(annotation,graph):
    if annotation['annotation_status']!='reviewed_first_pass':raise ValueError('Role targets require recorded review')
    by_zone={z['id']:z for z in annotation['zones']};membership=annotation['region_zone_membership']
    # Keep every original directed navigation edge and region. Contracting all
    # equally named places could invent paths across disconnected subareas.
    nodes=[]
    for node in graph['nodes']:
        copy_node=copy.deepcopy(node);zone=membership.get(node['id'])
        copy_node.update(semantic_zone_id=zone,role_context_targets=by_zone[zone]['roles_proposed'] if zone else [],
                         role_supervision_mask=bool(zone))
        nodes.append(copy_node)
    return {'schema_version':1,'task':'reviewed_navigation_role_context','map':'Dust2','dataset_role':'training',
        'independent_maps':1,'training_performed':False,'nodes':nodes,'directed_edges':graph['edges'],
        'nav_polygons':graph['nav_polygons'],'semantic_zones':annotation['zones'],
        'routes':annotation['routes'],'contest_contexts':annotation['front_hypotheses'],
        'source_graph_sha256':annotation['source_graph_sha256'],
        'supervised_region_count':sum(n['role_supervision_mask'] for n in nodes),
        'limits':['Context labels apply to reviewed groups, not measured tactical footprints.',
                  'Unlabeled regions retained with supervision masked off.',
                  'Semantic groups must not be rendered as rectangular rooms or blindly contracted into a traversability graph.']}


def run(source,graph_path,output):
    if output.exists():raise ValueError('Use new paths')
    original=json.loads(source.read_text());raw=graph_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=original['source_graph_sha256']:raise ValueError('Source graph changed')
    graph=json.loads(raw);annotation=reviewed(original);targets=role_targets(annotation,graph)
    output.mkdir(parents=True)
    (output/'annotation.json').write_text(json.dumps(annotation,indent=2))
    (output/'role-targets.json').write_text(json.dumps(targets,indent=2))
    draw_annotation(graph,annotation,output/'overview.png')
    (output/'review.md').write_text('# Dust2 first-pass review recorded\n\nContest contexts: A-doors, Middle and Upper tunnels. Top Mid remains distribution, not the annotated central meeting area.\n\nOriginal groups 15/18 form Outside B; subarea membership and directed NAV links remain intact. Seventeen role groups cover 100 source regions; ten unlabeled regions have supervision masked off.\n\nrole-targets.json retains all 110 regions and 291 directed links. This is one reviewed reference, not a trained model. Meeting-area extents and narrower choke boundaries remain separate, unannotated targets.\n')
    print(json.dumps({'zones':len(annotation['zones']),'supervised_regions':targets['supervised_region_count'],
                     'source_regions_retained':len(targets['nodes']),'directed_links_retained':len(targets['directed_edges']),
                     'training_performed':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--graph',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.graph,a.output)
