from __future__ import annotations

import numpy as np

from tools.medcpt_58.common import article_pair, rank_scores


def test_article_pair_preserves_hierarchy_and_content() -> None:
    pair = article_pair({"parents_context": "ICH Q9", "heading": "Risk review", "content": "Review risks."})
    assert pair == ["ICH Q9 | Risk review", "Review risks."]


def test_rank_scores_is_deterministic_on_ties() -> None:
    ranked = rank_scores(["chunk-b", "chunk-a", "chunk-c"], np.array([1.0, 1.0, 0.0]))
    assert [row["chunk_id"] for row in ranked] == ["chunk-a", "chunk-b", "chunk-c"]
