"""
制药供应链知识图谱 — 主入口
=============================
用法:
    python -m pharma_supply_chain.main                         # 仅使用核心数据
    python -m pharma_supply_chain.main --fda                   # + FDA 增强
    python -m pharma_supply_chain.main --rxnorm                # + RxNorm 增强
    python -m pharma_supply_chain.main --chembl                # + ChEMBL 增强
    python -m pharma_supply_chain.main --all                   # 全部数据源
    python -m pharma_supply_chain.main --all --cache           # 全部(优先用缓存)
    python -m pharma_supply_chain.main --fda --test            # 测试 FDA 连接

输出:
    output/pharma_kg_nodes.csv      节点文件（Neo4j LOAD CSV 兼容）
    output/pharma_kg_edges.csv      边文件
    output/import_neo4j.cypher      Neo4j 导入脚本
    output/kg_statistics.json       统计报告
"""

import argparse
import sys
import time

from . import config  # 触发代理配置
from .kg_builder import PharmaKGBuilder
from .fda_fetcher import FDADataFetcher, test_fda_connection
from .core_data import DRUGS


# 用于 API 查询的英文药名列表
DRUG_ENGLISH_NAMES = []
for _d in DRUGS:
    _en = _d["name"].split("（")[0].split("(")[0].strip()
    DRUG_ENGLISH_NAMES.append(_en.lower())


def main():
    parser = argparse.ArgumentParser(description="制药供应链知识图谱构建工具")
    parser.add_argument("--fda", action="store_true",
                        help="从 FDA OpenAPI 拉取增强数据")
    parser.add_argument("--rxnorm", action="store_true",
                        help="从 RxNorm API 拉取药物成分/交互数据")
    parser.add_argument("--chembl", action="store_true",
                        help="从 ChEMBL API 拉取靶点/适应症数据")
    parser.add_argument("--all", action="store_true",
                        help="启用全部数据源（FDA + RxNorm + ChEMBL）")
    parser.add_argument("--cache", action="store_true",
                        help="优先使用本地缓存数据（跳过 API 调用）")
    parser.add_argument("--test", action="store_true",
                        help="测试 FDA API 连通性后退出")
    args = parser.parse_args()

    if args.all:
        args.fda = args.rxnorm = args.chembl = True

    # ---- 1. 测试 FDA 连通性 ----
    if args.test:
        print("正在测试 FDA API 连通性...")
        test_fda_connection()
        return

    print("╔" + "═" * 58 + "╗")
    print("║  制药供应链知识图谱 — 多源数据自动构建流水线              ║")
    print("╚" + "═" * 58 + "╝")
    start_time = time.time()

    # ---- 2. 获取 FDA 增强数据 ----
    fda_data = None
    if args.fda:
        print("\n[ FDA 数据获取 ]")
        fetcher = FDADataFetcher()
        cache_path = config.DATA_DIR + "/fda_data.json"

        if args.cache:
            fda_data = fetcher.load_fda_data(cache_path)
            if fda_data:
                print(f"✓ 已从缓存加载 FDA 数据，覆盖 {len(fda_data)} 种药品")

        if not fda_data:
            # 扩展到所有 47 种药
            fda_data = fetcher.fetch_all_for_drugs(DRUG_ENGLISH_NAMES)
            fetcher.save_fda_data(fda_data)
            print(f"✓ FDA 数据获取完成，覆盖 {len(fda_data)} 种药品")

    # ---- 3. 获取 RxNorm 增强数据 ----
    rxnorm_data = None
    if args.rxnorm:
        print("\n[ RxNorm 数据获取 ]")
        from .rxnorm_fetcher import RxNormFetcher
        rxnorm = RxNormFetcher()

        if args.cache:
            rxnorm_data = rxnorm.load_data()
            if rxnorm_data:
                print(f"✓ 已从缓存加载 RxNorm 数据，覆盖 {len(rxnorm_data)} 种药品")

        if not rxnorm_data:
            rxnorm_data = rxnorm.fetch_all_for_drugs(DRUG_ENGLISH_NAMES)
            rxnorm.save_data(rxnorm_data)
            print(f"✓ RxNorm 数据获取完成，覆盖 {len(rxnorm_data)} 种药品")

    # ---- 4. 获取 ChEMBL 增强数据 ----
    chembl_data = None
    if args.chembl:
        print("\n[ ChEMBL 数据获取 ]")
        from .chembl_fetcher import ChEMBLFetcher
        chembl = ChEMBLFetcher()

        if args.cache:
            chembl_data = chembl.load_data()
            if chembl_data:
                print(f"✓ 已从缓存加载 ChEMBL 数据，覆盖 {len(chembl_data)} 种药品")

        if not chembl_data:
            chembl_data = chembl.fetch_all_for_drugs(DRUG_ENGLISH_NAMES)
            chembl.save_data(chembl_data)
            print(f"✓ ChEMBL 数据获取完成，覆盖 {len(chembl_data)} 种药品")

    # ---- 5. 构建知识图谱 ----
    builder = PharmaKGBuilder()
    nodes_df, edges_df = builder.build_full_graph(
        fda_data=fda_data,
        rxnorm_data=rxnorm_data,
        chembl_data=chembl_data,
    )

    # ---- 6. 分析 & 打印统计 ----
    stats = builder.analyze_graph(nodes_df, edges_df)
    builder.print_stats(stats)

    # ---- 7. 导出 ----
    print("\n[ 导出文件 ]")
    builder.export_csv(nodes_df, edges_df)
    builder.export_stats(stats)
    builder.export_neo4j_cypher(nodes_df, edges_df)

    elapsed = time.time() - start_time
    print(f"\n✅ 全部完成！耗时 {elapsed:.1f}s")
    print(f"   节点: {len(nodes_df)} | 边: {len(edges_df)}")

    # 按类型汇总
    if "label" in nodes_df.columns:
        node_summary = nodes_df["label"].value_counts().to_dict()
        print(f"   节点分布: {node_summary}")
    if "relation" in edges_df.columns:
        edge_summary = edges_df["relation"].value_counts().to_dict()
        print(f"   边分布: {edge_summary}")

    print(f"   输出目录: {config.OUTPUT_DIR}")


if __name__ == "__main__":
    main()
