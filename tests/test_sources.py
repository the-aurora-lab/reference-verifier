from reference_verifier.http import Http
from reference_verifier.model import Reference
from reference_verifier.sources import Sources


def test_registry_is_dropped_after_repeated_failures(monkeypatch):
    src = Sources(Http(), search_order=("crossref", "dblp"))
    calls = []

    def fake(name, ref):
        calls.append(name)
        if name == "dblp":
            raise ValueError("bot challenge page")
        return []

    monkeypatch.setattr(src, "_search", fake)
    ref = Reference("k", "article", "t")
    for _ in range(4):
        assert src.search("dblp", ref) is None
    assert calls.count("dblp") == 2 and "dblp" in src.unavailable
    assert src.search("crossref", ref) == []


def test_semantic_scholar_only_with_a_key():
    assert "semanticscholar" not in Sources(Http()).search_order
    assert "semanticscholar" in Sources(Http(), s2_key="k").search_order
