# Reproducibility contract

This package supports two different levels of reproduction. Source-level verification is possible from the repository alone. Empirical re-execution additionally requires lawful access to the source media and model runtimes used by the experiment; those private or licensed inputs are not redistributed.

## Current availability and standalone checks

As of the 2026-09-06 arXiv resubmission, this repository remains private. The submitted arXiv source contains only `main.tex`, `references.bib` and arXiv's build configuration; it does not include the implementation, matrix, manifest or private evidence. This limits independent reproduction. The checked PDF is retained as `arxiv-corrected.pdf`.

In this standalone repository, use `python verify_repository.py`, `python -m pytest -q` from `reference/`, and `python reference/analyze_specialist_comparisons.py` from the repository root. The research-checkout commands retained below refer to upstream tools/configurations and are not directly runnable here. See [the submission record](../../docs/ARXIV_SYNC_20260906.md).

## Publication-safe companion package (not uploaded to arXiv)

The publication-safe set is:

- `main.tex`
- `references.bib`
- `CLAIM_EVIDENCE_MATRIX.md`
- `REPRODUCIBILITY.md`
- `ARTIFACT_MANIFEST_PUBLIC.json`
- `ARXIV_METADATA.md`
- `SUBMISSION_CHECKLIST.md`
- `BUILD.md`

`SOURCE_PLAN.md` and `SOURCE_PLAN_METADATA.json` are local planning inputs and are deliberately not part of the public package. Runtime directories, raw media, selection manifests, per-role receipts, private source identifiers, and account/service metadata are also excluded.

## Source-level verification

For this revised PoC draft run `PYTHONPATH=src:. python tools/validate_rozephine_vrs_poc_revision.py` in the repository's configured Python environment. It retains the historical checks below and additionally binds existing Q/P8C/J/K receipts and the 100 J activation hashes through `configs/rozephine_vrs_poc_manuscript_revision_v1.json`. Those private raw receipts are needed for the full local audit; this is not a claim that the eight-file manuscript-only package reproduces the experiment without its authorized inputs. Reference-code packaging and empirical reproduction are distinct from manuscript validation.

From the original research repository root, run:

```bash
.runtime-rozephine-python314-torch214-cu132-20260903/venv/bin/python \
  tools/validate_rozephine_swegca_vrs_paper_phase8.py \
  --config configs/rozephine_swegca_vrs_paper_phase8_manuscript_freeze_v1.json \
  --output .runtime-rozephine-swegca-vrs-paper-phase8-validation-20260905-run001/report.json
```

The validator checks:

1. every frozen parent-report, source-plan, and sanitized Phase-7 result hash;
2. the two protected historical paper Git trees;
3. required publication files, UTF-8 decoding, and absence of a byte-order mark;
4. required manuscript sections and all TeX-to-BibTeX citation keys;
5. Phase-7 v1 invalidation and repair disclosure;
6. the frozen v2 aggregate numbers and explicit non-claim boundaries; and
7. prohibited private strings in the eight public artifacts.

The resulting validation report is a local runtime artifact, not part of the publication package. Original Phase8 config/report/manifest history remains in Git; the current manifest records a separately identified PoC revision and does not retroactively alter Phase8 results.

## Empirical re-execution boundary

Full empirical re-execution requires the exact code revision, model identities, hardware/runtime capacity, and user-supplied lawful source paths described by the private phase reports. Reproduction must preserve all of the following:

- development, invalid-run, repair, and final-confirmation source sets remain disjoint as frozen;
- all 100 prefix judgments are durably sealed before the first later interval is accessed;
- the outcome rule and threshold are not changed after reveal;
- the memory arm uses the full current accumulated-experience snapshot, while the no-memory arm remains a bounded diagnostic;
- failed, uncertain, conflicting, negative, and pending experience remains available to VRS convergence;
- specialists receive detached read-only state and return proposals only;
- no memory record or worker output grants semantic, action, write, model-update, distribution, or distribution authority by itself; and
- the resident main-owned state is unchanged by the final confirmation.

No command in this public package embeds a source path, username, token, cookie, account identifier, private URL, or hidden answer. Re-execution operators must provide authorized inputs through their own environment and must not publish non-redistributable media or private receipts.

## Retained GPT-5.6 Luna comparison

Use `python reference/analyze_specialist_comparisons.py` from this repository root, or `python analyze_specialist_comparisons.py` from `reference/`. This reads 30 minimized saved S/M/L cells only. C3/C4 produces 0/3 changes for 135.5M, 3/3 for E2B and 3/3 for Luna; parse failures and abstentions remain explicit. C0/C1 and post-swap outputs are retained separately. These are development diagnostics, not new outcomes or VRS-only effects.

The actual Luna transport and its mock tests now accompany original Phase2/3/5 caller source. `SPECIALIST_REPRODUCTION.md` in the package distinguishes independently executable transport/component tests and saved-data analysis from historical runners requiring the original resident/model environment. Source inclusion is not a claim of full portable empirical replay. The original 15-cell matrix is not declared complete, K is not a Luna replacement, and unestablished comparisons do not automatically trigger new acquisition.

## Interpreting the evidence

Re-evaluate the retained J/K/L/M/N/O/P/Q and P8C outputs with `PYTHONPATH=src:. python tools/reevaluate_rozephine_saved_paper_results.py`. This offline command uses small saved JSON/JSONL receipts and records their hashes; it does not read media, invoke models, rebuild VRS or replace historical gates. The derived checkpoint is `docs/worklogs/rozephine_existing_results_reevaluation_20260905.json`. Old FAIL labels do not exclude input rows. Changed/unchanged pairs are counted independently of outcome correctness, which remains secondary. Existing records, including completed observations from an interrupted run, are reused with their precise lineage and measurement scope rather than replaced by new collection.

Current PoC revision: primary influence evidence is Phase23's 1 changed and 2 unchanged memory-branch decisions. P8C contributes 0/12 A/B choice changes in a different task and is not pooled with Phase23. These counts are independent of correctness. The disabled-VRS branch mechanically prevents promotion; no shuffled/sham-controlled or general final-main effect is claimed. The original correctness-dependent gates remain historical, and the corrected influence interpretation is post-hoc.

The Phase7 100-source result contains source-specific analogy hypotheses, not isolated VRS effects. All 100 Re-evidence receipts requested abstention; 91 outputs were explicitly non-authoritative hypotheses. Phase9 reused the non-VRS judgment helper and produced a negative utility comparison. Neither dataset supplies 100 isolated VRS interventions. Phase7 performed zero assimilations and zero VRS reconvergences, so it is not a growth run. The invalid initial 100-source run remains in the lineage; its sources were excluded from the later evaluation.

The five Phase-6 historical outcomes were all uncertain. They demonstrate retention of outcome labels and source-diverse lineage more strongly than calibrated reward learning. Exact verdict retention after specialist replacement was 3/6 even though safe state preservation was 6/6. These limitations must remain visible in reproductions and derivative reports.
