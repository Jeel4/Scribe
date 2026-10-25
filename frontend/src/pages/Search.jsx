import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { Empty, fmt, Notice, PageHeader, Spinner, useLoad } from "../components/ui.jsx";

const MODES = [
  { id: "semantic", label: "Semantic", help: "Finds sentences with similar meaning (MiniLM embeddings, FAISS cosine similarity), even without shared words." },
  { id: "lexical", label: "Lexical", help: "Finds sentences that share words with the query (TF-IDF cosine similarity)." },
  { id: "compare", label: "Compare both", help: "Runs both searches side by side for the same query." },
];

function Results({ title, res, query }) {
  if (res.loading) return <div className="py-6"><Spinner label="Searching" /></div>;
  if (res.error) {
    return (
      <div className="self-start">
        {title && <h2 className="mb-2 font-semibold">{title}</h2>}
        <Notice tone={res.error.status === 503 ? "warn" : "error"}>{res.error.message}</Notice>
      </div>
    );
  }
  if (!res.data) return null;
  const { results, mode, min_score, index } = res.data;
  return (
    <div className="min-w-0">
      {title && <h2 className="mb-2 font-semibold">{title}</h2>}
      {results.length === 0 ? (
        <Empty title={index.indexed_sentences === 0 ? "Nothing to search yet" : `No matches for “${query}”`}>
          {index.indexed_sentences === 0
            ? "Analyse at least one meeting first."
            : mode === "semantic"
              ? `No sentence reached the similarity threshold of ${min_score}. Try other wording or lexical search.`
              : "No sentence shares a word with the query (common words are ignored). Try semantic search."}
        </Empty>
      ) : (
        <ol className="divide-y divide-rule rounded border border-rule bg-sheet">
          {results.map((h, i) => (
            <li key={`${h.meeting_id}-${h.sentence_index}`} className="px-4 py-3">
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3 text-xs text-muted">
                <span className="tabular-nums font-medium text-ink">{i + 1}.</span>
                <Link className="text-navy underline" to={`/meetings/${h.meeting_id}?tab=transcript`}>{h.meeting_title}</Link>
                <span>Meeting #{h.meeting_id}</span>
                <span>Line {h.sentence_index + 1}</span>
                <span className="ml-auto tabular-nums" title={mode === "semantic" ? "Cosine similarity of embeddings" : "TF-IDF cosine similarity"}>
                  Score {fmt.score(h.score)}
                </span>
              </div>
              {h.before && <p className="text-sm text-muted"><span className="font-medium">{h.before.speaker}</span> {h.before.text}</p>}
              <p className="my-0.5 font-serif text-[16px]"><span className="font-sans text-sm font-semibold">{h.speaker}</span> <mark className="hl">{h.text}</mark></p>
              {h.after && <p className="text-sm text-muted"><span className="font-medium">{h.after.speaker}</span> {h.after.text}</p>}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-2 text-xs text-muted">
        Searched {fmt.n(mode === "semantic" ? index.embedded_sentences : index.indexed_sentences)} sentences
        from {fmt.n(mode === "semantic" ? index.embedded_meetings : index.indexed_meetings)} meetings.
        {mode === "semantic" && ` Results below a similarity of ${min_score} are hidden.`}
      </p>
    </div>
  );
}

const idle = { data: null, error: null, loading: false };

export default function Search() {
  const [params, setParams] = useSearchParams();
  const meetings = useLoad(() => api.meetings(), []);
  const [q, setQ] = useState(params.get("q") || "");
  const [mode, setMode] = useState(params.get("mode") || "semantic");
  const [meetingId, setMeetingId] = useState(params.get("meeting_id") || "");
  const [topK, setTopK] = useState(params.get("top_k") || "10");
  const [sem, setSem] = useState(idle);
  const [lex, setLex] = useState(idle);
  const [ran, setRan] = useState(null);
  const seq = useRef(0);

  async function run(p) {
    const n = ++seq.current; // ignore responses that arrive after a newer search
    const base = { q: p.q, top_k: p.top_k, ...(p.meeting_id ? { meeting_id: p.meeting_id } : {}) };
    const go = (m, set) => {
      set({ ...idle, loading: true });
      return api.search({ ...base, mode: m })
        .then((data) => n === seq.current && set({ data, error: null, loading: false }))
        .catch((error) => n === seq.current && set({ data: null, error, loading: false }));
    };
    setRan(p);
    if (p.mode !== "lexical") go("semantic", setSem); else setSem(idle);
    if (p.mode !== "semantic") go("lexical", setLex); else setLex(idle);
  }

  // Run the search described by the URL (also on back/forward).
  useEffect(() => {
    const p = Object.fromEntries(params);
    if (p.q) run({ q: p.q, mode: p.mode || "semantic", meeting_id: p.meeting_id || "", top_k: p.top_k || "10" });
    else { setRan(null); setSem(idle); setLex(idle); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  function submit(e) {
    e.preventDefault();
    const query = q.trim();
    if (!query) return;
    const next = { q: query, mode, top_k: topK, ...(meetingId ? { meeting_id: meetingId } : {}) };
    // Same query again (e.g. after deleting a meeting): the URL does not
    // change, so run it directly to get fresh results.
    if (new URLSearchParams(next).toString() === params.toString()) run({ meeting_id: "", ...next });
    else setParams(next);
  }

  const done = (meetings.data?.meetings || []).filter((m) => m.status === "done");
  const active = MODES.find((m) => m.id === mode);

  return (
    <>
      <PageHeader title="Search">Search every analysed meeting sentence by sentence.</PageHeader>
      <form onSubmit={submit} className="mb-6 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label htmlFor="q" className="sr-only">Search query</label>
          <input id="q" className="field text-base" value={q} maxLength={500} onChange={(e) => setQ(e.target.value)}
                 placeholder="For example: who is updating the payment webhooks?" />
          <button className="btn justify-center" disabled={!q.trim()}>Search</button>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
          <fieldset className="flex rounded border border-rule bg-sheet p-0.5">
            <legend className="sr-only">Search method</legend>
            {MODES.map((m) => (
              <label key={m.id} className={`cursor-pointer rounded px-3 py-1 ${mode === m.id ? "bg-navy text-white" : "text-ink/80 hover:bg-paper"}`}>
                <input type="radio" name="mode" value={m.id} checked={mode === m.id} onChange={() => setMode(m.id)} className="sr-only" />
                {m.label}
              </label>
            ))}
          </fieldset>
          <label className="flex items-center gap-2">
            Meeting
            <select className="field w-auto max-w-64" value={meetingId} onChange={(e) => setMeetingId(e.target.value)}>
              <option value="">All meetings</option>
              {done.map((m) => <option key={m.id} value={m.id}>#{m.id} {m.title}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">
            Results
            <select className="field w-auto" value={topK} onChange={(e) => setTopK(e.target.value)}>
              {["5", "10", "20", "50"].map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
        </div>
        <p className="text-xs text-muted">{active.help}</p>
      </form>

      {!ran ? (
        <Empty title="Search across your meetings">
          {done.length === 0 && meetings.data
            ? "No meeting has been analysed yet, so there is nothing to search."
            : "Type a question or phrase above. Semantic search works best with a full question; lexical search with exact terms."}
        </Empty>
      ) : ran.mode === "compare" ? (
        <div className="grid gap-8 lg:grid-cols-2">
          <Results title="Semantic" res={sem} query={ran.q} />
          <Results title="Lexical" res={lex} query={ran.q} />
        </div>
      ) : (
        <Results res={ran.mode === "semantic" ? sem : lex} query={ran.q} />
      )}
    </>
  );
}
