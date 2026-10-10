"""Single authored usefulness/proportion revision. No batch or engine export."""
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from shapely.affinity import translate
from playable_composition import DerivedNavigation


def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


def refine(p):
    shapes={
        'west_forecourt':[[23,15],[55,15],[55,23],[32,23],[32,36],[44,36],[44,46],[48,46],[48,58],[16,58],[16,40],[23,40]],
        'west_yard':[[18,58],[30,58],[30,68],[40,68],[40,64],[48,64],[48,82],[42,82],[42,90],[24,90],[24,82],[22,82],[22,66],[18,66]],
        'east_forecourt':[[83,18],[98,18],[98,26],[112,26],[112,42],[104,42],[104,32],[89,32],[89,26],[83,26]],
        'east_service':[[92,50],[104,50],[104,58],[99,58],[99,70],[91,70],[91,66],[88,66],[88,58],[92,58]]}
    for s in p['spaces']:
        if s['id'] in shapes:s['boundary']=shapes[s['id']]
    p['spaces'].append({'id':'east_side_landing','boundary':[[87,70],[99,70],[99,90],[93,90],[93,78],[87,78]],
        'description':'Sheltered landing after a side-access threshold. Squad can pause/reset here before committing through the perpendicular site mouth.'})
    for o in p['openings']:
        if o['id']=='B_side':o['spaces']=['east_side_landing','east_assembly']
        if o['id']=='B_main':
            o['aperture']=[[114,74],[118,74]]
            o['purpose']='128-HU intended and clear final execute aperture beside the unchanged full-height partition. Covered portion of the former 224-HU declaration is closed.'
    p['openings'].append({'id':'B_side_threshold','spaces':['east_service','east_side_landing'],
        'aperture':[[92,70],[97,70]],'purpose':'Clear the building threshold and sheltered landing before the final site entry; breaks one passage into approach and execute decisions.'})
    for mass in p['internal_masses']:mass['height_source_units']=160;mass['height_class']='full_height'
    p['internal_masses'] += [
        {'id':'A_plant_low_cover','boundary':rect(29,80,34,82),'height_source_units':48,'height_class':'low_cover',
         'purpose':'Plant-side protection from lower entry angles; standing defenders can see over it, crouched sight is interrupted.'},
        {'id':'B_plant_low_cover','boundary':rect(128,87,131,89),'height_source_units':48,'height_class':'low_cover',
         'purpose':'Small plant-bay shelter requiring a close clear; does not occlude standing visibility across the bay.'}]
    p['annotations']['A']['point']=[35,84];p['annotations']['B']['point']=[132,91]
    p['units']='plan units; provisional 1 plan unit = 32 Source units. No travel-time calibration.'
    p['engine_scale']={'source_units_per_plan_unit':32,'player_width_source_units':32,
        'standing_height_source_units':72,'standing_eye_source_units':64,'crouched_eye_source_units':46,
        'full_height_boundary_source_units':160,'wall_thickness_source_units':25.6,
        'status':'Authored provisional assumptions, not verified CS2 runtime collision/eye dimensions.',
        'method':'Axis-aligned 32x32 footprint; eroded orthogonal walkable space. No jumps, crouch movement, doors, headroom or crowd simulation.',
        'evidence':'https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/game/shared/shareddefs.h — view/hull vectors are game-specific; this does not establish CS2 values.'}
    p['pocket_review']=[
        {'location':'A west recess (x10–22,y76–82)','action':'Removed','purpose':'No useful route or distinct target; extended clearing burden without affecting the approach.'},
        {'location':'A main-entry left corner (x18–21,y58–66)','action':'Reduced and retained','purpose':'Close hold to clear immediately after main entry; holder can withdraw around the store edge into the court.'},
        {'location':'A side-entry low corner (x40–48,y58–64)','action':'Removed','purpose':'Removed the blind extension below the side fight. Remaining shallow x40–48,y64–68 corner watches the side mouth and retreats north into the court.'},
        {'location':'CT north shoulder and rear foyer recesses','action':'Retained','purpose':'Deployment staging / fallback reset behind building faces, connected to rear assignment routes.'},
        {'location':'B side landing (x87–99,y70–78)','action':'Threshold + landing','purpose':'Local pause/retreat space before site entry; no CT access or new strategic destination.'},
        {'location':'B departure stub (x96–104,y42–50)','action':'Removed','purpose':'Blind extension beside the contest room had no entry or useful contest function.'}]
    p['encounter_sequences']={
        'A main':{'points':[[25,60],[20,63],[26,70],[35,84]],
            'steps':['Clear close-left pocket','Check store edge into court','Clear plant-cover front and rear access'],
            'purpose':'A doorway cannot see the whole plant bay; the store edge creates a distinct second clearing decision.'},
        'A side':{'points':[[44,72],[44,66],[37,78],[35,84]],
            'steps':['Clear shallow southern off-angle','Challenge crosscourt hold','Clear low cover / plant / rear'],
            'purpose':'Different initial fight from A main; holder in shallow corner can retreat toward the court.'},
        'B main':{'points':[[116,76],[118,84],[125,83],[132,91]],
            'steps':['Clear partition return','Check rear/side-sector crossfire','Turn into objective bay; clear low cover'],
            'purpose':'The full-height partition prevents one doorway clear from solving the whole site.'},
        'B side':{'points':[[94,74],[96,82],[103,83],[118,85],[132,91]],
            'steps':['Clear threshold/landing','Check site mouth from its sheltered edge','Challenge near hold before turning into plant bay'],
            'purpose':'Sheltered pause has a retreat into side access; final site entry exposes the defender sector.'}}
    p['defender_positions']=[
        {'id':'A court','point':[37,78],'targets':[[44,72],[26,70]],'retreat':'A_rear','purpose':'Choose side mouth versus main court clearance; retreat via rear threshold.'},
        {'id':'A close','point':[20,63],'targets':[[25,60]],'retreat':'A_rear','purpose':'Optional close entry hold. Escape crosses the court and is not guaranteed safe.'},
        {'id':'B near','point':[118,85],'targets':[[103,83],[116,76]],'retreat':'B_rear','purpose':'Hold side/main entry sectors, sacrificing immediate plant-bay coverage.'},
        {'id':'B bay','point':[132,95],'targets':[[125,83],[132,91]],'retreat':'B_rear','purpose':'Hold plant-bay turn; withdrawing exposes that bay.'}]
    p['reference_guidance'].extend([
        {'change':'Useful pockets and narrower departure approaches','references':['output/annotations/dust2-boundaries-v4/overview.png','output/annotations/cache-reviewed-v1/overview.png'],
         'observed':'Long-door forecourt / Cache lobby boundaries concentrate clearing around entry edges.',
         'use':'Remove A west and B lobby stubs; retain only named close holds with a court retreat. Departure lanes widen at staging rather than remaining wide throughout.'},
        {'change':'B side-access threshold and landing','references':['output/annotations/cobblestone-reviewed-v1/overview.png','output/annotations/cache-reviewed-v1/overview.png'],
         'observed':'Tunnel transitions and halls-to-main thresholds distinguish travel, local contest and final execute.',
         'use':'A doorway into a sheltered landing provides squad preparation/retreat before the perpendicular site entry. No decorative bend or CT shortcut.'},
        {'change':'Plant bays and height-aware cover','references':['output/annotations/train-reviewed-v1/overview.png','output/annotations/cache-reviewed-v1/overview.png'],
         'observed':'Site entries expose different building/cover sectors before reaching objective space.',
         'use':'Separate close entry, near hold and plant-bay checks. Radar outlines do not prove cover height: all height choices here are explicitly authored.'}])
    p['budget_revision_proposals']=[
        {'role':'A_rear','boundary':rect(25,91,37,97),'area_budget':[64,88],'reason':'Replaces an overlapping historical rectangle with the receiving pocket adjacent to the actual fallback door.'},
        {'role':'A_retake','boundary':rect(42.5,90,49.5,94.5),'area_budget':[28,40],'reason':'Regroup in the existing recessed rear-access elbow, rather than demanding a separate large room.'},
        {'role':'B_rear','boundary':rect(114,94,122,102),'area_budget':[56,80],'reason':'Existing receiving bay portion preserves a rear assignment and local fallback without reserving the whole strip.'},
        {'role':'B_retake','boundary':rect(104,94,113,100),'area_budget':[48,64],'reason':'Site-facing regroup portion inside B rear architecture; avoids the old rectangle extending into solid mass.'}]
    p['distance_revision_proposals']=[{'route':'CT-A-recover','budget':[24,36],
        'reason':'A rear-to-side-sector traverse fits the existing courtyard; 40–75 demanded extra travel with no distinct gameplay purpose. New interval is authored tolerance, not a learned CS quality threshold.'}]
    p['budget_revision_status']='Proposals for review only; original allocations/distance budgets retained unchanged and still reported. No silent acceptance.'
    p['aperture_correction']={'opening':'B_main','before_nominal_HU':224,'before_clear_HU':128,
        'after_intended_HU':128,'partition_unchanged':True,
        'scope':'Match declaration to existing free opening; no space/cover/spawn/site/proposal changes.'}
    p['architecture_frozen']=True
    return p


def measure(p,c,r,previous):
    scale=p['engine_scale']['source_units_per_plan_unit'];radius=p['engine_scale']['player_width_source_units']/scale/2
    centre=c['walkable'].buffer(-radius,join_style=2);nav=DerivedNavigation({**c,'walkable':centre})
    clearances=[]
    for row in r['budget_ledger']:
        route=next(x for x in r['strategy_routes_for_measurement'] if x['id']==row['route'])
        points=[p['annotations'][pid]['point'] for pid in route['places']]
        clearances.append({'route':route['id'],'fits_provisional_player':all(nav.path(a,b) is not None for a,b in zip(points,points[1:]))})
    widths=[]
    for o in p['openings']:
        line=LineString(o['aperture']);a,b=o['aperture'];length=line.length
        nx,ny=-(b[1]-a[1])/length,(b[0]-a[0])/length;depth=p['boundary_thickness']
        # A zero-depth aperture line can lie on a fixture boundary and appear
        # clear. Require collision-free space on both sides of the threshold.
        usable=line.intersection(c['walkable'])
        for sign in (-1,1):usable=usable.intersection(translate(c['walkable'],xoff=sign*nx*depth,yoff=sign*ny*depth))
        clear=usable.length*scale
        widths.append({'opening':o['id'],'nominal_source_units':line.length*scale,'clear_source_units':clear,
            'player_widths':clear/p['engine_scale']['player_width_source_units'],
            'player_centre_span_source_units':line.intersection(centre).length*scale})
    plant=[]
    for site,outline in p['objective_zones'].items():
        available=Polygon(outline).intersection(c['walkable']);safe=available.intersection(centre)
        plant.append({'site':site,'collision_free_area_source_units_squared':available.area*scale**2,
            'player_centre_plant_area_source_units_squared':safe.area*scale**2,'height_rule':'Ground-level plant envelope excludes cover footprints; engine trigger/rules unverified.'})
    cover_example={}
    sight=LineString([[25,58],[35,84]])
    for kind in ('standing','crouched'):cover_example[kind]=c['visibility_'+kind].covers(sight)
    proposals=[]
    for proposal in p['budget_revision_proposals']:
        poly=Polygon(proposal['boundary']);area=poly.intersection(c['walkable']).area
        proposals.append({**proposal,'walkable_area':area,'entire_region_walkable':c['walkable'].covers(poly),
            'within_proposed_budget':proposal['area_budget'][0]<=area<=proposal['area_budget'][1]})
    keys=('T-A-main','T-B-main','CT-A-deploy','CT-B-deploy','CT-A-switch')
    distances=[{'route':key,'source_units':r['derived_routes'][key]['length']*scale} for key in keys]
    travel=[]
    for site in ('A','B'):
        prior_points=previous['derived_routes'][f'T-{site}-main']['points']
        idx=prior_points.index(p['annotations'][site+'_fight']['point'])
        old=LineString(prior_points[:idx+1]).length
        ids=['T',site+'_prep',site+'_fight']
        # Measure only deployment -> first contact, not the full attack route.
        raw=DerivedNavigation(c);length=0
        for a,b in zip(ids,ids[1:]):length+=raw.path(p['annotations'][a]['point'],p['annotations'][b]['point'])['length']
        travel.append({'site':site,'to_first_contact_source_units':length*scale,'before_first_contact_source_units_at_same_provisional_scale':old*scale})
    return {'doorways':widths,'route_clearance':clearances,'plant_areas':plant,'proposed_area_allocations':proposals,
        'key_distances':distances,'deployment_to_first_contact':travel,'A_low_cover_example':cover_example,
        'clearance_scope':'32-unit square planning footprint, eroded orthogonal free space, no calibrated runtime hull, height/door/vertical/crowd simulation.',
        'remaining_clearance_problems':[x for x in clearances if not x['fits_provisional_player']]}
