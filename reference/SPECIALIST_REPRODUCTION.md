# Retained S/M/L comparison and implementation coverage

The user-selected GPT-5.6 Luna control remains alongside fixed 135.5M and Gemma 4 E2B. K's majority/prior/current-evidence/classifier/retrieval baselines do not replace it.

## Offline reproduction

```sh
python verify_package.py
python analyze_specialist_comparisons.py
python -m pytest -q tests/test_mosaic_luna_persistent_conversation.py
```

The analyzer reads `specialist_comparisons.json`: 30 minimized historical cells, not 30 independent episodes (six Phase2 C0/C1, eighteen Phase3 C3/C4, six Phase5 swap). Three models share the same three Phase3 tasks. Four original receipt hashes bind provenance; tasks use opaque roles. Prompts, source text/addresses, worker IDs, account data and weights are excluded. Original receipts and invalid S/M attempts remain unchanged upstream. Phase2 uses original Luna and repaired S/M cells; Phase3 uses combined valid receipts, not the invalid whole-run PASS.

| Model | C0/C1 strict outputs | C3 -> C4 | Changes | Paired-cell parse failures |
|---|---:|---|---:|---:|
| 135.5M | 0/2 | insufficient -> insufficient | 0/3 | 6/6 |
| E2B | 0/2 | support -> refute | 3/3 | 0/6 |
| GPT-5.6 Luna | 2/2 | insufficient -> refute | 3/3 | 0/6 |

All three Luna Phase5 outputs are refute. The original report separately verifies same request/main pair and E2B verdict retention; this snapshot does not reconstruct pre-swap state. C3/C4 varies Re-evidence, not VRS on/off. No population effect, full 15-cell C0–C4 completion or 100-source Luna control is inferred. Unestablished C2 coverage is not proof of absent raw data or authority for recollection.

## Implementation included

- `src/tinylm_slicer/mosaic_luna_persistent_conversation.py`: actual transport logic, executed by existing tests with injected mock process output; no provider invocation or current availability claim.
- `tools/run_rozephine_swegca_vrs_paper_phase2_baseline.py`: byte-exact C0/C1 caller; original resident, configs and local-model adapters required.
- `tools/run_rozephine_swegca_vrs_paper_phase3_re_evidence.py`: byte-exact C3/C4 caller; PyTorch, cognitive kernel, arbitration, resident state and adapters required.
- `tools/run_rozephine_swegca_vrs_paper_phase5_specialist_swap.py`: byte-exact swap caller; Phase3 dependencies and sealed pre-swap state required.
- `tools/validate_rozephine_swegca_vrs_paper_phase1_receipt_contract.py`: original receipt validator, not a substitute for private state.

Historical runner source is provided for inspection and reproduction in the authorized upstream environment, **not as standalone runners in this archive**. Its imports/config arguments identify dependencies; `LINEAGE.json` fixes the upstream revision. Independently executable paths here are decision components, Luna transport mock tests and saved-result analysis. Full portable resident/model replay is not included. Do not run historical inference runners as part of this correction.

## Rozephine의 판단

Retained proposals/diagnostic verdicts, not fresh live judgments or new experience. Formatting failures remain failures.

## Codex의 판단

Luna's abstain-to-refute changes count independently of stale-support correction. Keep this comparison separate from Q/K and retain its implementation/reproduction limits.

## Codex 작업 실수 및 교정

Earlier Codex summaries omitted Luna diagnostics and the narrow export omitted their transport/runner source. This revision restores actual code and existing outputs without inventing experiments or claiming full independent empirical replay.
