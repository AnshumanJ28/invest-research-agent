# Role 3 RAG and Memo Generation

The Role 3 layer reads the SQLite database produced by the existing C++ pipeline.
It does not duplicate ingestion, financial calculations, sentiment scoring, or
database table creation.

```text
cpp_pipeline/invest.sqlite
  -> chunking.py
  -> local embeddings
  -> FAISS retrieval
  -> Gemini memo generation
  -> claim/evidence verification
  -> cited, auditable memo outputs
```

## Setup

Use Python 3.10 from the repository root:

```powershell
py -3.10 -m pip install -r requirements.txt
```

Create `.env` from `.env.example` and set:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
RAG_DB_PATH=cpp_pipeline/invest.sqlite
RAG_OUTPUT_DIR=rag/output
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_TOP_K=5
ENABLE_VERIFICATION=true
VERIFY_BATCH_SIZE=1
```

`.env` is local-only and should not be committed.

## Commands

Run retrieval only, without Gemini:

```powershell
py -3.10 -m rag.main RELIANCE.NS --retrieval-only
```

Generate and verify a memo:

```powershell
py -3.10 -m rag.main RELIANCE.NS
```

Verify an existing memo without regenerating:

```powershell
py -3.10 -m rag.main RELIANCE.NS --verify-existing
```

Run the original C++ pipeline without Role 3:

```powershell
cd cpp_pipeline
.\build\Release\invest_pipeline.exe RELIANCE.NS --skip-rag
```

When the C++ executable is run without `--skip-rag`, it runs the existing
pipeline first and then calls:

```powershell
py -3.10 -m rag.main <TICKER>
```

## Outputs

Generated files are saved under `rag/output/<TICKER>/`:

- `memo.json`
- `memo.md`
- `verification.json`
- `verified_memo.json`
- `verified_memo.md`

## Verification

`rag/verification.py` performs deterministic checks before semantic checks:

- citation ID exists
- cited evidence exists
- citation ticker matches the memo ticker
- claim text is not empty
- evidence text is not empty

Semantic verification sends only the claim and cited evidence to Gemini. It
returns one of `SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, or `CONTRADICTED`.

Unsupported and contradicted claims are removed from the safe verified memo.
Partial claims are kept with a review flag by default.

## Current Data Limitations

- `news_articles` and `transcript_utterances` may be empty for the current DB.
- Competitor comparison is not available from the current SQLite outputs.
- Financial facts come from existing SQLite statements; ratios are computed by
  the C++ pipeline but are not currently persisted as reusable rows.
- Human review remains appropriate for financial research output.
