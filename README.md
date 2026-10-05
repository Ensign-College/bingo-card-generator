# BINGO card generator

Generates BINGO cards from a YAML file of labels. Output is a PDF with one card per page. The label text sits at the top of each square, leaving room below for players to write.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
bingo.py [--pages=10] [--size=5] [--free|--no-free] [--free-label=FREE] \
         [--title="BINGO!"] [--page-size=8.5x11|A4] [--header|--no-header] \
         [--seed=N] [--labels=]labels.yaml
```

| Option | Default | Notes |
|---|---|---|
| `--pages` | 10 | Number of cards to generate.
| `--size` | 5 | Squares per side; valid sizes range from 2 to 16.
| `--free` / `--no-free` | free | The free square is only used on odd sizes (there is no center square on even ones). |
| `--free-label` | `FREE` | Text of the free square. |
| `--title` | `BINGO!` | Printed above the grid; `""` for none. |
| `--page-size` | `8.5x11` | `8.5x11` or `A4`. |
| `--header` / `--no-header` | header | Column letters above the grid: the first *size* letters of `BINGOLARDYPEZMUX`. |
| `--seed` | random | Makes the cards reproducible. When omitted, a random seed is chosen and printed in each page footer, so any run can be reproduced. |

Each page has a footer in light, italic, 70% grey type: `Card N of M` on the
left and `Seed: S` on the right.

## Labels file

Each key introduces a category, and the lists under it supply labels. Category names are for human organization only and never appear on a card. Identical labels in different categories are merged, and a card never repeats a label.

```yaml
options:            # optional; same names as the command-line options
  size: 4
  free-label: GIFT
Languages:
  - Python
  - Rust
Tools:
  - Docker
```

Option precedence: command line options > YAML options > built-in defaults.

## Output

The PDF is written next to the input with `.yaml` replaced by `.pdf`. If that file exists, `.0`, `.1`, ... is inserted before `.pdf`. Existing files are never overwritten.

## Fonts

DejaVu Sans (regular, bold and extra-light) is bundled in `fonts/` so non-Latin characters such as `λ` render correctly. See `fonts/LICENSE-DejaVu`.

## Unit Tests

```bash
pip install pytest && pytest
```
