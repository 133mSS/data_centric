# Report review and update notes

The uploaded report is `Bao_cao_Bao_mat_du_lieu_Nhom_11_FULL(1).pdf`. It is a 31-page PDF; no editable source DOCX was supplied. It was rendered and visually reviewed, but it has not been designated `report_final` because the project's database-backed and Ollama-backed tests could not be executed after the code changes.

## Report content checks

- The core reported values in the saved 40-case answer-leakage artifacts are internally consistent: baseline exact-substring leakage 18/40 (45%), controlled 0/40; denied-target retrieval 10/10 for baseline and 0/10 for controlled; allowed target hits 20/30 for baseline and 28/30 for controlled. These are figures from saved October 26 artifacts, not a new execution of the modified code.
- The saved prompt-injection chart refers to run `20261018T072609Z`; it should keep that run ID in the caption and not be represented as a fresh run.
- The report's limitation statements about exact matching, paraphrase/obfuscation, synthetic data, finite test coverage, leadership override, audit `query_text`, and out-of-scope at-rest encryption/key management should be preserved.
- The `benchmark_v1` scale-based benchmark is now documented and has code-level fixes, but it has not been executed in the available environment. Do not add benchmark v1 performance numbers or claim successful live embedding runs until local PostgreSQL/Ollama execution produces new artifacts.
- After the local checks pass, reconcile the report's environment, implementation, metric captions, result paths, and figures against new result artifacts. Regenerate the final PDF from the editable document using one consistent paper size; in the provided PDF, pages 1–30 are A4 but page 31 is Letter.

## Recommended order

1. Complete the local steps in `TEST_RESULTS.md` and run benchmark v1 in its isolated database.
2. Save the run ID, exact command/configuration, stdout/stderr, and new CSV/JSON outputs; recompute metrics from those outputs.
3. Update the report from its editable source (request the original DOCX if one exists), regenerate figures using the source artifacts, and verify all citations, page references, headings, table of contents, and paper size.
4. Export and render the PDF; inspect the full page contact sheet and a few dense pages before declaring a final report.

This note intentionally does not claim a final report was produced or that unavailable integration tests passed.
