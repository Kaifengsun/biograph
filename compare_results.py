import json

with open('simulation_results/all_graphrag.json') as f:
    gg = json.load(f)
with open('simulation_results/all_results_no_graphrag_no_graphrag.json') as f:
    bl = json.load(f)

# normalize events to dict keyed by event_id
def events_dict(data):
    ev = data['events']
    if isinstance(ev, list):
        return {e['event_id']: e.get('metrics', e) for e in ev}
    return ev

bl_ev = events_dict(bl)
gg_ev = events_dict(gg)

hdr = '{:<8} {:>10} {:>10} {:>10} {:>10} {:>10} {:>10}'
row = '{:<8} {:>10} {:>10} {:>10} {:>10} {:>10} {:>10}'
print(hdr.format('Event','BL-SDE','GR-SDE','BL-PSC','GR-PSC','BL-SST','GR-SST'))
print('-'*72)
for e in ['E-01','E-02','E-03','E-04','E-05']:
    b = bl_ev.get(e,{})
    g = gg_ev.get(e,{})
    b_sde = b.get('sde_weeks', b.get('sde','N/A'))
    g_sde = g.get('sde_weeks', g.get('sde','N/A'))
    b_psc = b.get('psc',0)
    g_psc = g.get('psc',0)
    b_sst = b.get('sst_reproduced','N/A')
    g_sst = g.get('sst_reproduced','N/A')
    print(row.format(e, str(b_sde), str(g_sde),
        str(round(b_psc,3)), str(round(g_psc,3)),
        str(b_sst), str(g_sst)))

print()
bs = bl['summary']
gs = gg['summary']
# normalize mean_sde key
bs_sde = bs.get('mean_sde', bs.get('mean_sde_weeks','N/A'))
gs_sde = gs.get('mean_sde', gs.get('mean_sde_weeks','N/A'))
print('Summary:')
print('  Mean SDE:  BL={}  GR={}'.format(bs_sde, gs_sde))
print('  Mean PSC:  BL={}  GR={}'.format(round(bs.get('mean_psc',0),3), round(gs.get('mean_psc',0),3)))
print('  SST repro: BL={}  GR={}'.format(bs.get('sst_reproduced','N/A'), gs.get('sst_reproduced','N/A')))
print('  Queries:   BL={}  GR={}'.format(bs.get('total_rag_queries',0), gs.get('total_rag_queries',0)))

# SDE improvement
if isinstance(bs_sde,(int,float)) and isinstance(gs_sde,(int,float)):
    delta = bs_sde - gs_sde
    pct = delta / bs_sde * 100
    print('\n  SDE delta: {:.1f} weeks ({:.1f}% reduction)'.format(delta, pct))
