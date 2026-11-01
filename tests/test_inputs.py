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


def test_display_path_never_shows_the_home_folder(tmp_path, monkeypatch):
    from reference_verifier.inputs import display_path

    (tmp_path / "paper").mkdir()
    (tmp_path / "elsewhere").mkdir()
    bib = (tmp_path / "paper" / "refs.bib").resolve()
    monkeypatch.chdir(tmp_path)
    assert display_path(bib) == "paper/refs.bib"
    monkeypatch.chdir(tmp_path / "paper")
    assert display_path(str(bib)) == "refs.bib"
    monkeypatch.chdir(tmp_path / "elsewhere")
    assert display_path(bib) == "refs.bib"  # outside the working folder: the name only
    assert display_path("") == ""


def test_cli_names_files_relative_to_the_working_folder(tmp_path, monkeypatch, capsys):
    import json

    from reference_verifier.cli import main

    (tmp_path / "paper").mkdir()
    (tmp_path / "paper" / "refs.bib").write_text("@article{doe2020, title={A study of things}, author={Doe, Jane}, year={2020}}\n")
    (tmp_path / "paper" / "main.tex").write_text("See \\cite{doe2020}.\n\\bibliography{refs}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    main(["paper/main.tex", "--offline", "--json", "out.json"])
    out = capsys.readouterr().out
    assert "references from paper/refs.bib" in out
    for absolute in {str(tmp_path), str(tmp_path.resolve())}:
        assert absolute not in out
    data = json.loads((tmp_path / "out.json").read_text())
    assert data["inputs"] == ["paper/refs.bib"]
    assert [r["source_file"] for r in data["results"]] == ["paper/refs.bib"]
