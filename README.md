# Scribe — meeting analysis and knowledge assistant

Scribe turns plain-text meeting transcripts into summaries, candidate action
items, decisions, risks, open questions and deadlines, and lets you search
every analysed meeting by meaning (semantic) or by words (lexical). It is a
web application built around the NLP pipeline in
`Scribe_Final_Report_Ready.ipynb`, using the same pretrained models and the
same rules. Nothing is trained.

- **Backend:** Python, Flask, SQLite
- **Frontend:** React (Vite) and Tailwind CSS
- **Models (as in the notebook):** `sshleifer/distilbart-cnn-12-6`
  (abstractive summary), `sentence-transformers/all-MiniLM-L6-v2` + FAISS
  (semantic search), KeyBERT (keywords), spaCy `en_core_web_sm` (sentences and
  named entities), scikit-learn TF-IDF (extractive summary and lexical
  search), `rouge-score` (ROUGE-1/2/L F1)

---

## 1. Prerequisites

| Tool | Version |
|---|---|
| Python | 3.10 – 3.13 |
| Node.js | 18 or newer (with npm) |
| Disk space | about 3 GB for PyTorch and the models |
| Internet | needed the first time, to download the models from Hugging Face |

The DistilBART, MiniLM and KeyBERT models (about 1.3 GB in total) are downloaded
automatically from huggingface.co the first time they are used, then cached
in `~/.cache/huggingface`.

## 2. Install

From the project folder (the one containing this README):

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
# Optional but recommended without an NVIDIA GPU: the CPU build of PyTorch is ~200 MB instead of ~3 GB
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu   # optional, see above
pip install -r backend\requirements.txt

cd frontend
npm install
cd ..
```

`requirements.txt` installs the spaCy English model from GitHub. If that
fails, run `python -m spacy download en_core_web_sm`.

Configuration is optional: copy `backend/.env.example` to `backend/.env` to
change the port, upload limit, device, models and so on.

## 3. Start the app

You need two terminals (or use `./start.sh` on macOS/Linux, which starts both).

**Terminal 1: backend** (with the virtual environment activated)

```bash
cd backend
python run.py
```

The API runs at <http://127.0.0.1:5000>. The SQLite database is created
automatically at `backend/instance/scribe.db`.

**Terminal 2: frontend**

```bash
cd frontend
npm run dev
```

Open **<http://localhost:5173>** in your browser.

*Single-port alternative:* run `npm run build` in `frontend/` once; Flask then
serves the built app at <http://127.0.0.1:5000> and you only need terminal 1.

## 4. Using Scribe

### Upload and analyse a transcript

1. On **Dashboard**, drop a `.txt` file onto the upload box or choose one.
   Lines like `Maya: We need to…` or AMI-style `[A] We need to…` are read as
   speaker turns; untagged lines continue the previous speaker.
2. Optionally give it a title and paste a **reference summary** (a summary
   written by a person). The reference is only used to compute ROUGE.
3. Leave **Also generate a DistilBART summary** ticked to run the
   abstractive model. On a CPU this takes roughly 20–60 seconds for a long
   meeting; the very first run also downloads and loads the models.
4. Click **Upload and analyse**. You are taken to the meeting page, which
   shows the current step and updates itself until the analysis is done.

No transcript at hand? Use one of the **synthetic samples** listed under the
upload form. They were written for this demo and are labelled as such
everywhere in the app (see `samples/README.md`).

Upload rules: `.txt` only, UTF-8 text, up to 2 MB, at least 20 words. Files
are read into memory as text and stored in the database; they are never
saved under their original name or executed.

### The meeting page

| Tab | What it shows |
|---|---|
| Summaries | TF-IDF extractive summary (6 sentences copied from the transcript) and the DistilBART abstractive summary. If DistilBART could not run, the tab says so and the text is marked “Fallback — not DistilBART”. |
| Candidate items | Action items, decisions, risks, open questions and deadlines in separate tabs, with speaker, likely owner and deadline phrase. Click a line number to jump to it in the transcript. |
| Entities and keywords | spaCy named entities grouped by type and KeyBERT keywords with scores. |
| Transcript | The transcript split into numbered sentences per speaker. Sentences picked up by an extraction rule are highlighted. |
| Reference and ROUGE | ROUGE-1/2/L F1 of each summary against the reference. Add, change or remove the reference here; ROUGE is recalculated without re-running the models. |

Use **Re-run analysis** after fixing a model problem, or to add a DistilBART
summary later. **Delete** removes the meeting and everything derived from it,
including its search entries.

### Search

On **Search**, type a question or phrase and pick a method:

- **Semantic:** embeds the query with MiniLM and finds the most similar
  sentences with FAISS (cosine similarity). It finds paraphrases that share no
  words with the query. Results below a similarity of 0.25 are hidden
  (`SCRIBE_SEMANTIC_MIN_SCORE`).
- **Lexical:** TF-IDF cosine similarity; only sentences sharing words with
  the query match.
- **Compare both:** runs both side by side.

Each result shows the meeting (title and number), speaker, line number,
score, and the sentences before and after it. You can restrict the search to
one meeting. The index is rebuilt from the database after every upload,
re-analysis or delete, so deleted meetings never appear in results.

### Evaluation

The **Evaluation** page only reports what can be measured honestly:

- **ROUGE F1** per method, averaged over meetings that have a reference
  summary, plus a paired comparison over meetings where both methods have
  real scores. DistilBART fallbacks are never scored.
- **Corpus statistics**: words, sentences, number of fallbacks, and a check
  for identical summary pairs (the notebook bug, see below).
- **Extraction counts** per meeting. Without hand-labelled action items there
  is no ground truth, so Scribe does not claim any precision or recall.
- **Retrieval accuracy (Top-1, Top-k, MRR)** only for query → meeting pairs
  that you type in and have checked yourself.

### Evaluate on the AMI corpus

To get meaningful ROUGE numbers, import AMI meetings with their human
reference summaries. Download the AMI manual annotations
(`ami_public_manual_1.6.2.zip`) from the AMI corpus website, extract them,
then (backend folder, virtual environment active):

```bash
python scripts/import_ami.py --annotations /path/to/ami_annotations --limit 10
# or reuse the CSV the notebook wrote:
python scripts/import_ami.py --csv ami_scribe_dataset.csv --only-with-summary --limit 10
```

Add `--no-abstractive` to skip DistilBART (much faster). The script uses the
notebook's final AMI parser and analyses each meeting with the same
pipeline as uploads.

## 5. Why the notebook showed identical ROUGE scores

The notebook's final comparison table showed exactly the same ROUGE scores
for “TF-IDF” and “DistilBART / Fallback” for every meeting. The cause:

1. A later cell loaded the model with `pipeline("summarization", …)`.
   Transformers v5 removed the `summarization` pipeline task, so loading
   raised an error that the cell caught.
2. The summariser was set to `None`, and `summarize()` then returned the
   TF-IDF summary instead.
3. Both columns therefore scored the same text.

The earlier evaluation cell, which called
`AutoModelForSeq2SeqLM.generate` directly, did produce real DistilBART
summaries. Its recorded means over 138 AMI meetings were TF-IDF 0.2656 /
0.0367 / 0.1306 and DistilBART 0.2044 / 0.0410 / 0.1314 (ROUGE-1 / 2 / L).
Those figures come from the notebook's saved output; this app has not
recomputed them.

What Scribe does differently: it uses the working direct-generation code,
stores each summary with a status (`ok` or `fallback`), shows the reason
for a fallback in the interface, never computes a DistilBART ROUGE score for
fallback text, and flags any meeting whose two summaries are identical.

## 6. What comes from the notebook, and what changed

Kept as in the notebook: the model choices, TF-IDF summary (6 sentences,
sentences over 20 characters), the chunked hierarchical DistilBART summary
(850-token chunks, 4 beams, 20–120 new tokens), KeyBERT settings (1–3-grams,
MMR, diversity 0.45, top 8), the extraction regular expressions, ROUGE with
stemming, the retrieval metrics, and the AMI parser.

Changed, with the reason:

| Change | Why |
|---|---|
| `pipeline("summarization")` not used | Removed in Transformers v5; it caused the identical-ROUGE bug. |
| Transcript split per speaker turn before spaCy | Every sentence keeps its speaker, and `[B]`-style AMI tags work for owner detection (the notebook's owner regex only matched `Name:`). |
| Pronouns (“We”, “It”, “This”…) are not accepted as owners | The notebook's `Name will` pattern also matched “We will”. |
| Speaker labels removed before keyword extraction and NER | Otherwise speaker names dominate the keyword list and `[A]` appears as an entity. |
| The TF-IDF search vectoriser is fitted once on the indexed sentences | The notebook refitted it for every query; results are nearly the same and much faster. |
| Full transcript is summarised | The notebook's later `summarize()` cut the text at 9,000 characters. |
| Embeddings stored in SQLite | The FAISS index can be rebuilt after every change without re-encoding. |

## 7. Run the tests

```bash
cd backend
python -m pytest
```

The tests use the real spaCy model, TF-IDF, ROUGE and FAISS code, and go
through the HTTP API (upload validation, analysis, fallbacks, extraction,
ROUGE recalculation, search modes, no stale results after delete, retrieval
metrics, error handling). DistilBART and KeyBERT are switched off in tests,
and MiniLM is replaced by a simple hashed bag-of-words embedder that only
checks the FAISS indexing logic. It is not a semantic model.

## 8. Common problems

| Symptom | Fix |
|---|---|
| “Cannot reach the Scribe backend” in the browser | Start `python run.py` in `backend/`. The Vite dev server forwards `/api` to port 5000. |
| Sidebar shows DistilBART / MiniLM / KeyBERT “unavailable” | The models could not be downloaded or loaded. Hover over the red dot for the error. Check your internet connection (huggingface.co must be reachable on first use), then click **Retry loading** and **Re-run analysis** on affected meetings. |
| “spaCy model 'en_core_web_sm' is not installed” | `python -m spacy download en_core_web_sm` |
| Semantic search says it is unavailable | The embedding model is not loaded, or no meeting was analysed while it was. Fix the model, then re-run analysis on the meetings. Lexical search works in the meantime. |
| “File is too large” | Raise `SCRIBE_MAX_UPLOAD_MB` in `backend/.env`. |
| “… is not valid UTF-8 text” | Re-save the transcript as UTF-8 (most editors offer this in “Save as”). |
| DistilBART is very slow | Expected on CPU. Untick DistilBART when uploading, or set `SCRIBE_DEVICE=cuda` with an NVIDIA GPU. |
| A meeting says “Analysis was interrupted” | The server stopped during the analysis. Click **Re-run analysis**. |
| Port 5000 is in use (macOS AirPlay uses it) | Set `SCRIBE_PORT=5001` in `backend/.env` and start Vite with `VITE_BACKEND_URL=http://127.0.0.1:5001 npm run dev`. |

## 9. Project structure

```
scribe/
├── backend/
│   ├── run.py                  start the API
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── __init__.py         create_app(): config, database, models, routes, errors
│   │   ├── config.py           settings from environment variables
│   │   ├── db.py               SQLite schema and connections (database initialisation)
│   │   ├── models.py           loads each pretrained model once, records load errors
│   │   ├── api/                HTTP routes: meetings, search, evaluation, system
│   │   └── services/
│   │       ├── text.py           cleaning, speaker turns, sentence splitting
│   │       ├── summarization.py  TF-IDF and DistilBART summaries
│   │       ├── nlp.py            named entities and keywords
│   │       ├── extraction.py     action items, decisions, risks, questions, deadlines
│   │       ├── retrieval.py      FAISS semantic index and TF-IDF lexical index
│   │       ├── evaluation.py     ROUGE and retrieval metrics
│   │       └── analysis.py       runs the pipeline in a background worker
│   ├── scripts/import_ami.py   import AMI meetings with reference summaries
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.js          dev server and /api proxy
│   └── src/
│       ├── App.jsx             layout, navigation, model status
│       ├── api.js              calls to the backend
│       ├── components/         upload form, tabs, badges, notices
│       └── pages/              Dashboard, Meetings, Meeting, Search, Evaluation
├── samples/                    synthetic demo transcripts (clearly labelled)
└── start.sh                    starts backend and frontend together
```

### API overview

| Method and path | Purpose |
|---|---|
| `GET /api/health` | database, model and index status |
| `GET /api/dashboard` | counts for the dashboard |
| `GET /api/meetings`, `POST /api/meetings` | list; upload (multipart: `file`, `title`, `reference_summary`, `abstractive`) |
| `GET /api/meetings/<id>`, `DELETE /api/meetings/<id>` | full analysis; delete |
| `GET /api/meetings/<id>/status` | progress while analysing |
| `POST /api/meetings/<id>/analyze` | re-run analysis (`{"abstractive": true}`) |
| `PUT /api/meetings/<id>/reference` | set or clear the reference summary, recompute ROUGE |
| `GET /api/search?q=&mode=semantic\|lexical&top_k=&meeting_id=` | search |
| `GET /api/evaluation` | ROUGE, corpus statistics, extraction counts |
| `POST /api/evaluation/retrieval` | Top-1 / Top-k / MRR for your labelled queries |
| `GET /api/samples`, `POST /api/samples/<name>` | list and load synthetic samples |
| `POST /api/models/retry` | retry loading models that failed |

## 10. Known limitations

- Extraction is rule-based (keyword patterns). It produces false positives,
  for example any sentence with “should” becomes a candidate action item, and
  misses items phrased differently. The interface labels these as candidates.
- The owner is a guess: a capitalised name before will/should/must/can, else
  the speaker. Recap sentences such as “Priya tests the scripts…” get no owner.
- KeyBERT embeds the whole meeting with MiniLM, which reads only about the
  first 256 word pieces, so keywords for long meetings lean towards the start
  (a limitation inherited from the notebook).
- `en_core_web_sm` is small and mislabels some entities in spoken language.
- ROUGE measures word overlap with one reference summary. It favours
  extractive summaries on ROUGE-1 and says little about readability.
- One analysis runs at a time (a single background worker), and there is no
  login: run it locally, not on a public server.
