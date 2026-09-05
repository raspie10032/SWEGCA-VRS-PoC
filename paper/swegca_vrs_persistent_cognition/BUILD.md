# Build and validation

## Current build status

At the Phase 8 freeze, the assembly host had no `latexmk`, `pdflatex`, `bibtex`, `tectonic`, `pandoc`, `lualatex`, or `xelatex` executable. Installing a TeX distribution was outside the authorized scope. Therefore:

- source-level validation is required and was run locally;
- no successful PDF build is claimed;
- absence of a local PDF is not treated as a manuscript-source failure; and
- PDF layout validation remains an author action in an existing TeX environment.

## Validate the source package

For the current PoC revision (existing data only; no media/model execution):

```bash
PYTHONPATH=src:. python tools/validate_rozephine_vrs_poc_revision.py
```

This adds claim-boundary and raw-receipt checks to the historical source/privacy/tree checks. It verifies 1 changed/2 unchanged Q decisions, 0/12 P8C changes, the Phase7 non-authoritative-hypothesis boundary and Phase9 negative utility numbers. A source PASS is not a PDF, empirical rerun, peer-review or finished-paper PASS.

The command below belongs to the original Phase8 workflow; use a fresh output path when reproducing it rather than overwriting historical reports. It does not by itself validate the new scientific interpretation.

From the repository root:

```bash
.runtime-rozephine-python314-torch214-cu132-20260903/venv/bin/python \
  tools/validate_rozephine_swegca_vrs_paper_phase8.py \
  --config configs/rozephine_swegca_vrs_paper_phase8_manuscript_freeze_v1.json \
  --output .runtime-rozephine-swegca-vrs-paper-phase8-validation-20260905-run001/report.json
```

The output path is a regenerable local runtime artifact and is not included in the public package.

## Build in an existing TeX environment

Copy or check out the repository without adding private runtime artifacts, then run:

```bash
cd paper/swegca_vrs_persistent_cognition
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

If `latexmk` is unavailable but `pdflatex` and `bibtex` are already installed:

```bash
cd paper/swegca_vrs_persistent_cognition
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Do not report a PDF pass unless the command exits successfully and the resulting pages have been visually inspected.

## Expected source inputs

The PDF build needs only `main.tex` and `references.bib`. The remaining Markdown and JSON files form the evidence and submission companion package; they are not included by TeX.

## Clean generated TeX files

Generated TeX auxiliaries and PDF output are reproducible build products. Remove them only in a dedicated copy or with explicit exact filenames; do not use a broad recursive cleanup command in the research checkout.
