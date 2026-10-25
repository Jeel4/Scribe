import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import DeleteButton from "../components/DeleteButton.jsx";
import {
  Badge, Empty, fmt, Loading, Notice, PageHeader, Section, Spinner, StatusBadge, TabPanel, Tabs, useLoad,
} from "../components/ui.jsx";

const KINDS = [
  { id: "action", label: "Action items", owner: true, deadline: true },
  { id: "decision", label: "Decisions" },
  { id: "risk", label: "Risks" },
  { id: "question", label: "Open questions" },
  { id: "deadline", label: "Deadlines", owner: true, deadline: true },
];
const SOURCE = { upload: "Uploaded", sample: "Synthetic sample", ami: "AMI corpus" };

// ------------------------------------------------------------- summaries
function SummaryBlock({ title, s, method }) {
  if (!s) {
    return (
      <div>
        <h3 className="mb-2 font-semibold">{title}</h3>
        <p className="text-sm text-muted">
          Not generated for this run. Use “Re-run analysis” with DistilBART switched on to create it.
        </p>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{title}</h3>
        <StatusBadge status={s.status} />
      </div>
      {s.status === "fallback" && (
        <div className="mb-3">
          <Notice tone="warn" title="DistilBART did not run">{s.note}</Notice>
        </div>
      )}
      <p className={`reading ${s.status === "fallback" ? "text-muted" : ""}`}>{s.text}</p>
      <p className="mt-2 text-xs text-muted">
        {s.model_name}
        {s.status === "ok" && s.note ? `. ${s.note}` : ""}
        {method === "tfidf" && " Extractive: these are sentences copied from the transcript."}
      </p>
    </div>
  );
}

function Summaries({ m }) {
  return (
    <div className="grid gap-10 lg:grid-cols-2">
      <SummaryBlock title="Extractive (TF-IDF)" s={m.summaries.tfidf} method="tfidf" />
      <SummaryBlock title="Abstractive (DistilBART)" s={m.summaries.distilbart} method="distilbart" />
    </div>
  );
}

// ---------------------------------------------------------- extractions
function Items({ m, goToSentence }) {
  const [kind, setKind] = useState("action");
  const spec = KINDS.find((k) => k.id === kind);
  const rows = m.extractions[kind] || [];
  return (
    <>
      <Notice tone="info">
        These are candidates found with keyword rules from the notebook (for example “need to”, “we decided”,
        “risk”, a question mark, or a date phrase). They are not verified: expect some false positives and missed items,
        and check each one against the transcript.
      </Notice>
      <div className="mt-5">
        <Tabs label="Item type" active={kind} onChange={setKind}
              tabs={KINDS.map((k) => ({ id: k.id, label: k.label, count: (m.extractions[k.id] || []).length }))} />
        <TabPanel id={kind}>
          {rows.length === 0 ? (
            <Empty title={`No ${spec.label.toLowerCase()} found`}>
              None of the rule patterns matched a sentence in this transcript. Nothing is shown rather than guessing.
            </Empty>
          ) : (
            <div className="overflow-x-auto rounded border border-rule bg-sheet">
              <table className="table">
                <thead>
                  <tr>
                    <th className="num">Line</th><th>Sentence</th><th>Speaker</th>
                    {spec.owner && <th title="A name before will/should/must/can, otherwise the speaker">Likely owner</th>}
                    {spec.deadline && <th>Deadline phrase</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td className="num">
                        <button className="text-navy underline" onClick={() => goToSentence(r.sentence_index)}
                                aria-label={`Show line ${r.sentence_index + 1} in the transcript`}>
                          {r.sentence_index + 1}
                        </button>
                      </td>
                      <td className="min-w-72">{r.text}</td>
                      <td>{r.speaker || <span className="text-muted">—</span>}</td>
                      {spec.owner && <td>{r.owner || <span className="text-muted">Not stated</span>}</td>}
                      {spec.deadline && <td>{r.deadline || <span className="text-muted">None</span>}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabPanel>
      </div>
    </>
  );
}

// --------------------------------------------------- entities & keywords
function EntitiesKeywords({ m }) {
  const byLabel = useMemo(() => {
    const g = {};
    for (const e of m.entities) (g[e.label] ||= []).push(e);
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [m.entities]);
  const maxScore = Math.max(...m.keywords.map((k) => k.score), 0) || 1;
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <Section title="Keywords" aside={m.keyword_method === "keybert" ? "KeyBERT (MMR)" : "TF-IDF fallback"}>
        {m.keyword_method === "tfidf_fallback" && (
          <p className="mb-3 text-xs text-muted">KeyBERT could not be loaded, so these are the highest-weighted TF-IDF terms.</p>
        )}
        {m.keywords.length === 0 ? <p className="text-sm text-muted">No keywords found.</p> : (
          <ol className="space-y-2">
            {m.keywords.map((k) => (
              <li key={k.keyword} className="text-sm">
                <div className="flex justify-between gap-3"><span>{k.keyword}</span><span className="tabular-nums text-muted">{fmt.score(k.score)}</span></div>
                <div className="mt-1 h-1 rounded bg-rule"><div className="h-1 rounded bg-navy" style={{ width: `${(k.score / maxScore) * 100}%` }} /></div>
              </li>
            ))}
          </ol>
        )}
        <p className="mt-3 text-xs text-muted">Scores are relative within this meeting and are not comparable between the two methods.</p>
      </Section>
      <Section title="Named entities" aside={`${m.entities.length} distinct, spaCy`}>
        {byLabel.length === 0 ? <p className="text-sm text-muted">spaCy found no named entities.</p> : (
          <div className="space-y-4">
            {byLabel.map(([label, ents]) => (
              <div key={label}>
                <p className="mb-1.5 text-sm font-medium">{label} <span className="font-normal text-muted">{ENTITY_HELP[label] || ""}</span></p>
                <ul className="flex flex-wrap gap-1.5">
                  {ents.map((e) => (
                    <li key={e.text}><Badge tone="navy">{e.text}{e.count > 1 && <span className="ml-1 opacity-70">×{e.count}</span>}</Badge></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
        <p className="mt-4 text-xs text-muted">en_core_web_sm is a small general-purpose model; on spoken transcripts it mislabels some words.</p>
      </Section>
    </div>
  );
}
const ENTITY_HELP = {
  PERSON: "people", ORG: "organisations", GPE: "places", DATE: "dates", TIME: "times", CARDINAL: "numbers",
  MONEY: "money", ORDINAL: "ordinals", NORP: "groups", PRODUCT: "products", LOC: "locations", QUANTITY: "quantities",
  PERCENT: "percentages", EVENT: "events", FAC: "facilities", WORK_OF_ART: "titles", LAW: "laws", LANGUAGE: "languages",
};

// ------------------------------------------------------------ transcript
function Transcript({ m, focus }) {
  const [onlyMarked, setOnlyMarked] = useState(false);
  const marked = useMemo(() => {
    const map = {};
    for (const k of KINDS) for (const r of m.extractions[k.id] || []) (map[r.sentence_index] ||= new Set()).add(k.label);
    return map;
  }, [m.extractions]);
  useEffect(() => {
    if (focus === null) return;
    document.getElementById(`s-${focus}`)?.scrollIntoView({ block: "center" });
  }, [focus]);
  const rows = onlyMarked ? m.sentences.filter((s) => marked[s.idx]) : m.sentences;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          <mark className="hl">Highlighted</mark> sentences matched at least one extraction rule.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyMarked} onChange={(e) => setOnlyMarked(e.target.checked)} />
          Show highlighted only
        </label>
      </div>
      <ol className="rounded border border-rule bg-sheet">
        {rows.map((s) => (
          <li key={s.idx} id={`s-${s.idx}`}
              className={`grid grid-cols-[3rem_4.5rem_minmax(0,1fr)] gap-3 border-b border-rule px-3 py-2 last:border-b-0 ${focus === s.idx ? "bg-navy-soft" : ""}`}>
            <span className="text-right text-xs tabular-nums text-muted pt-1">{s.idx + 1}</span>
            <span className="truncate pt-0.5 text-sm font-medium" title={s.speaker || ""}>{s.speaker || "—"}</span>
            <span className="font-serif text-[16px] leading-relaxed">
              {marked[s.idx] ? <mark className="hl">{s.text}</mark> : s.text}
              {marked[s.idx] && <span className="ml-2 text-xs text-muted">{[...marked[s.idx]].join(", ")}</span>}
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}

// --------------------------------------------------------- reference/ROUGE
function Scores({ m, onSaved }) {
  const [text, setText] = useState(m.reference_summary || "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  async function save(value) {
    setBusy(true);
    setMsg(null);
    try {
      const updated = await api.setReference(m.id, value);
      onSaved(updated);
      setMsg({ tone: "ok", text: value.trim() ? "Reference saved and ROUGE recalculated." : "Reference removed." });
    } catch (e) {
      setMsg({ tone: "error", text: e.message });
    } finally {
      setBusy(false);
    }
  }
  const methods = [["tfidf", "TF-IDF"], ["distilbart", "DistilBART"]];
  return (
    <div className="grid gap-10 lg:grid-cols-2">
      <Section title="ROUGE F1 against the reference">
        {!m.has_reference ? (
          <Empty title="No reference summary">ROUGE needs a human-written summary of this meeting. Add one to score the generated summaries.</Empty>
        ) : (
          <div className="overflow-x-auto rounded border border-rule bg-sheet">
            <table className="table">
              <thead><tr><th>Summary</th><th className="num">ROUGE-1</th><th className="num">ROUGE-2</th><th className="num">ROUGE-L</th></tr></thead>
              <tbody>
                {methods.map(([k, label]) => {
                  const s = m.summaries[k];
                  return (
                    <tr key={k}>
                      <td>{label}</td>
                      {s?.rouge ? ["rouge1", "rouge2", "rougeL"].map((r) => <td key={r} className="num">{fmt.score(s.rouge[r])}</td>) : (
                        <td colSpan={3} className="text-muted">
                          {!s ? "Not generated" : s.status === "fallback" ? "Not scored: DistilBART did not run (fallback text)" : "Not scored"}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {m.source === "sample" && m.has_reference && (
          <p className="mt-3 text-xs text-muted">This is a synthetic sample whose reference was written by the same author. The score only shows that scoring works.</p>
        )}
        <p className="mt-3 text-xs text-muted">ROUGE measures word overlap with one reference, using Porter stemming. Extractive summaries copy transcript words, which favours them on ROUGE-1.</p>
      </Section>
      <Section title="Reference summary">
        <label htmlFor="ref" className="sr-only">Reference summary</label>
        <textarea id="ref" className="field min-h-40 font-serif" value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="Paste a human-written summary of this meeting." />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn" disabled={busy || !text.trim() || text.trim() === (m.reference_summary || "")} onClick={() => save(text)}>
            Save and recalculate
          </button>
          {m.has_reference && <button className="btn-quiet" disabled={busy} onClick={() => { setText(""); save(""); }}>Remove reference</button>}
        </div>
        {msg && <div className="mt-3"><Notice tone={msg.tone}>{msg.text}</Notice></div>}
      </Section>
    </div>
  );
}

// ----------------------------------------------------------------- page
function Progress({ id, onFinished }) {
  const [st, setSt] = useState(null);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const s = await api.status(id);
        if (stop) return;
        setSt(s);
        if (s.status === "done" || s.status === "failed") return onFinished();
      } catch { /* keep polling; the page shows the last known state */ }
      if (!stop) timer = setTimeout(tick, 2000);
    };
    let timer = setTimeout(tick, 800);
    return () => { stop = true; clearTimeout(timer); };
  }, [id, onFinished]);
  return (
    <div className="rounded border border-rule bg-sheet px-5 py-6">
      <Spinner label={st?.stage || "Waiting for the analysis worker"} />
      <p className="mt-2 text-sm text-muted">
        This page updates by itself. The first analysis also loads the models, which can take a minute.
      </p>
    </div>
  );
}

export default function Meeting() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const state = useLoad(() => api.meeting(id), [id]);
  const [override, setOverride] = useState(null);
  const [focus, setFocus] = useState(null);
  const [withBart, setWithBart] = useState(true);
  const [actionError, setActionError] = useState(null);
  const tab = params.get("tab") || "summary";
  const setTab = (t) => setParams(t === "summary" ? {} : { tab: t }, { replace: true });

  useEffect(() => setOverride(null), [state.data]);
  const m = override || state.data;
  useEffect(() => { if (state.data) setWithBart(state.data.options?.abstractive ?? true); }, [state.data]);

  async function rerun() {
    setActionError(null);
    try { await api.reanalyze(id, withBart); state.reload(); } catch (e) { setActionError(e.message); }
  }
  async function remove() {
    try { await api.remove(id); navigate("/meetings"); } catch (e) { setActionError(e.message); }
  }
  const goToSentence = (idx) => { setFocus(idx); setTab("transcript"); };

  return (
    <Loading state={{ ...state, data: m }} label="Loading meeting">
      {() => {
        const running = m.status === "pending" || m.status === "running";
        const counts = KINDS.reduce((n, k) => n + (m.extractions[k.id] || []).length, 0);
        return (
          <>
            <p className="mb-2 text-sm"><Link className="text-muted underline" to="/meetings">Meetings</Link></p>
            <PageHeader
              title={m.title}
              actions={!running && (
                <>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={withBart} onChange={(e) => setWithBart(e.target.checked)} />
                    Include DistilBART
                  </label>
                  <button className="btn-quiet" onClick={rerun}>Re-run analysis</button>
                  <DeleteButton onDelete={remove} />
                </>
              )}
            >
              <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <StatusBadge status={m.status} />
                <Badge tone={m.source === "sample" ? "warn" : "plain"}>{SOURCE[m.source] || m.source}</Badge>
                <span>Meeting #{m.id}</span>
                {m.word_count != null && <span>{fmt.n(m.word_count)} words</span>}
                {m.sentence_count != null && <span>{fmt.n(m.sentence_count)} sentences</span>}
                {m.speaker_count != null && <span>{m.speaker_count} speakers</span>}
                {m.analyzed_at && <span>Analysed {fmt.date(m.analyzed_at)}</span>}
              </span>
            </PageHeader>

            {actionError && <div className="mb-4"><Notice tone="error">{actionError}</Notice></div>}

            {running ? (
              <Progress id={m.id} onFinished={state.reload} />
            ) : m.status === "failed" ? (
              <Notice tone="error" title="Analysis failed" action={<button className="btn-quiet" onClick={rerun}>Re-run analysis</button>}>
                {m.error || "Unknown error. Check the backend log."}
              </Notice>
            ) : (
              <>
                {m.notes?.length > 0 && (
                  <div className="mb-5 space-y-2">
                    {m.notes.map((n, i) => <Notice key={i} tone="warn">{n}</Notice>)}
                  </div>
                )}
                <Tabs label="Meeting analysis" active={tab} onChange={setTab} tabs={[
                  { id: "summary", label: "Summaries" },
                  { id: "items", label: "Candidate items", count: counts },
                  { id: "entities", label: "Entities and keywords" },
                  { id: "transcript", label: "Transcript", count: m.sentences.length },
                  { id: "scores", label: "Reference and ROUGE" },
                ]} />
                <TabPanel id={tab}>
                  {tab === "summary" && <Summaries m={m} />}
                  {tab === "items" && <Items m={m} goToSentence={goToSentence} />}
                  {tab === "entities" && <EntitiesKeywords m={m} />}
                  {tab === "transcript" && <Transcript m={m} focus={focus} />}
                  {tab === "scores" && <Scores m={m} onSaved={setOverride} />}
                </TabPanel>
              </>
            )}
          </>
        );
      }}
    </Loading>
  );
}
