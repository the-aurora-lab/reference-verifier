from reference_verifier.match import author_match, family_key, is_found, normalize_title, score, title_similarity
from reference_verifier.model import Record, Reference


def test_normalize_title():
    assert normalize_title(r"\emph{Deep} Learning: A {R}eview & Outlook") == "deep learning a review and outlook"
    assert normalize_title("Über die Grundlagen") == "uber die grundlagen"


def test_similarity_tolerates_typos_and_dropped_subtitles():
    assert title_similarity("Attention is all you need", "Attention Is All You Need.") == 1.0
    assert title_similarity("Deep residual learning for image recognitoin", "Deep Residual Learning for Image Recognition") > 0.95
    assert title_similarity("Graph neural networks", "Graph neural networks: a review of methods and applications") >= 0.95


def test_similarity_rejects_different_papers():
    assert title_similarity("Attention is all you need for graphs", "Attention is all you need") < 0.9
    assert title_similarity("Quantum transformers for protein folding", "Deep residual learning for image recognition") < 0.5


def test_family_key():
    assert family_key("van der Berg") == "berg"
    assert family_key("Müller") == "muller"


def test_author_match_family_and_display_names():
    rec = Record("x", "t", ["Kaiming He", "Xiangyu Zhang", "Jian Sun"], full_names=True)
    ok, first, overlap = author_match(["He", "Zhang", "Ren", "Sun"], rec)
    assert ok and first and overlap == 1.0
    rec2 = Record("x", "t", ["Smith", "Jones"])
    assert author_match(["Doe", "Roe"], rec2) == (False, False, 0.0)
    assert author_match([], rec2) == (None, None, None)


def test_is_found_needs_authors_or_year_when_title_matches():
    ref = Reference("k", "article", "Deep learning", ["LeCun"], 2015)
    assert is_found(score(ref, Record("x", "Deep Learning", ["Yann LeCun"], 2015, full_names=True)))
    assert not is_found(score(ref, Record("x", "Deep Learning", ["Ian Goodfellow"], 2016, full_names=True)))
    no_authors = Reference("k", "article", "Deep learning", [], 2015)
    assert is_found(score(no_authors, Record("x", "Deep learning", [], 2016)))
    assert not is_found(score(no_authors, Record("x", "Deep learning", [], 1998)))


def test_short_main_title_needs_matching_authors():
    full = "BLEU: a method for automatic evaluation of machine translation"
    assert title_similarity(full, "BLEU") == 0.90
    ref = Reference("k", "inproceedings", full, ["Papineni", "Roukos"], 2002)
    assert is_found(score(ref, Record("x", "BLEU", ["Papineni", "Roukos"], 2002)))
    assert not is_found(score(ref, Record("x", "BLEU", ["Lin"], 2004)))


def test_crossref_subtitle_is_joined():
    from reference_verifier.sources.crossref import to_record
    rec = to_record({"title": ["BLEU"], "subtitle": ["a method for automatic evaluation of machine translation"],
                     "author": [{"family": "Papineni"}], "DOI": "10.3115/1073083.1073135", "type": "proceedings-article"})
    assert rec.title == "BLEU: a method for automatic evaluation of machine translation"
    assert rec.kind == "proceedings-article"


def test_series_heading_counts_only_one_way():
    quine = "Main Trends in Recent Philosophy: Two Dogmas of Empiricism"
    assert title_similarity("Two Dogmas of Empiricism", quine) >= 0.90
    assert title_similarity("Attention is all you need for graphs", "Attention is all you need") < 0.90


def test_retraction_prefixes_are_ignored():
    assert title_similarity("Paroles à la dérive", "RETRACTED ARTICLE: Paroles à la dérive") == 1.0
    assert title_similarity("Stimulus-triggered fate conversion of somatic cells into pluripotency",
                            "Retraction Note: Stimulus-triggered fate conversion of somatic cells into pluripotency") == 1.0


def test_consortium_authors_fall_back_to_the_year():
    rec = Record("x", "Global burden of 369 diseases", ["GBD 2019 Diseases and Injuries Collaborators"], 2020)
    assert author_match(["Vos", "Lim"], rec) == (None, None, None)
    ref = Reference("k", "article", "Global burden of 369 diseases", ["Vos", "Lim"], 2020)
    assert is_found(score(ref, rec))
