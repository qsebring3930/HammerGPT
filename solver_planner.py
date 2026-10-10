"""Decode entrance connections with Google's OR-Tools CP-SAT constraint solver."""
import itertools

import numpy as np
from ortools.sat.python import cp_model


def solve_plan(probabilities,time_limit=2.0):
    p=np.asarray(probabilities,dtype=np.float64)
    if p.ndim!=2 or p.shape[0]!=p.shape[1] or not np.isfinite(p).all(): raise ValueError('Invalid probability matrix')
    if not np.allclose(p,p.T) or np.any(p<0) or np.any(p>1): raise ValueError('Expected symmetric probabilities')
    if len(p)>20 or time_limit<=0 or not np.isfinite(time_limit): raise ValueError('Supports up to 20 ports and a positive finite time limit')
    pairs=list(itertools.combinations(range(len(p)),2)); model=cp_model.CpModel()
    connected={pair:model.new_bool_var(f'connected_{pair[0]}_{pair[1]}') for pair in pairs}
    for a,b,c in itertools.combinations(range(len(p)),3):
        ab,ac,bc=connected[a,b],connected[a,c],connected[b,c]
        # Every two connected pairs imply the third: equality is transitive.
        model.add(ab+bc-ac<=1); model.add(ab+ac-bc<=1); model.add(ac+bc-ab<=1)
    coefficients={}
    for pair in pairs:
        value=np.clip(p[pair],1e-6,1-1e-6)
        weight=int(np.rint((np.log(value)-np.log1p(-value))*1_000_000))
        # Prefer fewer connections only when rounded primary scores tie.
        coefficients[pair]=weight*(len(pairs)+1)-1
    model.maximize(sum(coefficients[pair]*connected[pair] for pair in pairs))
    solver=cp_model.CpSolver(); solver.parameters.max_time_in_seconds=float(time_limit)
    solver.parameters.num_search_workers=1; solver.parameters.random_seed=0
    status=solver.solve(model); name=solver.status_name(status)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return list(range(len(p))),{'status':name,'optimal':False,'fallback':'all_separate','seconds':solver.wall_time}
    plan=[]
    for a in range(len(p)):
        previous=next((b for b in range(a) if solver.value(connected[b,a])),None)
        plan.append(plan[previous] if previous is not None else max(plan,default=-1)+1)
    return plan,{'status':name,'optimal':status==cp_model.OPTIMAL,'fallback':None,'seconds':solver.wall_time,
                 'objective':solver.objective_value,'best_bound':solver.best_objective_bound,
                 'log_odds_integer_scale':1_000_000}


def solver_partition(probabilities):
    return solve_plan(probabilities)[0]
