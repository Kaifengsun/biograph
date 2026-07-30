import os

from neo4j import GraphDatabase

password = os.getenv("NEO4J_PASSWORD", "")
if not password:
    raise RuntimeError("NEO4J_PASSWORD is not set")
d = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), password),
)
with d.session() as s:
    # All unique doc_ids in DocChunk
    r3 = s.run('MATCH (n:DocChunk) RETURN DISTINCT n.doc_id ORDER BY n.doc_id').data()
    print('=== All doc_ids in DocChunk ===')
    for x in r3:
        print(x['n.doc_id'])
    print()

    # Check a few chunk IDs from regulatory docs
    r = s.run('MATCH (n:DocChunk) WHERE n.doc_id STARTS WITH "ich" RETURN n.chunk_id, n.doc_id, n.heading LIMIT 5').data()
    print('=== ICH chunks sample ===')
    for x in r:
        print(x['n.chunk_id'], '|', x['n.doc_id'], '|', x['n.heading'])
d.close()
