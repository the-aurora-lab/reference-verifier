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


def test_crossref_record_carries_pages_volume_issue_and_relations():
    from reference_verifier.sources.crossref import to_record

    rec = to_record({"DOI": "10.1101/2020.01.01.1", "title": ["T"], "type": "posted-content", "page": "1-9",
                     "volume": "3", "issue": "2",
                     "relation": {"is-preprint-of": [{"id-type": "doi", "id": "10.1038/S1", "asserted-by": "subject"}],
                                  "references": [{"id-type": "uri", "id": "https://x"}]}})
    assert (rec.pages, rec.volume, rec.issue) == ("1-9", "3", "2")
    assert rec.relations == {"is-preprint-of": ["10.1038/s1"]}
    assert to_record({"title": ["T"]}).pages is None


def test_crossref_record_carries_notices():
    from reference_verifier.sources.crossref import to_record

    rec = to_record({"DOI": "10.1/A", "title": ["RETRACTED: T"], "update-to": [
        {"DOI": "10.1/A", "type": "retraction", "source": "publisher", "updated": {"date-parts": [[2022, 11, 1]]}}],
        "updated-by": [
            {"DOI": "10.1/N", "type": "retraction", "source": "retraction-watch", "record-id": "65391",
             "updated": {"date-parts": [[2025, 6, 9]]}},
            {"DOI": "10.1/E", "type": "Erratum", "source": "publisher", "updated": {"date-parts": [[2025]]}},
            {"source": "publisher"}]})
    assert [(u.type, u.doi, u.date, u.source, u.record_id) for u in rec.updated_by] == [
        ("retraction", "10.1/n", "2025-06-09", "retraction-watch", "65391"),
        ("erratum", "10.1/e", "2025", "publisher", None)]
    assert [(u.type, u.doi, u.date) for u in rec.update_to] == [("retraction", "10.1/a", "2022-11-01")]
    assert to_record({"title": ["T"]}).updated_by == []


def test_arxiv_entry_carries_journal_ref():
    from reference_verifier.sources.arxiv import _entries

    xml = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
      <id>http://arxiv.org/abs/1512.03385v1</id><title>Deep Residual Learning</title><published>2015-12-10</published>
      <author><name>Kaiming He</name></author><arxiv:doi>10.1109/CVPR.2016.90</arxiv:doi>
      <arxiv:journal_ref>CVPR 2016,  770-778</arxiv:journal_ref></entry></feed>"""
    [(aid, rec)] = _entries(xml)
    assert aid == "1512.03385" and rec.doi == "10.1109/cvpr.2016.90" and rec.journal_ref == "CVPR 2016, 770-778"
