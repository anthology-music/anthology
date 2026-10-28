# Tasks

## 1. Data model

- [x] 1.1 Add `JobItem.outcome : ItemOutcome [0..1]` with enum `ItemOutcome` (`NEW`, `REPLACED`, `ALREADY_PRESENT`, `NOT_BETTER_THAN_EXISTING`, `NEEDS_REVIEW`, `FAILED`) to `docs/architecture/data-model.puml`; verify the diagram renders without errors on the PlantUML server

## 2. CD import

- [ ] 2.1 Compare each CD track with the existing original's effective quality against genuine CD quality and mark it new, skip or replace; verify with tests for a genuine CD-quality FLAC (skip), an upscaled FLAC (replace) and a missing track (new)

## 3. Sources

- [x] 3.1 Before download, compare the source's declared quality with the existing original's effective quality and skip unless the offer is better; verify with tests for both scenarios of the spec
- [x] 3.2 After download, apply the analysis result: replace on high-confidence improvement, discard with "not better than existing" on high-confidence non-improvement, otherwise keep the file and create a review entry with "needs review"; verify with tests for all three outcomes and that discarded files are removed from `imports`

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
