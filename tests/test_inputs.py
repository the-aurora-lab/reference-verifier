import pytest

from reference_verifier.inputs import InputError, load_inputs

BIB_A = "@article{a, title = {First}}\n@article{b, title = {Second}}\n"
BIB_B = "@article{a, title = {First again}}\n@article{c, title = {Third}}\n"


def test_tex_limits_to_cited_keys_and_keeps_every_entry(tmp_path):
    (tmp_path / "a.bib").write_text(BIB_A)
    (tmp_path / "b.bib").write_text(BIB_B)
    (tmp_path / "main.tex").write_text("\\cite{a,c} \\bibliography{a,b,missing}\n")
    inp = load_inputs([tmp_path / "main.tex"])
    assert [r.key for r in inp.refs] == ["a", "c"]
    assert inp.refs[0].title == "First"  # the first entry of a repeated key wins, as in BibTeX
    assert [r.key for r in inp.entries] == ["a", "b", "a", "c"]
    assert inp.restricted and inp.cited == ["a", "c"]
    assert len(inp.warnings) == 1 and "missing.bib" in inp.warnings[0]


def test_all_and_nocite_star_check_everything(tmp_path):
    (tmp_path / "a.bib").write_text(BIB_A)
    (tmp_path / "main.tex").write_text("\\cite{a} \\bibliography{a}\n")
    assert [r.key for r in load_inputs([tmp_path / "main.tex"], include_uncited=True).refs] == ["a", "b"]
    (tmp_path / "main.tex").write_text("\\cite{a} \\nocite{*} \\bibliography{a}\n")
    inp = load_inputs([tmp_path / "main.tex"])
    assert inp.cites_everything and not inp.restricted and [r.key for r in inp.refs] == ["a", "b"]


def test_input_errors(tmp_path):
    with pytest.raises(InputError):
        load_inputs([tmp_path / "nope.bib"])
    (tmp_path / "main.tex").write_text("no bibliography here")
    with pytest.raises(InputError):
        load_inputs([tmp_path / "main.tex"])
