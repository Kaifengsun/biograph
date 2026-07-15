"""诊断 chunk_id 匹配问题"""
import sys
sys.path.insert(0, '.')
from pharma_graphrag.config import GraphRAGConfig
from pharma_graphrag.retriever import GraphRAGRetriever

config = GraphRAGConfig()
ret = GraphRAGRetriever(config)

# 获取 stage1 的返回
print("=== Stage 1 test ===")
chunks, ents = ret.stage1_bottom_up("What are ICH Q10 requirements for change control documentation?")
print("Returned chunks:")
for c in chunks[:5]:
    print(f"  chunk_id={c.chunk_id!r}  doc={c.doc_id!r}  score={c.score:.3f}")

print()
print("=== Neo4j chunk sample ===")
with ret.neo4j_driver.session() as s:
    r = s.run("MATCH (n:DocChunk) WHERE n.doc_id='ich_q10' RETURN n.chunk_id LIMIT 5").data()
    for x in r:
        print("  neo4j:", x['n.chunk_id'])
    
    print()
    # keyword search test
    r2 = s.run("MATCH (n:DocChunk) WHERE n.doc_id='ich_q10' AND toLower(n.content) CONTAINS 'change' RETURN n.chunk_id LIMIT 3").data()
    print("  keyword='change' results:", [x['n.chunk_id'] for x in r2])

print()
print("=== Chunk store sample ===")
from pathlib import Path
import json
chunk_dir = Path("data/chunks")
files = list(chunk_dir.glob("*.json"))[:3]
for f in files:
    with open(f, encoding='utf-8') as fp:
        data = json.load(fp)
    if isinstance(data, list):
        print(f"  {f.name}: {len(data)} items, first chunk_id={data[0].get('chunk_id', data[0].get('id','?'))!r}")
    elif isinstance(data, dict):
        print(f"  {f.name}: dict, keys={list(data.keys())[:3]}")
