# RISE Meeting

RISE Meeting adapts the [RISE](https://github.com/texttron/RISE) agentic search
framework to collections of meeting documents. It converts complete PDFs into a
document-level corpus, builds a BM25 index, and gives an LLM a bounded workspace
that it can explore with search, shell, and line-based reading tools.

The repository is intended as a reusable research pipeline. Collection-specific
metadata rules are isolated from extraction, indexing, retrieval, agent
execution, and evaluation.

## Current Capabilities

- Complete-document PDF extraction with Docling.
- Native-text parsing with OCR support for scanned pages.
- Resumable extraction with an atomic per-document checkpoint.
- Stable document IDs and collection-specific metadata adapters.
- Semantic document roles such as agenda items, official minutes, draft
  minutes, circulation papers, and table-of-contents documents.
- Generated meeting overview documents that connect records from the same
  meeting without duplicating their contents.
- Document-level BM25 indexing with `bm25s`.
- Bounded related-document expansion:
  - retrieving an agenda item may add its official minutes and meeting overview
  - retrieving official minutes may add the meeting overview
  - expansion is capped and does not add every document in the meeting
- RISE agent execution over a per-query workspace.
- Per-query trajectories, retrieved-document coverage, recall, answer
  generation, and optional LLM-as-judge evaluation.
- OpenAI-compatible HKUST Azure GenAI routing.

## Architecture

```text
source PDFs
  -> metadata adapter
  -> Docling extraction
  -> complete text documents
  -> corpus manifests + meeting overviews + Parquet
  -> BM25 index
  -> per-query bounded interaction workspace
  -> agent search / shell exploration / line reads
  -> answer + trajectory + retrieval and answer evaluation
```

RISE treats retrieval as the construction of an interaction space, rather than
as a fixed list of snippets inserted into a prompt. BM25 retrieves an initial
set of complete documents. Those documents are materialized into a query-local
workspace, where the agent can run focused searches and read relevant line
ranges before producing an answer.

Meeting-aware expansion is an optional layer on top of the upstream RISE search
tool. It uses manifests instead of hard-coded paths, so the core retrieval and
agent code remains reusable across collections.

## Repository Layout

```text
RISE_Meeting/
  src/rise/
    retrieval.py           # BM25 corpus loading, indexing, and retrieval
    tools.py               # Search, shell, and line-based read tools
    rise_agent.py          # RISE agent loop
    trajectory.py          # Per-query result and trajectory schema
    decompose.py           # Query decomposition and LLM client construction
    uac_metadata.py        # Reference filename metadata adapter
    uac_extract.py         # Docling extraction adapter
    uac_pipeline.py        # Resumable extraction checkpoint helpers
    uac_corpus.py          # Corpus, manifest, and meeting overview builder
    uac_workspace.py       # Bounded same-meeting document expansion

  scripts/
    build_uac_corpus.py    # Extract PDFs and build the meeting corpus
    build_bm25_index.py    # Build a BM25 index from corpus Parquet
    run_rise.py            # Run RISE over a JSONL query set
    judge.py               # Evaluate generated answers
    summarize_runs.py      # Summarize recall, coverage, accuracy, and cost

  tests/                   # Unit tests for adapters and meeting-aware behavior

  corpus/                  # Generated complete documents; ignored by Git
  runs/                    # Generated manifests, indexes, runs, and logs; ignored
  data/local/              # Local query sets or collection data; ignored
```

Runtime data is intentionally excluded from Git. Source PDFs, extracted text,
indexes, API credentials, query results, and private project documents must
remain local or be distributed through a separate controlled data store.

## Setup

### Windows with uv

```powershell
git clone https://github.com/TANGYirui/RISE_Meeting.git
cd RISE_Meeting

uv venv .venv --python 3.12
uv pip install -e ".[test,extract]"
```

Install the CUDA build of PyTorch appropriate for the local GPU before running a
large OCR job. Use the official PyTorch installation selector for the exact
command.

### macOS / Linux

```bash
git clone https://github.com/TANGYirui/RISE_Meeting.git
cd RISE_Meeting

python3 -m venv .venv
.venv/bin/pip install -e ".[test,extract]"
```

## Environment Variables

Create a local `.env` file:

```powershell
copy .env.example .env
```

Required for query decomposition, agent execution, and answer judging:

```env
HKUST_GENAI_API_KEY=your_api_key
HKUST_GENAI_ENDPOINT=https://hkust.azure-api.net/hkust-genai/v1/chat/completions
HKUST_GENAI_MODEL=your_deployment_name
HKUST_GENAI_TIMEOUT=60
```

`.env` is ignored by Git and must never be committed.

## Adapting A Meeting Collection

The built-in metadata adapter supports the UAC filename conventions used during
development. It is a reference implementation, not a requirement of the RISE
pipeline.

To support another collection, adapt `parse_uac_filename()` in
`src/rise/uac_metadata.py`, or replace it with another parser that returns:

```text
doc_id          stable unique document identifier
filename        original source filename
role            semantic role such as minutes or agenda_item
meeting_date    normalized ISO date
item_number     optional agenda item number
title           optional display title
```

The extraction, corpus, BM25, workspace, agent, and evaluation layers consume
these normalized fields and do not need to know the source naming convention.

Recommended role semantics:

- `minutes`: official meeting record and primary decision evidence.
- `draft_minutes`: draft minutes included as an agenda item.
- `agenda_item`: proposal, report, budget, or background paper.
- `circulation`: document handled outside a standard meeting.
- `table_of_contents`: meeting membership/navigation evidence.
- `meeting_overview`: generated navigation document.

## Build The Corpus

The corpus builder accepts any flat source directory containing PDFs:

```powershell
.\.venv\Scripts\python.exe scripts\build_uac_corpus.py `
  --source-dir path\to\pdfs `
  --extracted-dir corpus\meeting_extracted `
  --out runs\meeting_corpus
```

Useful smoke-test options:

```powershell
# Process the first 20 PDFs.
.\.venv\Scripts\python.exe scripts\build_uac_corpus.py `
  --source-dir path\to\pdfs `
  --limit 20

# Process documents assigned to one meeting date by the metadata adapter.
.\.venv\Scripts\python.exe scripts\build_uac_corpus.py `
  --source-dir path\to\pdfs `
  --meeting-date 2024-05-09
```

Extraction is resumable:

- each completed document is written to the checkpoint immediately
- successful documents are skipped on the next run
- failed documents are retried on the next run
- the same Docling converter is reused during one process

Generated complete documents:

```text
corpus/meeting_extracted/
  agenda_item/<doc_id>.txt
  minutes/<doc_id>.txt
  draft_minutes/<doc_id>.txt
  circulation/<doc_id>.txt
  table_of_contents/<doc_id>.txt
  historical/<doc_id>.txt
```

Each source PDF becomes one complete text document. The file begins with
normalized metadata and then contains the Docling-produced body, headings, and
tables. These are not token chunks.

Generated corpus artifacts:

```text
runs/meeting_corpus/
  files/                    # Complete files exposed to RISE workspaces
  extraction_records.json  # Resumable extraction checkpoint and failure ledger
  document_manifest.json   # doc_id -> metadata and corpus path
  meeting_manifest.json    # meeting date -> related document IDs
  filename_docid_map.json  # corpus relative path -> doc_id
  completeness_report.json # Source, success, failure, overview, and index counts
  uac_corpus.parquet        # docid/text/url rows used to build BM25
```

The default output names remain `corpus/uac_extracted` and `runs/uac_corpus` for
backward compatibility. Use explicit CLI paths when applying the pipeline to a
different collection.

## Build The BM25 Index

```powershell
.\.venv\Scripts\python.exe scripts\build_bm25_index.py `
  --corpus runs\meeting_corpus\uac_corpus.parquet `
  --out runs\meeting_bm25
```

Generated index artifacts:

```text
runs/meeting_bm25/
  bm25_index/
  doc_ids.json
  meta.json
```

## Query Set Format

RISE runs against a JSONL query set. Keep local or private query sets under
`data/local/`.

```json
{"query_id":"1","query":"What decision was made about the proposed fee change?","answer":"Gold answer","gold_doc_ids":["item_doc_id","minutes_doc_id"],"evidence_doc_ids":["minutes_doc_id"]}
```

Fields:

- `query_id`: stable query identifier.
- `query`: question presented to the agent.
- `answer`: gold answer used by answer evaluation.
- `gold_doc_ids`: relevant documents used for retrieval recall.
- `evidence_doc_ids`: documents containing the strongest answer evidence.

Questions without gold labels can still generate answers, but recall and answer
accuracy cannot be measured objectively.

## Run RISE

```powershell
.\.venv\Scripts\python.exe scripts\run_rise.py `
  --mini-dev data\local\queries.jsonl `
  --index-dir runs\meeting_bm25 `
  --filename-map runs\meeting_corpus\filename_docid_map.json `
  --bc-plus-docs runs\meeting_corpus\files `
  --document-manifest runs\meeting_corpus\document_manifest.json `
  --meeting-manifest runs\meeting_corpus\meeting_manifest.json `
  --related-doc-cap 20 `
  --bm25-k 100 `
  --no-sandbox `
  --concurrency 1
```

Use `--no-sandbox` on Windows because upstream RISE uses the macOS-only
`sandbox-exec` utility. The line-based read tool remains restricted to the
configured corpus or workspace root.

RISE currently provides experiment artifacts rather than a web frontend. A
frontend can be added later without changing the corpus and evaluation
contracts.

## Run Outputs

Each RISE run creates a directory under `runs/`:

```text
runs/rise_<model>_t<turns>_k<k>_<index>/
  _working/qid<id>/          # Bounded documents available to the agent
  _traces/qid_<id>/single.json
                             # Search, shell, read, and model trajectory
  _per_query/qid_<id>.json   # Answer, surfaced documents, coverage, and cost
  _summary.json              # Aggregate run statistics before judging
  _judge_summary.json        # Answer accuracy after judging
```

Use `_working` to inspect the actual interaction space. Use `_traces` to inspect
the agent's search terms, shell commands, line reads, and final response. Use
`_per_query` for machine-readable per-question evaluation.

## Evaluation

Summarize retrieval recall, evidence recall, document coverage, tool usage,
latency, and cost:

```powershell
.\.venv\Scripts\python.exe scripts\summarize_runs.py runs\<run-directory>
```

Evaluate generated answers with the configured HKUST model:

```powershell
.\.venv\Scripts\python.exe scripts\judge.py `
  --run-dir runs\<run-directory> `
  --mode online `
  --judge-model your_deployment_name
```

Important metrics:

- `BM25 gold_R`: recall of labeled relevant documents.
- `BM25 ev_R`: recall of labeled evidence documents.
- `coverage_mean`: fraction of relevant documents surfaced to the agent.
- `accuracy`: judged final-answer correctness.
- `_traces`: qualitative evidence that the agent searched and read effectively.

## Tests

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run a syntax check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

## Notes For Maintainers

- Do not commit `.env`, source PDFs, extracted documents, indexes, run outputs,
  local query sets, or private project documentation.
- Keep collection-specific metadata parsing isolated from the RISE retrieval and
  agent layers.
- Review `completeness_report.json` and failed extraction records before
  building an index.
- Rebuild the BM25 index after changing the extracted corpus.
- Keep `gold_doc_ids` stable when comparing experiments.
- Prefer plain descriptive commit messages, for example:
  `Explain meeting corpus outputs`.

## Upstream RISE

This repository preserves the upstream RISE agent, retrieval tools, baselines,
trajectory schema, and evaluation scripts. See the original
[RISE repository](https://github.com/texttron/RISE) and
[paper](https://arxiv.org/abs/2606.06880) for the method and benchmark details.
