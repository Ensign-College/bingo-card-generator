import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bingo  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def write_yaml(tmp_path, text, name="labels.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def many_labels(n):
    return "Things:\n" + "".join(f"  - label {i}\n" for i in range(n))


def page_count(pdf_path):
    return len(re.findall(rb"/Type\s*/Page\b", Path(pdf_path).read_bytes()))


# -- input ---------------------------------------------------------------

def test_categories_are_not_labels_and_options_are_split_out(tmp_path):
    p = write_yaml(tmp_path, "options:\n  size: 3\nA:\n  - x\n  - y\nB:\n  - z\n")
    labels, options = bingo.load_yaml(p)
    assert labels == ["x", "y", "z"]
    assert options == {"size": 3}


def test_duplicates_across_categories_are_dropped(tmp_path):
    p = write_yaml(tmp_path, "A:\n  - x\n  - y\nB:\n  - y\n  - '  x '\n  - z\n")
    labels, _ = bingo.load_yaml(p)
    assert labels == ["x", "y", "z"]


def test_option_names_accept_dashes(tmp_path):
    p = write_yaml(tmp_path, "options:\n  free-label: GIFT\n  page-size: A4\nA: [x]\n")
    _, options = bingo.load_yaml(p)
    assert options == {"free_label": "GIFT", "page_size": "A4"}


@pytest.mark.parametrize("text", ["- a\n- b\n", "A: scalar\n", "A:\n  - [x]\n", ""])
def test_malformed_yaml_structure_is_an_error(tmp_path, text):
    with pytest.raises(bingo.BingoError):
        bingo.load_yaml(write_yaml(tmp_path, text))


def test_bundled_example_file_loads():
    labels, options = bingo.load_yaml(REPO / "squares.yaml")
    assert len(labels) == 64 and "λ" in labels and options == {}


# -- configuration -------------------------------------------------------

def test_precedence_cli_over_yaml_over_defaults():
    cli = {"pages": 3, "size": None, "title": None}
    cfg = bingo.resolve_config(cli, {"pages": 7, "size": 4, "title": "Hi"})
    assert (cfg["pages"], cfg["size"], cfg["title"]) == (3, 4, "Hi")
    assert cfg["free_label"] == "FREE" and cfg["header"] is True


def test_cli_false_overrides_yaml_true():
    cfg = bingo.resolve_config({"header": False}, {"header": True})
    assert cfg["header"] is False


def test_size_is_capped_at_16():
    assert bingo.resolve_config({"size": 16}, {})["size"] == 16
    with pytest.raises(bingo.BingoError):
        bingo.resolve_config({"size": 17}, {})


def test_unknown_yaml_option_is_an_error():
    with pytest.raises(bingo.BingoError, match="bogus"):
        bingo.resolve_config({}, {"bogus": 1})


@pytest.mark.parametrize("opts", [{"pages": 0}, {"pages": "3"}, {"free": "yes"},
                                  {"page_size": "A3"}, {"size": True}])
def test_invalid_option_values_are_errors(opts):
    with pytest.raises(bingo.BingoError):
        bingo.resolve_config({}, opts)


def test_header_letters_are_distinct():
    assert len(set(bingo.HEADER_LETTERS)) == bingo.MAX_SIZE == 16


# -- cards ---------------------------------------------------------------

def test_card_has_free_square_in_middle_and_no_repeats():
    cfg = bingo.resolve_config({}, {})
    labels = [f"l{i}" for i in range(40)]
    grid = bingo.make_card(labels, cfg, random.Random(1))
    flat = [c for row in grid for c in row]
    assert grid[2][2] is None and flat.count(None) == 1
    real = [c for c in flat if c is not None]
    assert len(real) == 24 and len(set(real)) == 24


def test_even_size_has_no_free_square():
    cfg = bingo.resolve_config({"size": 4}, {})
    grid = bingo.make_card([f"l{i}" for i in range(16)], cfg, random.Random(1))
    assert None not in [c for row in grid for c in row]


def test_no_free_fills_every_square():
    cfg = bingo.resolve_config({"free": False}, {})
    grid = bingo.make_card([f"l{i}" for i in range(25)], cfg, random.Random(1))
    assert None not in [c for row in grid for c in row]


def test_seed_makes_cards_reproducible():
    cfg = bingo.resolve_config({}, {})
    labels = [f"l{i}" for i in range(40)]
    a = bingo.make_card(labels, cfg, random.Random(5))
    b = bingo.make_card(labels, cfg, random.Random(5))
    assert a == b


# -- output --------------------------------------------------------------

def test_output_name_is_indexed_when_file_exists(tmp_path):
    p = write_yaml(tmp_path, "A: [x]\n", name="game.yaml")
    assert bingo.write_unique(p, b"1").name == "game.pdf"
    assert bingo.write_unique(p, b"2").name == "game.0.pdf"
    assert bingo.write_unique(p, b"3").name == "game.1.pdf"
    assert (tmp_path / "game.pdf").read_bytes() == b"1"


def test_end_to_end_one_page_per_card(tmp_path, capsys):
    p = write_yaml(tmp_path, many_labels(30))
    assert bingo.main(["--pages=3", "--seed=1", str(p)]) == 0
    out = tmp_path / "labels.pdf"
    assert out.read_bytes().startswith(b"%PDF") and page_count(out) == 3


def test_end_to_end_options_from_yaml_and_labels_flag(tmp_path):
    p = write_yaml(tmp_path, "options:\n  pages: 2\n  size: 3\n  page-size: A4\n"
                   + many_labels(20))
    assert bingo.main([f"--labels={p}", "--no-header"]) == 0
    assert page_count(tmp_path / "labels.pdf") == 2


def test_too_few_labels_is_an_error(tmp_path, capsys):
    p = write_yaml(tmp_path, many_labels(10))
    assert bingo.main([str(p)]) == 1
    assert "needs 24" in capsys.readouterr().err
    assert not (tmp_path / "labels.pdf").exists()


def test_free_square_does_not_count_toward_needed_labels(tmp_path):
    p = write_yaml(tmp_path, many_labels(24))
    assert bingo.main(["--pages=1", str(p)]) == 0
    assert bingo.main(["--pages=1", "--no-free", str(p)]) == 1


def test_max_size_card_renders(tmp_path):
    p = write_yaml(tmp_path, many_labels(300))
    assert bingo.main(["--size=16", "--pages=1", "--page-size=A4", str(p)]) == 0


def test_missing_labels_argument_exits(tmp_path):
    with pytest.raises(SystemExit):
        bingo.main([])


def test_label_given_both_ways_exits(tmp_path):
    p = write_yaml(tmp_path, many_labels(30))
    with pytest.raises(SystemExit):
        bingo.main([str(p), f"--labels={p}"])
