I want a Python program that generates BINGO cards from a YAML file that contains phrases to put on each square.  Output will be a PDF file, one BINGO card per 8.5"x11" page.

By default the program generates 5x5 cards with a free square in the middle.  The label for the free square defaults to "FREE", but can be user selected from the command line.

Text within BINGO card squares should be center-aligned along toward the top of the square - this leaves room in the middle and bottom of the BINGO square for players to freely write names or other information, depending on the nature of the game this BINGO card supports.

The command line options and default values are as follows:

```bash
bingo.py [--pages=10] [--size=5] [--free|--no-free] [--free-label=free] [--title="BINGO!"] [--page-size=8.5x11|A4] [--labels=]labels.yaml
```

The input list of labels (supplied in this example as the file named `labels.yaml` may be encoded in YAML as lists under a key. The key introduces the category of labels; this is for human organization only. the name of a label category should not appear on a BINGO card square.  Only members of lists within keys are eligible to go into a BINGO card square.

There is one special key, `options`, which should be treated specially.  Items under the `options` key can replace hard-coded configuration values as if these options were specified on the command line. Thus, a BINGO card YAML file can contain its own data as well as configuration metadata. These configuration data items can be overridden by the command line.

In order of precedence:

    command-line option > YAML file option > hard-coded option.

The output filename is equal to the input filename, except the .yaml extension is replaced with .pdf.  If a file by that name already exists, insert an index `.0`, `.1`, `.2`, etc. between the filename stem and the `.pdf` extension.
