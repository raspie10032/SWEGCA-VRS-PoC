# arXiv correction and repository synchronization

The user requested that this separate manuscript repository match the corrected arXiv submission. Baseline: `1cd67ec6fb139e147e94432f66da3852c53fca3d`.

## Submitted state

On 2026-09-06 at 12:43 KST, the arXiv account confirmed **Article submitted** for existing submission **8040733** after correction. Status was **on hold**. This is a submission identifier, not a public arXiv identifier or acceptance; the specific hold reason is not established.

Title: Evidence-Gated Experience and Verified Reinforcement Synapses across Context Resets and Replaceable Reasoning Models. Author: Dongjun Park, Independent Researcher. Primary category: cs.AI; no secondary category. License selected for arXiv: CC BY 4.0. Comments: 15 pages, 1 figure, 6 tables. Repository visibility remains private; first-party code retains its existing MIT license.

## Corrections synchronized

- Removed editorial/request wording and obsolete pre-submission TeX/PDF notes.
- Expanded SWEGCA and defined historical cohort labels; removed undefined P3 wording.
- Clarified that implementation and supporting research materials are not publicly released with this article.
- Added visible existing source URLs to all 14 bibliography entries.
- Included the previously verified Table 4 wrapping fix in the repository source.
- Recorded actual submitted web metadata, build status and submission status in companion documents.

No research numbers or equations were changed. No experiment, model call or VRS execution was performed for this synchronization. Reference implementation and retained evidence bytes remain unchanged.

## Verified artifacts

Files are under `paper/swegca_vrs_persistent_cognition/`:

| File | SHA-256 |
| --- | --- |
| main.tex | 6e5b573917726a6bfba209ab111f7ba38f8864593cc9da107b74b2250f8068bc |
| references.bib | af4640f3ae4f44041bf9b5032a86a4614219de7fb912c4dd70707674cf4c1e20 |
| arxiv-corrected.pdf | 6fb302449f5e67381abaaf0c42cd5a7c16363b7a427e528737ee4cb0c91a472b |

The arXiv server source was downloaded and compared byte for byte. It contained only main.tex, references.bib and arXiv's 00README.json. The PDF compiled successfully using pdflatex with TeX Live 2025. All 15 pages were rendered and visually reviewed, and all 14 unique reference URLs were verified present. No embedded files or unresolved double-question-mark references were found. Optional HTML preview returned Unauthorized; only the PDF preview was verified.

`UPSTREAM.json` records current file hashes and preserves the prior editorial revision and imported hashes. The artifact manifest retains historical evidence hashes and explicitly separates historical authority/run metadata from current submission status. Byte/component verification does not establish independent empirical replay or peer review.

## Repository validation

`python verify_repository.py` passed (14 snapshot files; 24 reference package files). Saved specialist comparison analysis completed without model calls. The unchanged component test suite passed: 65 passed, 1 deselected. The full-resident integration test remains explicitly deselected by the existing project configuration.

This check used an isolated environment with pytest 8.4.2 because the available package index did not provide the historical pytest 9.1.1 pin. The repository's test requirements and reference implementation were preserved. Exact-file comparison includes the submitted TeX/BibTeX trailing blank lines; these account for the two `git diff --check` blank-at-EOF notices. All other whitespace checks passed.
