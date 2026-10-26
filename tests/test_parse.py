from reference_verifier.parse import parse_bib, scan_tex
from reference_verifier.parse.bibtex import family_name, normalize_doi, split_names

BIB = r"""
@string{nat = "Nature"}
@article{lecun2015,
  title = {Deep learning},
  author = {LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
  journal = nat, year = {2015}, doi = {10.1038/NATURE14539.}
}
@inproceedings{he2016,
  title = {Deep Residual Learning for Image Recognition},
  author = {Kaiming He and Xiangyu Zhang and Shaoqing Ren and Jian Sun},
  booktitle = {CVPR}, year = 2016,
  url = {https://doi.org/10.1109/CVPR.2016.90}
}
@article{vaswani2017,
  title = {Attention is All you Need},
  author = {Vaswani, Ashish and others},
  journal = {arXiv preprint arXiv:1706.03762}, year = {2017}
}
@misc{eprint,
  title = {{BERT}: Pre-training of Deep Bidirectional Transformers},
  author = {Devlin, Jacob}, eprint = {1810.04805v2}, archivePrefix = {arXiv}, year = {2018}
}
@article{accents,
  title = {{\"U}ber die {G}rundlagen},
  author = {M{\"u}ller, J{\"o}rg and van der Berg, Anna and {World Health Organization}},
  year = {1999}
}
@online{site, title = {Some web page}, url = {https://example.org}}
"""


def refs():
    return {r.key: r for r in parse_bib(BIB)}


def test_fields_and_strings():
    r = refs()["lecun2015"]
    assert r.entry_type == "article"
    assert r.title == "Deep learning"
    assert r.authors == ["LeCun", "Bengio", "Hinton"]
    assert r.year == 2015 and r.venue == "Nature"
    assert r.doi == "10.1038/nature14539"


def test_doi_from_url_and_first_last_names():
    r = refs()["he2016"]
    assert r.doi == "10.1109/cvpr.2016.90"
    assert r.authors == ["He", "Zhang", "Ren", "Sun"]


def test_arxiv_ids():
    assert refs()["vaswani2017"].arxiv_id == "1706.03762"
    assert refs()["vaswani2017"].authors == ["Vaswani"]  # "others" dropped
    assert refs()["eprint"].arxiv_id == "1810.04805"
    assert refs()["lecun2015"].arxiv_id is None


def test_latex_accents_and_braces():
    r = refs()["accents"]
    assert r.title == "Über die Grundlagen"
    assert r.authors == ["Müller", "van der Berg", "World Health Organization"]


def test_nonstandard_types_are_kept():
    assert refs()["site"].entry_type == "online"


def test_helpers():
    assert split_names("A and {Smith and Sons} and others") == (["A", "{Smith and Sons}"], True)
    assert family_name("Ludwig van Beethoven") == "Beethoven"
    assert family_name("van Beethoven, Ludwig") == "van Beethoven"
    assert normalize_doi("https://doi.org/10.1000/ABC%2F123") == "10.1000/abc/123"
    assert normalize_doi("no doi here") is None


def test_scan_tex(tmp_path):
    (tmp_path / "refs.bib").write_text("")
    (tmp_path / "sec.tex").write_text(r"As shown \citep[p.~3]{b,c}. % \cite{commented}")
    (tmp_path / "main.tex").write_text(
        r"\cite{a} \textcite{b} \input{sec} \nocite{d} \bibliography{refs,other}" "\n"
    )
    scan = scan_tex(tmp_path / "main.tex")
    assert scan.cited == ["a", "b", "d", "c"]
    assert [p.name for p in scan.bib_files] == ["refs.bib", "other.bib"]
    assert not scan.cites_everything


def test_sici_doi_keeps_angle_brackets():
    assert normalize_doi("10.1175/1520-0469(1963)020<0130:DNF>2.0.CO;2") == "10.1175/1520-0469(1963)020<0130:dnf>2.0.co;2"


def test_raw_fields_are_kept():
    r = parse_bib("@article{k, title = {T}, pages = {436--444}, volume = {521}, number = {7553}}")[0]
    assert r.fields["pages"] == "436--444" and r.fields["volume"] == "521" and r.fields["number"] == "7553"
    assert "ID" not in r.fields and "ENTRYTYPE" not in r.fields


def test_capitalised_cite_commands_and_locations(tmp_path):
    (tmp_path / "sec.tex").write_text("intro\n\\Parencite{c} and \\citep{a}\n")
    (tmp_path / "main.tex").write_text("\\Citet{a} says\n\\Textcite{b}\n\\input{sec}\n")
    scan = scan_tex(tmp_path / "main.tex")
    assert scan.cited == ["a", "b", "c"]
    assert scan.locations == {"a": ["main.tex:1", "sec.tex:2"], "b": ["main.tex:2"], "c": ["sec.tex:2"]}


def test_missing_inputs_are_reported(tmp_path):
    (tmp_path / "fig.pgf").write_text("")
    (tmp_path / "main.tex").write_text("\\input{contents/intro} \\input{fig.pgf} \\input{missing.tex}\n")
    assert scan_tex(tmp_path / "main.tex").missing_inputs == ["contents/intro", "missing.tex"]
