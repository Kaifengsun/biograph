import math

import pytest

from tools.modern_reranker_58.common import aggregate, metric_row, rank_scored_candidates


def test_rank_scored_candidates_uses_locked_tie_breaking():
    rows = [
        {"chunk_id": "z", "bm25_rank": 2, "score": 1.0},
        {"chunk_id": "b", "bm25_rank": 1, "score": 1.0},
        {"chunk_id": "a", "bm25_rank": 1, "score": 1.0},
        {"chunk_id": "q", "bm25_rank": 3, "score": 2.0},
    ]
    ranked = rank_scored_candidates(rows)
    assert [row["chunk_id"] for row in ranked] == ["q", "a", "b", "z"]
    assert [row["reranker_rank"] for row in ranked] == [1, 2, 3, 4]


def test_rank_scored_candidates_rejects_duplicates():
    with pytest.raises(ValueError, match="duplicate"):
        rank_scored_candidates([
            {"chunk_id": "a", "bm25_rank": 1, "score": 1.0},
            {"chunk_id": "a", "bm25_rank": 2, "score": 0.0},
        ])


def test_metric_row_matches_hand_calculation_with_multiple_gold_chunks():
    ranking = [f"c{index}" for index in range(1, 51)]
    row = metric_row(ranking, {"c2", "c5"})
    ideal = 1.0 + 1.0 / math.log2(3)
    observed = 1.0 / math.log2(3) + 1.0 / math.log2(6)
    assert row["hit_at_1"] == 0.0
    assert row["hit_at_3"] == 1.0
    assert row["hit_at_5"] == 1.0
    assert row["hit_at_50"] == 1.0
    assert row["mrr_at_50"] == 0.5
    assert row["ndcg_at_5"] == pytest.approx(observed / ideal)


def test_metric_row_assigns_zero_when_gold_is_outside_top_50():
    ranking = [f"c{index}" for index in range(1, 51)]
    row = metric_row(ranking, {"not_retrieved"})
    assert row == {
        "hit_at_1": 0.0, "hit_at_3": 0.0, "hit_at_5": 0.0,
        "hit_at_50": 0.0, "mrr_at_50": 0.0, "ndcg_at_5": 0.0,
    }


def test_aggregate_computes_macro_mean():
    value = aggregate([
        {"hit_at_1": 1.0, "mrr_at_50": 1.0},
        {"hit_at_1": 0.0, "mrr_at_50": 0.5},
    ])
    assert value == {"hit_at_1": 0.5, "mrr_at_50": 0.75}
