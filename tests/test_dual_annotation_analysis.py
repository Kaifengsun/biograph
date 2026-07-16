import pytest

from tools.dual_annotation_60.analyze_dual_annotations import (
    agreement_metrics,
    binary_metrics,
    cohen_kappa,
    gwet_ac1,
)


def test_perfect_binary_agreement() -> None:
    labels = [True, False, True, False]
    metrics = binary_metrics(labels, labels)
    assert metrics["exact_agreement"] == 1.0
    assert metrics["cohen_kappa"] == 1.0
    assert metrics["gwet_ac1"] == 1.0
    assert metrics["positive_agreement"] == 1.0


def test_question_prevalence_paradox_is_visible() -> None:
    labels_a = ["Answerable"] * 60
    labels_b = ["Answerable"] * 58 + ["Needs Revision"] * 2
    metrics = agreement_metrics(labels_a, labels_b, ["Answerable", "Needs Revision", "Invalid"])
    assert metrics["exact_agreement"] == pytest.approx(58 / 60)
    assert metrics["cohen_kappa"] == 0.0
    assert metrics["gwet_ac1"] > 0.96


def test_nominal_agreement_functions_accept_empty_input() -> None:
    assert cohen_kappa([], [], ["a", "b"]) is None
    assert gwet_ac1([], [], ["a", "b"]) is None
