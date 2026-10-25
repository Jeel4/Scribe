import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Badge, Empty, fmt, Loading, Notice, PageHeader, Section, useLoad } from "../components/ui.jsx";

const METRICS = [["rouge1", "ROUGE-1"], ["rouge2", "ROUGE-2"], ["rougeL", "ROUGE-L"]];
const KIND_LABELS = { action: "Actions", decision: "Decisions", risk: "Risks", question: "Questions", deadline: "Deadlines" };

function RougeSummary({ ev }) {
  const { rouge, rouge_paired: paired } = ev;
  if (rouge.tfidf.meetings === 0 && rouge.distilbart.meetings === 0) {
    return (
      <Empty title="No ROUGE scores yet">
        ROUGE is only computed for meetings that have a human reference summary. Add one on a meeting’s
        “Reference and ROUGE” tab, or import AMI meetings with <code>scripts/import_ami.py</code>.
      </Empty>
    );
  }
  return (
    <>
      <div className="overflow-x-auto rounded border border-rule bg-sheet">
        <table className="table">
          <thead>
            <tr><th>Summary method</th><th className="num">Meetings scored</th>{METRICS.map(([k, l]) => <th key={k} className="num">{l} F1</th>)}</tr>
          </thead>
          <tbody>
            {[["tfidf", "TF-IDF extractive"], ["distilbart", "DistilBART abstractive"]].map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                <td className="num">{rouge[k].meetings}</td>
                {METRICS.map(([m]) => <td key={m} className="num">{fmt.score(rouge[k][m])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm text-muted">
        {paired.meetings > 0
          ? `Paired over the ${paired.meetings} meeting${paired.meetings > 1 ? "s" : ""} where both methods have real scores: TF-IDF ${fmt.score(paired.tfidf.rouge1)} vs DistilBART ${fmt.score(paired.distilbart.rouge1)} ROUGE-1.`
          : "No meeting has scores for both methods yet, so the two rows are not directly comparable."}
        {" "}DistilBART fallbacks are never scored, so they cannot make the two methods look identical.
      </p>
    </>
  );
}

function RetrievalEval({ meetings }) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("semantic");
  const [k, setK] = useState("5");
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function parse() {
    const queries = [];
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    for (const [i, line] of lines.entries()) {
      const at = line.lastIndexOf("|");
      const id = Number(line.slice(at + 1).trim());
      if (at < 1 || !Number.isInteger(id)) throw new Error(`Line ${i + 1}: write it as “query | meeting id”.`);
      queries.push({ query: line.slice(0, at).trim(), gold_meeting_id: id });
    }
    if (!queries.length) throw new Error("Add at least one query.");
    return queries;
  }
  async function run(e) {
    e.preventDefault();
    setError(null);
    setRes(null);
    let queries;
    try { queries = parse(); } catch (err) { return setError(err.message); }
    setBusy(true);
    try { setRes(await api.evaluateRetrieval({ mode, k: Number(k), queries })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <form onSubmit={run} className="space-y-3">
        <p className="text-sm text-muted">
          Write one test query per line with the number of the meeting that should answer it. Only use pairs
          you have checked by hand: the metric is only as good as these labels.
        </p>
        <label htmlFor="gold" className="sr-only">Queries with their correct meeting</label>
        <textarea id="gold" className="field min-h-36 font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={meetings.length ? `who updates the payment webhooks | ${meetings[0].meeting_id}` : "query | meeting id"} />
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">Method
            <select className="field w-auto" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="semantic">Semantic</option><option value="lexical">Lexical</option>
            </select>
          </label>
          <label className="flex items-center gap-2">k
            <select className="field w-auto" value={k} onChange={(e) => setK(e.target.value)}>
              {["1", "3", "5", "10"].map((v) => <option key={v}>{v}</option>)}
            </select>
          </label>
          <button className="btn" disabled={busy || !text.trim()}>{busy ? "Evaluating…" : "Evaluate retrieval"}</button>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {meetings.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted">Meeting numbers</summary>
            <ul className="mt-2 space-y-0.5">{meetings.map((m) => <li key={m.meeting_id}>#{m.meeting_id} {m.title}</li>)}</ul>
          </details>
        )}
      </form>
      <div>
        {res ? (
          <>
            <dl className="grid grid-cols-3 gap-4 border-y border-rule py-3">
              <div><dt className="text-sm text-muted">Top-1 accuracy</dt><dd className="text-xl font-semibold tabular-nums">{fmt.pct(res.summary.top1_accuracy)}</dd></div>
              <div><dt className="text-sm text-muted">Top-{res.summary.k} accuracy</dt><dd className="text-xl font-semibold tabular-nums">{fmt.pct(res.summary.topk_accuracy)}</dd></div>
              <div><dt className="text-sm text-muted">MRR</dt><dd className="text-xl font-semibold tabular-nums">{fmt.score(res.summary.mrr)}</dd></div>
            </dl>
            <p className="mt-2 text-xs text-muted">
              {res.summary.evaluated_queries} queries, {res.mode} search, meeting-level hits. A query counts as a hit when any retrieved sentence comes from the labelled meeting.
            </p>
            <div className="mt-3 overflow-x-auto rounded border border-rule bg-sheet">
              <table className="table">
                <thead><tr><th>Query</th><th className="num">Meeting</th><th>Top-1</th><th>Top-{res.summary.k}</th><th className="num">RR</th></tr></thead>
                <tbody>
                  {res.rows.map((r, i) => (
                    <tr key={i}>
                      <td>{r.query}</td><td className="num">#{r.gold_meeting_id}</td>
                      <td>{r.top1_hit ? "Hit" : <span className="text-bad">Miss</span>}</td>
                      <td>{r.topk_hit ? "Hit" : <span className="text-bad">Miss</span>}</td>
                      <td className="num">{fmt.score(r.reciprocal_rank, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <Empty title="No retrieval results yet">Scribe does not report retrieval accuracy without labelled queries.</Empty>
        )}
      </div>
    </div>
  );
}

function NotebookFindings() {
  return (
    <details className="rounded border border-rule bg-sheet px-5 py-4">
      <summary className="cursor-pointer font-medium">Why the notebook showed identical ROUGE scores for both methods</summary>
      <div className="mt-3 max-w-3xl space-y-3 text-sm leading-relaxed">
        <p>
          A later notebook cell loaded DistilBART with <code>pipeline("summarization", …)</code>. That task was
          removed in Transformers v5, so loading failed, the summariser was set to <code>None</code>, and the
          summarise function silently returned the TF-IDF summary instead. Both columns were therefore scoring the
          same text, which is why every row in that table matched exactly (mean ROUGE-1 0.2395 for both).
        </p>
        <p>
          An earlier cell called the model directly with <code>AutoModelForSeq2SeqLM.generate</code> and did produce
          real DistilBART summaries. The notebook recorded these means over 138 AMI meetings with reference summaries:
        </p>
        <table className="table max-w-md">
          <thead><tr><th>Method</th><th className="num">ROUGE-1</th><th className="num">ROUGE-2</th><th className="num">ROUGE-L</th></tr></thead>
          <tbody>
            <tr><td>TF-IDF</td><td className="num">0.2656</td><td className="num">0.0367</td><td className="num">0.1306</td></tr>
            <tr><td>DistilBART</td><td className="num">0.2044</td><td className="num">0.0410</td><td className="num">0.1314</td></tr>
          </tbody>
        </table>
        <p className="text-muted">
          These figures are copied from the notebook’s saved output and were not recomputed by this app. Scribe uses
          the working direct-generation path, records a DistilBART failure as a labelled fallback, and never scores
          fallback text as DistilBART.
        </p>
      </div>
    </details>
  );
}

export default function Evaluation() {
  const state = useLoad(() => api.evaluation(), []);
  return (
    <>
      <PageHeader title="Evaluation">
        Measurements this app can compute honestly. Extraction quality and retrieval accuracy are not estimated without labelled data.
      </PageHeader>
      <Loading state={state} label="Loading evaluation">
        {(ev) => (
          <>
            <dl className="mb-8 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-rule py-4 sm:grid-cols-3 lg:grid-cols-6">
              {[
                ["Meetings analysed", fmt.n(ev.corpus.analysed_meetings)],
                ["With a reference", fmt.n(ev.corpus.with_reference)],
                ["Average words", fmt.n(ev.corpus.avg_words && Math.round(ev.corpus.avg_words))],
                ["Average sentences", fmt.n(ev.corpus.avg_sentences && Math.round(ev.corpus.avg_sentences))],
                ["DistilBART fallbacks", fmt.n(ev.corpus.distilbart_fallbacks)],
                ["Identical summary pairs", fmt.n(ev.corpus.identical_summary_pairs)],
              ].map(([l, v]) => (
                <div key={l}><dt className="text-sm text-muted">{l}</dt><dd className="text-xl font-semibold tabular-nums">{v}</dd></div>
              ))}
            </dl>
            {ev.corpus.distilbart_fallbacks > 0 && (
              <div className="mb-6">
                <Notice tone="warn">
                  DistilBART did not run for {ev.corpus.distilbart_fallbacks} meeting{ev.corpus.distilbart_fallbacks > 1 ? "s" : ""}.
                  Those meetings have no DistilBART score. The model status in the sidebar shows why.
                </Notice>
              </div>
            )}

            <Section title="Summary quality (ROUGE F1)"><RougeSummary ev={ev} /></Section>

            <Section title="Per meeting" aside="Counts of rule-based candidates, not accuracy">
              {ev.meetings.length === 0 ? (
                <Empty title="No analysed meetings">Analyse a meeting to see its statistics here.</Empty>
              ) : (
                <div className="overflow-x-auto rounded border border-rule bg-sheet">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Meeting</th><th className="num">Words</th><th className="num">Sentences</th>
                        <th className="num">TF-IDF R-1</th><th className="num">BART R-1</th>
                        {Object.values(KIND_LABELS).map((l) => <th key={l} className="num">{l}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {ev.meetings.map((m) => {
                        const r = (k) => m.summaries[k]?.rouge?.rouge1;
                        const bart = m.summaries.distilbart;
                        return (
                          <tr key={m.meeting_id}>
                            <td className="min-w-48">
                              <Link className="text-navy hover:underline" to={`/meetings/${m.meeting_id}?tab=scores`}>{m.title}</Link>
                              {m.source === "sample" && <span className="ml-2"><Badge tone="warn">Synthetic</Badge></span>}
                              {m.summaries_identical && <span className="ml-2"><Badge tone="bad">Identical summaries</Badge></span>}
                            </td>
                            <td className="num">{fmt.n(m.word_count)}</td>
                            <td className="num">{fmt.n(m.sentence_count)}</td>
                            <td className="num">{m.has_reference ? fmt.score(r("tfidf")) : <span className="text-muted">no ref.</span>}</td>
                            <td className="num">
                              {!bart ? <span className="text-muted">not run</span>
                                : bart.status === "fallback" ? <span className="text-warn">fallback</span>
                                : m.has_reference ? fmt.score(r("distilbart")) : <span className="text-muted">no ref.</span>}
                            </td>
                            {Object.keys(KIND_LABELS).map((k) => <td key={k} className="num">{m.extraction_counts[k]}</td>)}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="mt-2 text-xs text-muted">
                There is no ground truth for action items, decisions or risks in uploaded transcripts, so Scribe reports
                how many candidates the rules found, not precision or recall.
              </p>
            </Section>

            <Section title="Retrieval accuracy from labelled queries">
              <RetrievalEval meetings={ev.meetings} />
            </Section>

            <Section title="Notes from the original notebook"><NotebookFindings /></Section>
          </>
        )}
      </Loading>
    </>
  );
}
