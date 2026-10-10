"""Strict, blueprint-independent Stage 1 design controls. No keyword parser."""
import copy
import random

VERSION='map-design-spec-v1'
CHOICES={
 'gameplay':{'sites':[2],'mid':['absent','contested','auto'],'mid_organization':['auto','contested_street','linked_courts'],'mid_access_mode':['auto','separate_entries','one_approach_handoff'],
             'main_approaches':['independent'], 'secondary_access':['local','mid','local_and_mid','auto'],
             'defender_rotation':['rear','central','auto'], 'site_commitment':['immediate','staged','mixed','auto']},
 'architecture':{'site_setting':['courtyard','interior','mixed','auto'],
                 'site_separation':['adjacent','separated','auto']},
}
DEFAULTS={'version':VERSION,'gameplay':{'sites':2,'mid':'auto','mid_organization':'auto','mid_access_mode':'auto','main_approaches':'independent','secondary_access':'auto','defender_rotation':'auto','site_commitment':'auto'},
 'architecture':{'site_setting':'auto','site_separation':'auto'},
 'hard_constraints':{'max_extent_HU':5120,'minimum_door_width_HU':128,'maximum_main_route_HU':None},
 'soft_preferences':{'compactness':0.7,'sightline_breaks':0.8,'asymmetry':0.7,'route_complexity':0.5},'seed':None}

class SpecificationError(ValueError):pass

def validate_spec(value):
    if not isinstance(value,dict):raise SpecificationError('Specification must be a JSON object')
    out=copy.deepcopy(DEFAULTS)
    if set(value)-set(out):raise SpecificationError('Unsupported fields: '+', '.join(sorted(set(value)-set(out))))
    for section,content in value.items():
        if section in ('version','seed'):out[section]=content;continue
        if not isinstance(content,dict):raise SpecificationError(section+' must be an object')
        if set(content)-set(out[section]):raise SpecificationError('Unsupported '+section+' controls: '+', '.join(sorted(set(content)-set(out[section]))))
        out[section].update(content)
    if out['version']!=VERSION:raise SpecificationError('Unsupported specification version')
    if out['seed'] is not None and (type(out['seed']) is not int or not 0<=out['seed']<2**63):raise SpecificationError('seed must be an integer from 0 to 2^63-1 or null')
    for section,fields in CHOICES.items():
        for field,allowed in fields.items():
            v=out[section][field]
            if isinstance(v,bool) or (field=='sites' and type(v) is not int) or v not in allowed:raise SpecificationError(f'{section}.{field}: unsupported {v!r}; supported: {allowed}')
    h=out['hard_constraints']
    for field,lo,hi in [('max_extent_HU',3584,6400),('minimum_door_width_HU',96,192),('maximum_main_route_HU',256,12800)]:
        v=h[field]
        if v is None and field=='maximum_main_route_HU':continue
        if type(v) not in (int,float) or not lo<=v<=hi:raise SpecificationError(f'{field} must be between {lo} and {hi} HU')
    for k,v in out['soft_preferences'].items():
        if type(v) not in (int,float) or not 0<=v<=1:raise SpecificationError(k+' must be between 0 and 1')
    g=out['gameplay']
    if g['mid']=='absent' and g['mid_organization']!='auto':raise SpecificationError('Absent Mid conflicts with explicit Mid organization')
    if g['mid']=='absent' and g['mid_access_mode']!='auto':raise SpecificationError('Absent Mid conflicts with explicit Mid access mode')
    if g['mid']=='absent' and (g['secondary_access'] in ('mid','local_and_mid') or g['defender_rotation']=='central'):raise SpecificationError('Absent Mid conflicts with Mid access or central rotation')
    if g['mid']=='contested' and g['secondary_access']=='local':raise SpecificationError('This version supports contested Mid only with secondary access to both sites; local-only secondaries unsupported')
    return out

def resolve_spec(spec,seed):
    """Resolve unspecified controls once, reproducibly; never replace explicit ones."""
    out=copy.deepcopy(spec);r=random.Random(seed);log=[];g=out['gameplay'];a=out['architecture']
    def choose(section,key,values,reason='Unspecified; seeded choice'):
        if out[section][key]=='auto':
            selected=r.choice(values);out[section][key]=selected;log.append(dict(control=section+'.'+key,selected=selected,reason=reason))
    if g['mid']=='auto' and (g['secondary_access'] in ('mid','local_and_mid') or g['defender_rotation']=='central' or g['mid_organization']!='auto' or g['mid_access_mode']!='auto'):
        g['mid']='contested';log.append(dict(control='gameplay.mid',selected='contested',reason='Required by explicit Mid access/central rotation'))
    elif g['mid']=='auto' and g['secondary_access']=='local':
        g['mid']='absent';log.append(dict(control='gameplay.mid',selected='absent',reason='Local-only request; contested Mid local-only not supported'))
    if g['secondary_access']=='local_and_mid':
        # This architectural family has a deliberately bounded capability set.
        # Resolve only omitted choices into that set; explicit incompatible
        # requests remain intact for the composer's supports() error report.
        for section,key,selected in [
            ('gameplay','mid_organization','contested_street'),
            ('gameplay','mid_access_mode','separate_entries'),
            ('gameplay','defender_rotation','rear'),
            ('gameplay','site_commitment','staged'),
            ('architecture','site_setting','mixed'),
            ('architecture','site_separation','separated')]:
            choose(section,key,[selected],reason='Unspecified; supported by the local_and_mid architectural family')
    choose('gameplay','mid',['absent','contested'])
    if g['mid']=='contested':choose('gameplay','mid_organization',['contested_street','linked_courts'])
    if g['mid']=='contested':choose('gameplay','mid_access_mode',['separate_entries'])
    choose('gameplay','secondary_access',['mid'] if g['mid']=='contested' else ['local'])
    choose('gameplay','defender_rotation',['rear','central'] if g['mid']=='contested' else ['rear'])
    choose('gameplay','site_commitment',['immediate','staged','mixed'])
    choose('architecture','site_setting',['courtyard','interior','mixed'])
    choose('architecture','site_separation',['adjacent','separated'])
    return validate_spec(out),log

def json_schema():
    def obj(props):return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    props={'version':{'type':'string','enum':[VERSION]}}
    for section,fields in CHOICES.items():props[section]=obj({k:{'type':'integer' if k=='sites' else 'string','enum':v} for k,v in fields.items()})
    props['hard_constraints']=obj({'max_extent_HU':{'type':'number','minimum':3584,'maximum':6400},'minimum_door_width_HU':{'type':'number','minimum':96,'maximum':192},'maximum_main_route_HU':{'type':['number','null']}})
    props['soft_preferences']=obj({k:{'type':'number','minimum':0,'maximum':1} for k in DEFAULTS['soft_preferences']})
    props['seed']={'type':['integer','null']}
    return obj(props)

def mid_strategy(spec,seed):
    """Coordinate-free seeded choices held fixed across spatial attempts."""
    r=random.Random((spec.get('seed') if spec.get('seed') is not None else seed)^0xAC21)
    organization=spec['gameplay'].get('mid_organization','auto')
    if organization=='auto':organization=r.choice(['contested_street','linked_courts'])
    handoff=r.choice(['A','B']) if spec['gameplay'].get('mid_access_mode')=='one_approach_handoff' else None
    return dict(organization=organization,handoff_site=handoff,team_access='Independent approaches to different parts of shared Mid territory',branches={site:'transfer to primary preparation; shared final entry' if site==handoff else 'transfer territory to separate entry preparation' for site in ('A','B')},provenance='Authored strategic rules; not inferred timings or copied Dust2 graph')

def strategic_contract(spec):
    g=spec['gameplay'];mid=g['mid']=='contested';routes=[]
    for site in ('A','B'):
        investment=[site+'_investment'] if g['site_commitment']=='staged' or (g['site_commitment']=='mixed' and site=='B') else []
        routes.extend([dict(id='T-'+site+'-main',purpose='Independent primary commitment via staging to '+site,places=['T',site+'_staging',site]),
                       dict(id='T-'+site+'-secondary',purpose='Secondary approach through '+('Mid-controlled transfer territory; not immediate site access' if mid else 'local side approach'),places=['T','Mid' if mid else site+'_staging']+([site+'_transfer'] if mid else [])+[site+'_secondary',site]),
                       dict(id='CT-'+site+'-deploy',purpose='Defensive assignment with receiving and fallback',places=['CT',site+'_receiving',site]),
                       dict(id=site+'-retreat',purpose='Withdraw from objective to receiving and rear deployment',places=[site,site+'_receiving','CT'])])
        routes[-4]['places']=['T']+investment+[site+'_staging',site]
    routes.append(dict(id='CT-rotate',purpose='Rear deployment rotation' if g['defender_rotation']=='rear' else 'Central contested rotation; control-dependent',places=['A','CT' if g['defender_rotation']=='rear' else 'Mid','B']))
    if mid:routes.extend([dict(id='T-Mid',purpose='Independent attacker contest',places=['T','Mid']),dict(id='CT-Mid',purpose='Independent defender contest',places=['CT','Mid'])])
    if g['secondary_access']=='local_and_mid':
        for site in ('A','B'):routes.append(dict(id='T-'+site+'-local',purpose='Local split from committed staging to a different final entry; Mid also reaches this side-entry preparation from another territory',places=['T',site+'_staging',site+'_secondary',site]))
    return dict(schema='coordinate-free-design-contract-v3',gameplay=g,mid_plan=mid_strategy(spec,spec.get('seed') or 0) if mid else None,roles=['main approach','first contest','connector','split point','execute preparation','flank','rotation junction','T deployment','CT deployment','A/B objectives','staging','entry sectors','receiving/fallback','retake','local secondaries' if not mid else 'distributed Mid, transfer territory and approach junctions'],routes=routes,
                role_semantics={'staging':'Hold or gather before selecting entry; may share execute space','main approach':'Primary committed territory, potentially several connected architectural subspaces','first contest':'Potential meeting support at an entry where attacker and defender routes/visibility can interact; timings unresolved','connector':'Connect strategically distinct territories, not a generic room','split point':'Choice between primary entry and a separate approach; can share a staging court','execute preparation':'Last protected gathering/clearing support before a site entry','flank':'Alternative sector access; opening approach versus later flank status unresolved','fallback':'Defender receiving/withdrawal support, not certified safe retreat','rotation junction':'Defender assignments diverge/converge; may share deployment'},role_to_space='Many-to-many; callout text does not allocate geometry',complexity=spec['soft_preferences'].get('route_complexity',.5),unresolved=['Timing/territory ownership/retreat safety cannot be certified without engine playtests.'],examples='P04 illustrates no-Mid separate commitments; P01 illustrates contested Mid. Neither blueprint is loaded as a template.')
