from reference_verifier.check import check_all, check_reference
from reference_verifier.model import Record, Reference, Status

RESNET = Record("Crossref", "Deep Residual Learning for Image Recognition", ["He", "Zhang", "Ren", "Sun"], 2016,
                "CVPR", "10.1109/cvpr.2016.90")
OTHER = Record("Crossref", "A Survey of Protein Folding Benchmarks", ["Doe"], 2020, "J", "10.1/other")


class FakeSources:
    """Stands in for the registries: DOIs and title searches answer from fixed tables."""

    search_order = ("crossref", "dblp", "arxiv", "openalex")

    def __init__(self, dois=None, search=None, arxiv=None, unreachable=False):
        self.dois = dois or {}
        self.results = search or {}
        self.arxiv = arxiv or {}
        self.unreachable = unreachable
        self.searched = []

    def doi(self, doi):
        if self.unreachable:
            return None, None, ["Crossref", "doi.org"]
        rec = self.dois.get(doi)
        return rec, rec is not None, ["Crossref"] if rec else ["Crossref", "doi.org"]

    def arxiv_id(self, aid):
        rec = self.arxiv.get(aid)
        return rec, rec is not None

    def pmid(self, pmid):
        return None, False

    def prefetch_arxiv(self, ids):
        pass

    def search(self, name, ref):
        self.searched.append(name)
        if self.unreachable:
            return None
        return self.results.get(name, [])


def ref(**kw):
    base = dict(key="he2016", entry_type="inproceedings", title="Deep residual learning for image recognition",
                authors=["He", "Zhang"], year=2016)
    base.update(kw)
    return Reference(**base)


def test_found_by_doi_without_searching():
    src = FakeSources(dois={"10.1109/cvpr.2016.90": RESNET})
    r = check_reference(ref(doi="10.1109/cvpr.2016.90"), src)
    assert r.status is Status.FOUND and r.match is RESNET
    assert src.searched == []


def test_found_by_title_search_stops_early():
    src = FakeSources(search={"crossref": [OTHER], "dblp": [RESNET]})
    r = check_reference(ref(), src)
    assert r.status is Status.FOUND and r.match is RESNET
    assert src.searched == ["crossref", "dblp"]


def test_doi_of_another_work():
    src = FakeSources(dois={"10.1/other": OTHER}, search={"crossref": [RESNET]})
    r = check_reference(ref(doi="10.1/other"), src)
    assert r.status is Status.DOI_OTHER_WORK
    assert "belongs to a different work" in r.note and "exists" in r.note


def test_unregistered_doi_but_work_exists():
    src = FakeSources(search={"crossref": [RESNET]})
    r = check_reference(ref(doi="10.9999/fake"), src)
    assert r.status is Status.DOI_NOT_FOUND
    assert "the DOI is wrong" in r.note


def test_not_found():
    src = FakeSources(search={"crossref": [OTHER]})
    r = check_reference(ref(title="Quantum transformers for genome alignment"), src)
    assert r.status is Status.NOT_FOUND
    assert r.severity == "high"
    assert src.searched == list(FakeSources.search_order)


def test_not_found_book_is_low_severity():
    r = check_reference(ref(entry_type="book", title="An obscure handbook"), FakeSources())
    assert r.status is Status.NOT_FOUND and r.severity == "low"


def test_same_title_other_authors_is_uncertain():
    src = FakeSources(search={"crossref": [RESNET]})
    r = check_reference(ref(authors=["Goodfellow", "Bengio"]), src)
    assert r.status is Status.UNCERTAIN and "authors differ" in r.note


def test_web_pages_are_skipped_and_unreachable_is_an_error():
    assert check_reference(ref(entry_type="online"), FakeSources()).status is Status.SKIPPED
    assert check_reference(ref(), FakeSources(unreachable=True)).status is Status.ERROR


def test_check_all_keeps_order():
    src = FakeSources(search={"crossref": [RESNET]})
    refs = [ref(key=f"k{i}") for i in range(6)]
    assert [r.ref.key for r in check_all(refs, src, workers=3)] == [f"k{i}" for i in range(6)]


def test_renamed_arxiv_paper_by_the_same_authors_is_found():
    new = Record("arXiv", "CodeGen: An Open Large Language Model for Code", ["Erik Nijkamp", "Bo Pang"], 2022,
                 full_names=True)
    r = check_reference(ref(title="A conversational paradigm for program synthesis", authors=["Nijkamp", "Pang"],
                            year=2022, arxiv_id="2203.13474"), FakeSources(arxiv={"2203.13474": new}))
    assert r.status is Status.FOUND and "now titled" in r.note


def test_random_arxiv_id_sharing_a_common_surname_is_not_enough():
    other = Record("arXiv", "Sparse attention for video", ["Wei Wang", "Anna Kowalski", "Tom Berg"], 2019,
                   full_names=True)
    r = check_reference(ref(title="Scaling laws for theorem proving", authors=["Wang", "Garcia", "Okafor"],
                            year=2024, arxiv_id="1901.00001"), FakeSources(arxiv={"1901.00001": other}))
    assert r.status is Status.NOT_FOUND


def test_versioned_software_doi_is_found():
    zenodo = Record("doi.org", "EleutherAI/lm-evaluation-harness: v0.4.13", ["Sutawika", "Gao"], 2024,
                    doi="10.5281/zenodo.5371628", kind="software")
    r = check_reference(ref(entry_type="misc", title="A framework for few-shot language model evaluation",
                            authors=["Gao", "Tow"], year=2021, doi="10.5281/zenodo.5371628"),
                        FakeSources(dois={"10.5281/zenodo.5371628": zenodo}))
    assert r.status is Status.FOUND and "now titled" in r.note


def test_code_releases_are_skipped():
    r = check_reference(ref(entry_type="misc", title="GPT-J-6B", url="https://github.com/kingoflolz/mesh-transformer-jax"),
                        FakeSources())
    assert r.status is Status.SKIPPED


def test_grey_literature_miss_is_low_severity():
    r = check_reference(ref(entry_type="article", title="Improving language understanding by generative pre-training",
                            venue="OpenAI blog"), FakeSources())
    assert r.status is Status.NOT_FOUND and r.severity == "low"


def test_unreachable_registries_are_not_listed_as_searched():
    class HalfDown(FakeSources):
        def search(self, name, ref):
            return None if name == "dblp" else []
    r = check_reference(ref(title="Quantum attention for genome alignment"), HalfDown())
    assert r.status is Status.NOT_FOUND
    assert "DBLP could not be reached" in r.note and "DBLP" not in r.sources_tried
