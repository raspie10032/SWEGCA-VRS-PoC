# VRS Judgment PoC

Private manuscript and implementation checkpoint for **Does VRS Affect Judgment? A Proof-of-Concept Study of Evidence-Gated Memory in a SWEGCA Reference Implementation**.

Author: Dongjun Park. First-party code: MIT. This repository is separate from SWEGCA-Architecture and from the private development repository's Git history. It investigates whether judgment changes, not whether VRS must improve accuracy. It is a concept-validation research package, not a finished product.

## Contents

- [Manuscript source](paper/swegca_vrs_persistent_cognition/main.tex) and bibliography, including the restored GPT-5.6 Luna comparison.
- [Claim–evidence matrix](paper/swegca_vrs_persistent_cognition/CLAIM_EVIDENCE_MATRIX.md), reproduction notes and historical submission checklist.
- [Reference implementation](reference/README.md): actual memory/VRS decision components, Luna transport and offline tests, saved specialist comparisons, and historical Phase2/3/5 caller source.
- [Specialist comparison coverage](reference/SPECIALIST_REPRODUCTION.md): three-model C0/C1, C3/C4 and swap evidence, with exact reproduction limits.
- `UPSTREAM.json` and `reference/LINEAGE.json`: source revision, per-file hashes and derivation boundaries. Original source bytes are retained.
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

Existing Q evidence has one changed and two unchanged memory-branch decisions; a separate P8C task has 0/12 changes. Historical J/K 100-source datasets are secondary analogy/algorithm comparisons, not isolated VRS effects. Luna's retained three C3-to-C4 judgments change from abstention to refutation; this varies Re-evidence, not VRS alone. Comparisons across tasks are not pooled. Failed outputs, unchanged judgments and negative utility remain evidence.

The compact specialist snapshot contains 30 historical cells, not 30 independent sources or new observations. Private source media, full experience/VRS state, models, credentials, original private receipts and private Git history are not included. Their exclusion from distribution does not mean their evidence was discarded or that new acquisition is required.

**PDF build/layout verification and bibliography verification remain pending. No arXiv submission or public release has occurred as part of this upload.** The original eight manuscript files are byte-exact snapshots; their paths, manifests and checklists refer to upstream historical evidence, not a claim that every upstream runtime artifact is present here. Current package commands are the ones above.

## Rozephine의 판단

Only already recorded outputs and constructed software tests are represented. This upload produces no new empirical judgments or growth.

## Codex의 판단

Byte checks, offline execution and a verified private push establish this repository checkpoint only, not full empirical replay, PDF acceptance, peer review or paper completion.

## Codex 작업 실수 및 교정

Prior Codex work confused influence with correct influence and omitted Luna coverage from summaries/the initial narrow export. The corrected manuscript and implementation preserve those distinctions and original evidence. [Upload checkpoint](docs/UPLOAD_CHECKPOINT.md) records this upload's scope, checks and any additional errors.
