#!/usr/bin/env python3
"""Generate BINGO cards, one per page, as a PDF from a YAML file of labels."""

import argparse
import random
import sys
from pathlib import Path

import yaml
from fpdf import FPDF

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FAMILY = "DejaVu"

# DejaVu has no light italic, so the footer uses ExtraLight slanted by the
# same angle DejaVu's own Oblique faces use.
FOOTER_FAMILY = "DejaVuLight"
FOOTER_PT = 8
FOOTER_SLANT_DEG = 11
FOOTER_GREY = 77  # 70% grey: 70% ink coverage, i.e. 30% of full white

# One distinct letter per column, so cards can be up to 16x16.
HEADER_LETTERS = "BINGOLARDYPEZMUX"
MIN_SIZE = 2
MAX_SIZE = len(HEADER_LETTERS)

PAGE_SIZES_MM = {
    "8.5x11": (215.9, 279.4),
    "a4": (210.0, 297.0),
}

# Lowest precedence: hard-coded defaults.
DEFAULTS = {
    "pages": 10,
    "size": 5,
    "free": True,
    "free_label": "FREE",
    "title": "BINGO!",
    "page_size": "8.5x11",
    "header": True,
    "seed": None,
}

PT_TO_MM = 25.4 / 72
LINE_SPACING = 1.2


class BingoError(Exception):
    """A problem the user can fix; reported without a traceback."""


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------

def normalize_option_name(name):
    return str(name).strip().lower().replace("-", "_")


def load_yaml(path):
    """Return (labels, options) from a labels YAML file.

    Every list under a key (other than `options`) contributes labels; the key
    itself is only for human organization. Duplicate labels are dropped,
    keeping first-seen order.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise BingoError(f"cannot read {path}: {e.strerror}") from e
    except yaml.YAMLError as e:
        raise BingoError(f"{path} is not valid YAML:\n{e}") from e

    if not isinstance(data, dict):
        raise BingoError(
            f"{path}: expected a mapping of category names to lists of labels"
        )

    options = {}
    labels = []
    seen = set()
    for key, value in data.items():
        if key == "options":
            if value is None:
                continue
            if not isinstance(value, dict):
                raise BingoError(f"{path}: 'options' must be a mapping")
            options = {normalize_option_name(k): v for k, v in value.items()}
            continue
        if value is None:
            continue
        if not isinstance(value, list):
            raise BingoError(f"{path}: '{key}' must be a list of labels")
        for item in value:
            if item is None:
                continue
            if isinstance(item, (dict, list)):
                raise BingoError(
                    f"{path}: '{key}' contains a nested item; labels must be "
                    "plain text"
                )
            label = " ".join(str(item).split())
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels, options


# --------------------------------------------------------------------------
# Configuration: command line > YAML `options` > hard-coded defaults
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="bingo.py",
        description="Generate BINGO cards (one per page) as a PDF from a "
        "YAML file of labels.",
        epilog="Options may also be set under an `options:` key in the YAML "
        "file; command-line values take precedence.",
    )
    p.add_argument("labels_file", nargs="?", metavar="labels.yaml",
                   help="YAML file of labels (or use --labels)")
    p.add_argument("--labels", dest="labels_opt", metavar="labels.yaml",
                   help="YAML file of labels")
    p.add_argument("--pages", type=int, metavar="N",
                   help=f"number of cards to generate (default {DEFAULTS['pages']})")
    p.add_argument("--size", type=int, metavar="N",
                   help=f"squares per side, {MIN_SIZE}-{MAX_SIZE} "
                   f"(default {DEFAULTS['size']})")
    p.add_argument("--free", action=argparse.BooleanOptionalAction, default=None,
                   help="put a free square in the middle of odd-sized cards "
                   "(default: on)")
    p.add_argument("--free-label", metavar="TEXT",
                   help=f"label for the free square (default {DEFAULTS['free_label']})")
    p.add_argument("--title", metavar="TEXT",
                   help=f"title above the grid (default {DEFAULTS['title']!r}; "
                   "'' for none)")
    p.add_argument("--page-size", metavar="SIZE",
                   help="8.5x11 or A4 (default 8.5x11)")
    p.add_argument("--header", action=argparse.BooleanOptionalAction, default=None,
                   help=f"show the {HEADER_LETTERS[:5]}... letter row above the "
                   "grid (default: on)")
    p.add_argument("--seed", type=int, metavar="N",
                   help="random seed, for reproducible cards")
    return p


def resolve_config(cli, yaml_options):
    """Merge the three option sources and validate the result."""
    unknown = sorted(set(yaml_options) - set(DEFAULTS))
    if unknown:
        raise BingoError(
            "unknown option(s) in YAML 'options': " + ", ".join(unknown)
        )
    cfg = dict(DEFAULTS)
    cfg.update(yaml_options)
    cfg.update({k: v for k, v in cli.items() if v is not None})
    return validate_config(cfg)


def validate_config(cfg):
    def need_int(name, lo, hi=None):
        v = cfg[name]
        if isinstance(v, bool) or not isinstance(v, int):
            raise BingoError(f"{name} must be an integer, got {v!r}")
        if v < lo or (hi is not None and v > hi):
            rng = f"between {lo} and {hi}" if hi is not None else f"at least {lo}"
            raise BingoError(f"{name} must be {rng}, got {v}")

    def need_bool(name):
        if not isinstance(cfg[name], bool):
            raise BingoError(f"{name} must be true or false, got {cfg[name]!r}")

    need_int("pages", 1)
    need_int("size", MIN_SIZE, MAX_SIZE)
    need_bool("free")
    need_bool("header")
    if cfg["seed"] is not None:
        need_int("seed", -(2**63), 2**63)

    for name in ("free_label", "title"):
        if cfg[name] is None:
            cfg[name] = ""
        cfg[name] = str(cfg[name])

    key = str(cfg["page_size"]).lower().replace(" ", "")
    key = "8.5x11" if key in ("letter", "8.5x11") else key
    if key not in PAGE_SIZES_MM:
        raise BingoError(
            f"page_size must be 8.5x11 or A4, got {cfg['page_size']!r}"
        )
    cfg["page_size"] = key
    return cfg


# --------------------------------------------------------------------------
# Card generation
# --------------------------------------------------------------------------

def has_free_square(cfg):
    return cfg["free"] and cfg["size"] % 2 == 1


def make_card(labels, cfg, rng):
    """Return a size x size grid (list of rows); free square is None."""
    size = cfg["size"]
    free = has_free_square(cfg)
    picks = rng.sample(labels, size * size - (1 if free else 0))
    cells = iter(picks)
    mid = size // 2
    return [
        [None if free and r == mid and c == mid else next(cells)
         for c in range(size)]
        for r in range(size)
    ]


# --------------------------------------------------------------------------
# PDF rendering
# --------------------------------------------------------------------------

class CardRenderer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.size = cfg["size"]
        self.page_w, self.page_h = PAGE_SIZES_MM[cfg["page_size"]]
        self.margin = 15.0
        self.warnings = set()
        self._fit_cache = {}

        pdf = FPDF(unit="mm", format=(self.page_w, self.page_h))
        pdf.set_auto_page_break(False)
        pdf.add_font(FONT_FAMILY, "", str(FONT_DIR / "DejaVuSans.ttf"))
        pdf.add_font(FONT_FAMILY, "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        pdf.add_font(FOOTER_FAMILY, "", str(FONT_DIR / "DejaVuSans-ExtraLight.ttf"))
        pdf.set_title(cfg["title"] or "BINGO")
        pdf.set_creator("bingo.py")
        self.pdf = pdf
        self._compute_layout()

    # -- layout ----------------------------------------------------------

    def _compute_layout(self):
        usable_w = self.page_w - 2 * self.margin
        usable_h = self.page_h - 2 * self.margin
        self.title_h = 20.0 if self.cfg["title"] else 0.0
        self.cell = min(usable_w / self.size,
                        (usable_h - self.title_h - 14.0) / self.size)
        self.header_h = min(12.0, self.cell * 0.6) if self.cfg["header"] else 0.0
        self.grid_w = self.cell * self.size
        block_h = self.title_h + self.header_h + self.grid_w
        # Center the title+header+grid block vertically on the page.
        self.top = self.margin + (usable_h - block_h) / 2
        self.left = (self.page_w - self.grid_w) / 2
        self.pad = max(1.0, self.cell * 0.06)
        self.max_label_pt = min(18.0, self.cell / PT_TO_MM * 0.4)
        self.min_label_pt = 4.0
        self.max_text_h = self.cell * 0.5

    # -- text fitting ----------------------------------------------------

    def _width(self, text, style, pt):
        self.pdf.set_font(FONT_FAMILY, style, pt)
        return self.pdf.get_string_width(text)

    def _wrap(self, text, style, pt, max_w, hard):
        """Greedy word wrap. With hard=True, over-long words are split."""
        lines, cur = [], ""
        for word in text.split():
            cand = f"{cur} {word}" if cur else word
            if self._width(cand, style, pt) <= max_w:
                cur = cand
                continue
            if cur:
                lines.append(cur)
                cur = ""
            if hard and self._width(word, style, pt) > max_w:
                chunk = ""
                for ch in word:
                    if chunk and self._width(chunk + ch, style, pt) > max_w:
                        lines.append(chunk)
                        chunk = ""
                    chunk += ch
                cur = chunk
            else:
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def fit(self, text, style="", max_pt=None, max_w=None, max_h=None):
        """Return (font_pt, lines) for the largest size that fits the box."""
        max_pt = max_pt or self.max_label_pt
        max_w = max_w or self.cell - 2 * self.pad
        max_h = max_h or self.max_text_h
        key = (text, style, max_pt, max_w, max_h)
        if key in self._fit_cache:
            return self._fit_cache[key]

        result = None
        pt = max_pt
        while pt >= self.min_label_pt:
            lines = self._wrap(text, style, pt, max_w, hard=False)
            lh = pt * PT_TO_MM * LINE_SPACING
            if (lines and len(lines) * lh <= max_h
                    and all(self._width(ln, style, pt) <= max_w for ln in lines)):
                result = (pt, lines)
                break
            pt -= 0.5
        if result is None:
            pt = self.min_label_pt
            lines = self._wrap(text, style, pt, max_w, hard=True)
            if len(lines) * pt * PT_TO_MM * LINE_SPACING > max_h:
                self.warnings.add(text)
            result = (pt, lines)
        self._fit_cache[key] = result
        return result

    # -- drawing ---------------------------------------------------------

    def add_card(self, grid, number, total):
        pdf = self.pdf
        pdf.add_page()
        pdf.set_draw_color(0)
        pdf.set_text_color(0)
        pdf.set_line_width(0.35)

        if self.cfg["title"]:
            pt, lines = self.fit(
                self.cfg["title"], "B", max_pt=32,
                max_w=self.page_w - 2 * self.margin, max_h=self.title_h - 4)
            pdf.set_font(FONT_FAMILY, "B", pt)
            lh = pt * PT_TO_MM * LINE_SPACING
            pdf.set_xy(self.margin, self.top)
            pdf.multi_cell(self.page_w - 2 * self.margin, lh, "\n".join(lines),
                           align="C")

        y = self.top + self.title_h
        if self.cfg["header"]:
            self._draw_header(y)
            y += self.header_h
        for r, row in enumerate(grid):
            for c, label in enumerate(row):
                self._draw_square(self.left + c * self.cell,
                                  y + r * self.cell, label)
        self._draw_footer(*footer_texts(number, total, self.cfg["seed"]))

    def _draw_footer(self, left_text, right_text):
        pdf = self.pdf
        baseline = self.page_h - 10.0
        pdf.set_font(FOOTER_FAMILY, "", FOOTER_PT)
        pdf.set_text_color(FOOTER_GREY)
        right_x = self.left + self.grid_w - pdf.get_string_width(right_text)
        for x, text in ((self.left, left_text), (right_x, right_text)):
            with pdf.skew(ax=FOOTER_SLANT_DEG, x=x, y=baseline):
                pdf.text(x, baseline, text)
        pdf.set_text_color(0)

    def _draw_header(self, y):
        pdf = self.pdf
        pt = min(self.header_h / PT_TO_MM * 0.6, self.cell / PT_TO_MM * 0.6)
        pdf.set_fill_color(225)
        pdf.set_font(FONT_FAMILY, "B", pt)
        for c in range(self.size):
            x = self.left + c * self.cell
            pdf.rect(x, y, self.cell, self.header_h, style="DF")
            pdf.set_xy(x, y)
            pdf.cell(self.cell, self.header_h, HEADER_LETTERS[c], align="C")

    def _draw_square(self, x, y, label):
        pdf = self.pdf
        is_free = label is None
        if is_free:
            pdf.set_fill_color(235)
            pdf.rect(x, y, self.cell, self.cell, style="DF")
            label = self.cfg["free_label"]
        else:
            pdf.rect(x, y, self.cell, self.cell, style="D")
        if not label:
            return
        style = "B" if is_free else ""
        pt, lines = self.fit(label, style)
        pdf.set_font(FONT_FAMILY, style, pt)
        lh = pt * PT_TO_MM * LINE_SPACING
        # Text hugs the top, leaving the rest of the square for writing.
        for i, line in enumerate(lines):
            pdf.set_xy(x, y + self.pad + i * lh)
            pdf.cell(self.cell, lh, line, align="C")

    def render(self):
        return bytes(self.pdf.output())


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_unique(labels_path, data):
    """Write data next to the input as NAME.pdf, or NAME.0.pdf, NAME.1.pdf...

    Opened exclusively, so an existing file is never overwritten.
    """
    labels_path = Path(labels_path)
    stem = labels_path.stem
    candidates = [labels_path.with_name(f"{stem}.pdf")]
    candidates.extend(
        labels_path.with_name(f"{stem}.{i}.pdf") for i in range(10_000)
    )
    for path in candidates:
        try:
            with open(path, "xb") as f:
                f.write(data)
            return path
        except FileExistsError:
            continue
    raise BingoError(f"could not find an unused output name for {stem}.pdf")


def footer_texts(number, total, seed):
    return f"Card {number} of {total}", f"Seed: {seed}"


def resolve_seed(cfg):
    """Return cfg with a concrete seed, so the footer can always show it."""
    if cfg["seed"] is not None:
        return cfg
    return {**cfg, "seed": random.SystemRandom().getrandbits(32)}


def generate(labels_path, cfg, labels):
    cfg = resolve_seed(cfg)
    free = has_free_square(cfg)
    needed = cfg["size"] ** 2 - (1 if free else 0)
    if len(labels) < needed:
        raise BingoError(
            f"a {cfg['size']}x{cfg['size']} card needs {needed} distinct "
            f"labels but {labels_path} provides only {len(labels)}"
        )
    rng = random.Random(cfg["seed"])
    renderer = CardRenderer(cfg)
    for n in range(1, cfg["pages"] + 1):
        renderer.add_card(make_card(labels, cfg, rng), n, cfg["pages"])
    for text in sorted(renderer.warnings):
        print(f"bingo.py: warning: label does not fit its square: {text!r}",
              file=sys.stderr)
    return write_unique(labels_path, renderer.render())


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.labels_file and args.labels_opt:
        parser.error("give the labels file once: positional or --labels")
    labels_path = args.labels_file or args.labels_opt
    if not labels_path:
        parser.error("a labels YAML file is required")

    cli = {k: v for k, v in vars(args).items()
           if k not in ("labels_file", "labels_opt")}
    try:
        labels, yaml_options = load_yaml(labels_path)
        cfg = resolve_config(cli, yaml_options)
        out = generate(labels_path, cfg, labels)
    except BingoError as e:
        print(f"bingo.py: error: {e}", file=sys.stderr)
        return 1
    print(f"Created {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
