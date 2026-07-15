import json, numpy as np
with open('data/ablation_results_abc.json', encoding='utf-8') as f:
    d = json.load(f)
agg = d['aggregate']
print('=== Current Results (n=23 queries) ===')
for v in ['A','B','C']:
    if v in agg:
        a = agg[v]
        print('Variant {}: R@5={:.3f} R@10={:.3f} MRR={:.3f}'.format(
            v, a['recall5_mean'], a['recall10_mean'], a['mrr_mean']))
print()
# Breakdown by category
cats = {}
for q in d['queries']:
    c = q['category']
    cats.setdefault(c, []).append(q)
for cat, qs in cats.items():
    r5a = [q['variants']['A']['recall5'] for q in qs if 'recall5' in q['variants'].get('A',{})]
    if r5a:
        print('{}: mean_R@5={:.3f} (n={})'.format(cat, np.mean(r5a), len(r5a)))

# Check queries with non-zero results
print()
print('=== Non-zero queries ===')
for q in d['queries']:
    a = q['variants'].get('A', {})
    if a.get('recall5', 0) > 0 or a.get('mrr', 0) > 0:
        print('  {} [{}]: R@5={:.3f} MRR={:.3f}'.format(q['qid'], q['category'], a['recall5'], a['mrr']))
