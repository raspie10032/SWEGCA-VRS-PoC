# Evidence-Gated Experience and Verified Reinforcement Synapses

Private manuscript and implementation checkpoint for **Evidence-Gated Experience and Verified Reinforcement Synapses across Context Resets and Replaceable Reasoning Models**.

Author: Dongjun Park. First-party code: MIT. This repository is separate from SWEGCA-Architecture and from the private development repository's Git history. Within an architecture that preserves main-owned experience outside specialist context and across model replacement, it investigates whether VRS changes judgment, not whether VRS must improve accuracy. It is a concept-validation research package, not a finished product. The repository identifier is `SWEGCA-VRS-PoC`, not a new definition of VRS.

Current private repository: [raspie10032/SWEGCA-VRS-PoC](https://github.com/raspie10032/SWEGCA-VRS-PoC). It was renamed from `VRS-Judgment-PoC` with the same repository identity. The earlier name and then-local status in historical notes describe those checkpoints; see [the rename and synchronization record](docs/REPOSITORY_RENAME_20260906.md) for the subsequent operation.

## Contents

- [Manuscript source](paper/swegca_vrs_persistent_cognition/main.tex) and bibliography, including the restored GPT-5.6 Luna comparison.
- [Claim–evidence matrix](paper/swegca_vrs_persistent_cognition/CLAIM_EVIDENCE_MATRIX.md), reproduction notes and historical submission checklist.
- [Reference implementation](reference/README.md): actual memory/VRS decision components, Luna transport and offline tests, saved specialist comparisons, and historical Phase2/3/5 caller source.
- [Specialist comparison coverage](reference/SPECIALIST_REPRODUCTION.md): three-model C0/C1, C3/C4 and swap evidence, with exact reproduction limits.
- `UPSTREAM.json` and `reference/LINEAGE.json`: source revision, current per-file hashes and derivation boundaries. The initial imported paper remains in Git history; the current paper includes the documented editorial revision. Reference implementation bytes are unchanged.
- `docs/reference-source.tar`: exact component export archive.

## Run without the original checkout

Python 3.11+ is specified; the verified environment is Python 3.14.7 with pytest 9.1.1. No model, GPU, live resident service or network is needed for the offline checks (installing pytest separately may need network).

```sh
python verify_repository.py
cd reference
python -m pip install -r requirements-test.txt  # omit if pytest is already installed
python -m pytest -q
python analyze_specialist_comparisons.py
```

The component suite explicitly deselects one full-resident integration test; that exclusion is not an integration PASS. Luna transport tests inject mock process outputs and never call the provider. Historical full experiment runners are included as actual source but require the authorized original resident/model environment. They are not standalone inference runners in this repository.

## Evidence and current limits

Context reset retained 3/3 provenance-bound E2B refutations. All six specialist-replacement calls on the same three requests retained the recorded main-state pair and ended in refutation or abstention; exact verdict retention was 3/6, all from Luna. Five historical episodes remained retrievable from a later full-current snapshot. These observations concern the tested configurations, not general cognitive continuity, exhaustive safety, equal model competence or context-length performance. They do not isolate VRS influence.

Existing Q evidence has one changed and two unchanged memory-branch decisions; a separate P8C task has 0/12 changes. Historical J/K 100-source datasets are secondary analogy/algorithm comparisons, not isolated VRS effects. Luna's retained three C3-to-C4 judgments change from abstention to refutation; this varies Re-evidence, not VRS alone. Comparisons across tasks are not pooled. Failed outputs, unchanged judgments and negative utility remain evidence.

The compact specialist snapshot contains 30 historical cells, not 30 independent sources or new observations. Private source media, full experience/VRS state, models, credentials, original private receipts and private Git history are not included. Their exclusion from distribution does not mean their evidence was discarded or that new acquisition is required.

**PDF build/layout and full bibliography verification remain pending. No arXiv submission or public release has occurred as part of this local revision.** The initial eight manuscript files were byte-exact imports. [The title-alignment note](docs/TITLE_ALIGNMENT_20260906.md) preserves the earlier correction; [the overclaim review](docs/OVERCLAIM_REVIEW_20260906.md) records the subsequent user-approved shorter title and claim audit. `UPSTREAM.json` tracks current hashes and prior lineage. Historical evidence paths and checklists do not imply that every upstream runtime artifact is present here. Current package commands are the ones above.

## Rozephine의 판단

Only already recorded outputs and constructed software tests are represented. This upload produces no new empirical judgments or growth.

## Codex의 판단

The historical private push established the imported checkpoint. The title/overclaim corrections and repository rename are tracked in [the synchronization record](docs/REPOSITORY_RENAME_20260906.md). Byte checks and offline execution do not establish full empirical replay, PDF acceptance, peer review or paper completion.

## Codex 작업 실수 및 교정

Prior Codex work confused influence with correct influence, omitted Luna coverage from summaries/the initial narrow export, and replaced the original title with an assistant-created question title. Restoring the original title then retained an overly broad headline despite small-sample caveats. The current correction uses the original subtitle as the title and separates measured outcomes from architectural requirements without reverting evaluation corrections. Historical decisions remain in [the upload checkpoint](docs/UPLOAD_CHECKPOINT.md) and [title-alignment note](docs/TITLE_ALIGNMENT_20260906.md); [the overclaim review](docs/OVERCLAIM_REVIEW_20260906.md) records this correction and its limits.
