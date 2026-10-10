"""Small regularized pairwise preference model, not a layout generator.

Numeric choices train this scorer. Free-text comments are retained as design
feedback, not silently converted to labels or purportedly learned by this model.
"""
import numpy as np
from shapely.geometry import shape

FEATURES=['places','links','opening_sharing','rotation_ratio','T_shorter_approach_s',
          'T_longer_approach_s','CT_shorter_distribution_s','CT_longer_distribution_s',
          'T_approach_gap_s','CT_distribution_gap_s','worst_CT_late_arrival_s',
          'log_floor_area','mean_passage_width']


def features(candidate):
    t=[candidate['timings'][f'T-{s}']['seconds_proxy'] for s in ('A','B')]
    ct=[candidate['timings'][f'CT-{s}']['seconds_proxy'] for s in ('A','B')]
    return np.array([len(candidate['nodes']),len(candidate['edges']),
        candidate['descriptors']['opening_sharing'],candidate['descriptors']['rotation_ratio'],
        min(t),max(t),min(ct),max(ct),abs(t[0]-t[1]),abs(ct[0]-ct[1]),
        max(c-t for c,t in zip(ct,t)),np.log1p(shape(candidate['floor']).area),
        np.mean([e['width'] for e in candidate['edges']])],dtype=float)


def train(candidates,pairs):
    """Fit preferred-minus-less-preferred logistic comparisons with L2 penalty."""
    if not pairs:raise ValueError('Human preference comparisons are required.')
    keys=list(candidates);x=np.stack([features(candidates[k]) for k in keys])
    mean=x.mean(0);scale=x.std(0);scale[scale<1e-6]=1
    standardized={k:(features(candidates[k])-mean)/scale for k in keys}
    delta=np.stack([standardized[a]-standardized[b] for a,b in pairs])
    weight=np.zeros(len(FEATURES));penalty=.3
    for _ in range(600):
        margin=np.clip(delta@weight,-40,40)
        gradient=-(delta/(1+np.exp(margin))[:,None]).mean(0)+penalty*weight
        weight-=.08*gradient
    before=float(np.log(2));after=float(np.logaddexp(0,-delta@weight).mean())
    return {'kind':'L2-regularized pairwise logistic preference scorer',
        'features':FEATURES,'mean':mean.tolist(),'scale':scale.tolist(),'weights':weight.tolist(),
        'training_pairs':len(pairs),'distinct_training_layouts':len(candidates),
        'training_log_loss_before':before,'training_log_loss_after':after,
        'validation':'No independent human-rated holdout yet; fitting improvement is not generalization.',
        'generator_weights_updated':False,'learns_free_text_comments':False}


def score(model,candidate):
    x=(features(candidate)-np.array(model['mean']))/np.array(model['scale'])
    return float(x@np.array(model['weights']))
