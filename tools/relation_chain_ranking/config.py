from __future__ import annotations

PROJECTED_RELATIONS = (
    "AFFECTS_NDC_PRODUCT",
    "REPORTED_BY",
    "HAS_ACTIVE_INGREDIENT",
    "CONTAINS_API",
    "SUPPLIED_BY",
    "COVERS_TOPIC",
    "SUPERSEDES",
    "USES_PRINCIPLES_FROM",
    "COMPLEMENTS",
    "INTERPRETS",
    "APPLIES_DEFINITION_FROM",
    "REQUIRES_COMPLIANCE_WITH",
)

ALIAS_PROPERTY_ALLOWLIST = (
    "doc_id",
    "package_ndc",
    "generic_name",
    "ingredient_name",
    "company_name",
    "reference_name",
    "topic_name",
    "cas",
)

RELATION_ALIASES = {
    "AFFECTS_NDC_PRODUCT": ("affects ndc product", "package ndc", "ndc product"),
    "REPORTED_BY": ("reported by", "company reported", "reported"),
    "HAS_ACTIVE_INGREDIENT": ("has active ingredient", "active ingredient", "ingredient"),
    "CONTAINS_API": ("contains api", "linked api", "api is linked"),
    "SUPPLIED_BY": (
        "supplied by",
        "manufacturers supply",
        "manufacturer supply",
        "suppliers",
        "supplier",
    ),
    "COVERS_TOPIC": ("covers topic", "topic does", "topic is", "linked topic"),
    "SUPERSEDES": ("supersedes", "superseding", "replaces", "replacement"),
    "USES_PRINCIPLES_FROM": (
        "uses principles from",
        "source of principles",
        "principle dependencies",
        "supplies principles",
        "foundation",
    ),
    "COMPLEMENTS": ("complements", "complementary", "complement"),
    "INTERPRETS": ("interprets", "interpreted by", "interpretation"),
    "APPLIES_DEFINITION_FROM": (
        "applies definition from",
        "source of applied definitions",
        "applied definitions",
    ),
    "REQUIRES_COMPLIANCE_WITH": (
        "requires compliance with",
        "ensure full compliance",
        "compliance with",
        "direct readers to consult",
    ),
}

STOP_WORDS = frozenset(
    "a an and are as at be both by does for from how in is it of on or that the their "
    "then this through to was what when which who with".split()
)

METHODS = ("b0", "m0", "cue_off", "direction_off", "r1")
WEIGHTS = {
    "node_token_f1": 1.0,
    "provenance": 0.1,
    "extra_edge": -0.02,
    "relation_coverage": 2.0,
    "relation_precision": 0.5,
    "orientation": 0.5,
}

MAX_ANCHORS = 64
MAX_EDGES = 5
MAX_CANDIDATES = 50_000
MAX_EDGE_ATTEMPTS = 2_000_000
BOOTSTRAP_ITERATIONS = 10_000
BOOTSTRAP_SEED = 20_260_718

FORBIDDEN_INFERENCE_KEYS = frozenset(
    {
        "answer",
        "draft_answer",
        "final_answer",
        "gold",
        "gold_edges",
        "gold_nodes",
        "edges",
        "nodes",
        "target",
        "reviewer",
        "reviewer_a",
        "reviewer_b",
        "adjudication",
        "consensus",
    }
)

