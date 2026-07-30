import importlib

import pytest


def test_graphrag_neo4j_password_has_no_literal_default(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    from pharma_graphrag.config import Neo4jConfig

    assert Neo4jConfig().password == ""


def test_neo4j_import_requires_password_environment_variable(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    module = importlib.import_module("pharma_supply_chain.neo4j_import")
    module = importlib.reload(module)

    assert module.NEO4J_PASSWORD == ""
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD is not set"):
        module.import_to_neo4j()
