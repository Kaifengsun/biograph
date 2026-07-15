import json

with open('simulation_results/all_graphrag.json') as f:
    d = json.load(f)

print("=== GRAPHRAG EVENTS ===")
events = d['events'] if isinstance(d['events'], list) else [{'event_id': k, **v} for k,v in d['events'].items()]
for ev in events:
    eid = ev.get('event_id', '')
for eid, ev in [(e.get('event_id',''), e) for e in events]:
    print("--- {} ---".format(eid))
    for k, v in ev.items():
        if k not in ('weekly_severity', 'sst_sequence'):
            print("  {}: {}".format(k, v))
    sst = ev.get('sst_sequence', {})
    if sst:
        print("  sst_sequence:", sst)
    print()

print("=== SUMMARY ===")
for k, v in d['summary'].items():
    print("  {}: {}".format(k, v))

print()
with open('simulation_results/all_results_no_graphrag_no_graphrag.json') as f:
    b = json.load(f)

print("=== BASELINE EVENTS ===")
for ev in b['events']:
    print("--- {} ---".format(ev.get('event_id')))
    for k, v in ev.items():
        if k not in ('weekly_severity',):
            print("  {}: {}".format(k, v))
    print()

print("=== BASELINE SUMMARY ===")
for k, v in b['summary'].items():
    print("  {}: {}".format(k, v))
