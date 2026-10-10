"""One reference-guided architectural revision of the authored P04 prototype.

Not a diversity sampler. The first revision's strategic plan/budgets are retained.
"""

def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


def build(base):
    p=base;p['spaces']=[];p['openings']=[];p['internal_masses']=[]
    p['architectural_revision']='reference-guided single composition, visual review pending'
    p['recovery_budget_status']='Frozen historical area/distance allocations remain checked. Misses are retained as unresolved violations; no budget optimization in this architectural review.'
    def space(pid,boundary,why):p['spaces'].append({'id':pid,'boundary':boundary,'description':why})
    space('south_court',[[55,8],[72,8],[72,13],[83,13],[83,26],[66,26],[66,23],[55,23]],
          'Compact loading court between building faces; west and east deployment doors face different directions.')
    space('west_forecourt',[[15,10],[38,10],[38,15],[55,15],[55,23],[30,23],[30,36],[44,36],[44,46],[48,46],[48,58],[10,58],[10,38],[15,38]],
          'A deployment lane opens into a doorway forecourt; its widening supports the first fight and an execute reset.')
    space('west_yard',[[10,58],[30,58],[30,68],[40,68],[40,58],[48,58],[48,82],[42,82],[42,90],[24,90],[24,82],[10,82],[10,76],[22,76],[22,66],[10,66]],
          'A court is shaped by attached store/loading buildings: entry pocket, diagonal crosscourt fight, northern objective bay and side entry sector.')
    space('west_service',[[48,46],[59,46],[59,62],[54,62],[54,78],[48,78]],
          'Local side approach beside the loading building; terminates at A instead of continuing to CT.')
    space('west_foyer',[[24,90],[42,90],[42,86],[50,86],[50,94],[61,94],[61,102],[38,102],[38,98],[24,98]],
          'Building-edge rear access with a recessed regroup pocket and a CT-facing neck; shared recovery/rotation circulation.')
    space('deployment_hall',[[61,94],[73,94],[73,99],[86,99],[86,114],[76,114],[76,120],[60,120],[60,108],[61,108]],
          'CT deployment courtyard sits behind a building face; assignments leave through separate rear access arms.')
    space('east_foyer',[[86,99],[103,99],[103,90],[123,90],[123,104],[112,104],[112,110],[86,110]],
          'Rear B receiving bay and building-edge access; regroup and fallback annotate this circulation.')
    space('east_assembly',[[99,74],[120,74],[120,78],[136,78],[136,98],[123,98],[123,90],[99,90]],
          'B execute space has a near entry fight and an offset objective bay; rear access challenges the side sector.')
    space('east_workshop',[[124,46],[138,46],[138,64],[126,64],[126,70],[119,70],[119,74],[108,74],[108,62],[124,62]],
          'Workshop turns around the contest-room building; secure it before preparing the west-facing return into B.')
    space('east_gate',rect(104,42,124,56),
          'First-contact room entered from a narrower lobby; workshop doorway and side branch expose different choices.')
    space('east_service',[[92,50],[104,50],[104,58],[99,58],[99,90],[93,90],[93,66],[88,66],[88,58],[92,58]],
          'Local B side access ends at the site wall; no rear-gallery exit. The site defender can contest its mouth.')
    space('east_forecourt',[[83,18],[98,18],[98,26],[112,26],[112,42],[104,42],[104,50],[96,50],[96,32],[89,32],[89,26],[83,26]],
          'Separate attacker departure wraps the loading building and reaches a small lobby before first contact.')
    p['envelope']=rect(5,5,143,125)
    def opening(pid,a,b,line,why):p['openings'].append({'id':pid,'spaces':[a,b],'aperture':line,'purpose':why})
    opening('south_west','south_court','west_forecourt',[[55,17],[55,22]],'Commit west through the loading-court door.')
    opening('south_east','south_court','east_forecourt',[[83,19],[83,25]],'Commit east through the separate departure frontage.')
    opening('A_main','west_forecourt','west_yard',[[21,58],[29,58]],'A main doorway opens into a constrained entry pocket before the objective court.')
    opening('A_side_access','west_forecourt','west_service',[[48,48],[48,54]],'Branch at the first fight into local side access.')
    opening('A_side','west_service','west_yard',[[48,68],[48,75]],'Enter the crosscourt fight from another sector; defenders hold the site-side mouth.')
    opening('A_rear','west_yard','west_foyer',[[27,90],[35,90]],'Contestable fallback/rear boundary; attackers must cross A to reach it.')
    opening('west_CT','west_foyer','deployment_hall',[[61,95],[61,101]],'Rear A assignment diverges from CT deployment.')
    opening('east_CT','deployment_hall','east_foyer',[[86,101],[86,108]],'Rear B assignment diverges from CT deployment.')
    opening('B_rear','east_foyer','east_assembly',[[108,90],[116,90]],'Rear B access holds the side-entry sector, then withdraws into the receiving bay.')
    opening('B_main','east_workshop','east_assembly',[[111,74],[118,74]],'Final execute portal after the workshop turn; sightline does not extend back into the lobby.')
    opening('B_territory_access','east_gate','east_workshop',[[124,48],[124,54]],'Win the contest room before clearing around the workshop return.')
    opening('B_lobby','east_forecourt','east_gate',[[106,42],[111,42]],'Narrow entrance into the wider first-contact room.')
    opening('B_side_access','east_gate','east_service',[[104,51],[104,55]],'Alternative commitment branches from the same first fight.')
    opening('B_side','east_service','east_assembly',[[99,80],[99,86]],'B side mouth faces occupied site space and does not lead directly to CT.')
    p['internal_masses']=[{'id':'assembly_partition','boundary':rect(108,74,114,82),
        'purpose':'Attached loading-building face separates workshop-main and side-sector combat, rather than an isolated cover block.'}]
    anchors={'T':(68,17),'CT':(72,111),'A':(33,82),'A_prep':(24,43),'A_fight':(36,52),
        'A_entry':(25,58),'A_side':(44,72),'A_hold':(37,78),'A_rear':(31,95),'A_retake':(44,94),
        'B':(129,89),'B_prep':(108,36),'B_fight':(111,50),'B_territory':(130,59),
        'B_entry':(116,74),'B_side':(103,83),'B_hold':(118,85),'B_rear':(117,99),'B_retake':(108,97)}
    parents={'T':'south_court','CT':'deployment_hall','A':'west_yard','A_prep':'west_forecourt','A_fight':'west_forecourt',
        'A_entry':'west_yard','A_side':'west_yard','A_hold':'west_yard','A_rear':'west_foyer','A_retake':'west_foyer',
        'B':'east_assembly','B_prep':'east_forecourt','B_fight':'east_gate','B_territory':'east_workshop',
        'B_entry':'east_assembly','B_side':'east_assembly','B_hold':'east_assembly','B_rear':'east_foyer','B_retake':'east_foyer'}
    p['annotations']={pid:{'point':list(pos),'space':parents[pid],'level':0,'interpretation':'Role within architectural space; not a floor patch.'} for pid,pos in anchors.items()}
    p['reference_guidance']=[
        {'change':'A doorway forecourt, attached building notches and crosscourt objective bay',
         'references':['output/annotations/dust2-boundaries-v4/overview.png','output/annotations/cache-reviewed-v1/overview.png'],
         'observed':'Dust2 Long doorway opens into a widened encounter; Cache A main/side entrances present different sectors around building edges.',
         'use':'Doorway narrower than forecourt, entry pocket narrower than objective court, side entry faces a different part of the same court. No Dust2 Mid copied.'},
        {'change':'B lobby, contest room, workshop turn and offset execute bay',
         'references':['output/annotations/cache-reviewed-v1/overview.png','output/annotations/cobblestone-reviewed-v1/overview.png'],
         'observed':'Cache B halls/main has an approach-to-site threshold; Cobblestone tunnels distinguish circulation, encounters and doorway transitions.',
         'use':'A narrow lobby feeds a wider fight, then a side doorway/turn breaks lobby-to-site visibility; the side route skips workshop territory but still enters occupied B.'},
        {'change':'Compact deployment and integrated rear recovery',
         'references':['output/annotations/train-reviewed-v1/overview.png','output/annotations/cache-reviewed-v1/overview.png'],
         'observed':'Train spawn/yard and CT-side circulation sit between building faces; Cache rear-site access has local recesses and site-facing thresholds.',
         'use':'Separate departure doors and building-edge receiving bays replace broad strips. Local paths remain narrower than deployment and site courts.'}]
    p['proportion_basis']='Qualitative ratios from inspected local radar regions: 4–8-unit openings, roughly 6–12-unit circulation and 18–38-unit encounter/site widths. Not source-unit calibration or learned dimensions.'
    p['objective_zones']={'A':rect(28,79,38,87),'B':rect(126,84,133,93)}
    from p04_spatial_usefulness import refine
    return refine(p)
