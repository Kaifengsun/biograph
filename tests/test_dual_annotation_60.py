from collections import Counter

from evaluate_bm25_enrichment_ablation import load_corpus
from tools.dual_annotation_60.prepare_dual_annotation_pack import (
    CORPUS,
    SLICE_COUNTS,
    blind_passage_id,
    historical_questions,
    normalize_question,
    select_anchors,
)


def test_anchor_selection_matches_preregistered_slice_counts() -> None:
    anchors = select_anchors(load_corpus(CORPUS))
    assert len(anchors) == 60
    assert Counter(item["query_slice"] for item in anchors) == SLICE_COUNTS
    assert len({item["query_id"] for item in anchors}) == 60


def test_cross_document_anchors_use_two_distinct_documents() -> None:
    anchors = select_anchors(load_corpus(CORPUS))
    for item in anchors:
        if item["query_slice"] == "cross_document":
            assert len(item["anchors"]) == 2
            assert len({row["doc_id"] for row in item["anchors"]}) == 2


def test_blind_passage_ids_are_stable_and_query_specific() -> None:
    first = blind_passage_id("DA60-SC01", "chunk-a")
    assert first == blind_passage_id("DA60-SC01", "chunk-a")
    assert first != blind_passage_id("DA60-SC02", "chunk-a")
    assert first != blind_passage_id("DA60-SC01", "chunk-b")
    assert first.startswith("P-")


def test_historical_registry_contains_prior_formal_question() -> None:
    prior = normalize_question(
        "After an API synthesis change may introduce a mutagenic impurity, what does ICH M7 require "
        "for assessing the impact of the change and developing an appropriate control strategy?"
    )
    assert prior in historical_questions()
