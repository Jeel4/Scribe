import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import UploadForm from "../components/UploadForm.jsx";
import { Empty, fmt, Loading, Notice, PageHeader, Section, StatusBadge, useLoad } from "../components/ui.jsx";

const KIND_LABELS = { action: "Action items", decision: "Decisions", risk: "Risks", question: "Open questions", deadline: "Deadlines" };

function Samples() {
  const navigate = useNavigate();
  const samples = useLoad(() => api.samples(), []);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  if (!samples.data?.samples?.length) return null;
  async function load(name) {
    setBusy(name);
    setError(null);
    try {
      const { id } = await api.loadSample(name, false);
      navigate(`/meetings/${id}`);
    } catch (e) {
      setError(e.message);
      setBusy(null);
    }
  }
  return (
    <div className="mt-4 text-sm">
      <p className="text-muted">
        No transcript to hand? Load a synthetic sample. These were written for this demo and are not real meetings.
      </p>
      <ul className="mt-2 space-y-1">
        {samples.data.samples.map((s) => (
          <li key={s.name} className="flex flex-wrap items-center gap-2">
            <button className="text-navy underline disabled:opacity-50" disabled={!!busy} onClick={() => load(s.name)}>
              {s.name.replace("synthetic_", "").replace(".txt", "").replaceAll("_", " ")}
            </button>
            <span className="text-xs text-muted">{s.words} words{s.has_reference ? ", has a reference summary" : ""}</span>
            {busy === s.name && <span className="text-xs text-muted">Loading…</span>}
          </li>
        ))}
      </ul>
      {error && <div className="mt-2"><Notice tone="error">{error}</Notice></div>}
    </div>
  );
}

function Figures({ d }) {
  const items = [
    ["Meetings analysed", d.meetings.done],
    ["Words analysed", d.analysed_words],
    ["Sentences searchable", d.index.indexed_sentences],
    ["With embeddings", d.index.embedded_sentences],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-y border-rule py-4 sm:grid-cols-4">
      {items.map(([label, v]) => (
        <div key={label}>
          <dt className="text-sm text-muted">{label}</dt>
          <dd className="text-2xl font-semibold tabular-nums">{fmt.n(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function Dashboard() {
  const state = useLoad(() => Promise.all([api.dashboard(), api.health()]), []);
  return (
    <>
      <PageHeader title="Dashboard">Upload a transcript to summarise it, pull out candidate action items and make it searchable.</PageHeader>
      <Loading state={state} label="Loading dashboard">
        {([d, health]) => (
          <div className="grid gap-10 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
            <div>
              <Section title="New meeting">
                <UploadForm maxMb={health.limits.max_upload_mb} />
                <Samples />
              </Section>
            </div>
            <div className="min-w-0">
              <Figures d={d} />
              {d.meetings.failed > 0 && (
                <div className="mt-4">
                  <Notice tone="warn">
                    {d.meetings.failed} meeting{d.meetings.failed > 1 ? "s" : ""} failed to analyse.{" "}
                    <Link to="/meetings" className="underline">Open the meeting list</Link> to see why or re-run them.
                  </Notice>
                </div>
              )}

              <Section title="Recent meetings" className="mt-8" aside={d.meetings.total > 0 && <Link className="underline" to="/meetings">All meetings</Link>}>
                {d.recent.length === 0 ? (
                  <Empty title="No meetings yet">Upload a transcript or load a sample to get started.</Empty>
                ) : (
                  <div className="overflow-x-auto rounded border border-rule bg-sheet">
                    <table className="table">
                      <thead><tr><th>Title</th><th>Status</th><th className="num">Words</th><th>Added</th></tr></thead>
                      <tbody>
                        {d.recent.map((m) => (
                          <tr key={m.id}>
                            <td><Link className="font-medium text-navy hover:underline" to={`/meetings/${m.id}`}>{m.title}</Link></td>
                            <td><StatusBadge status={m.status} /></td>
                            <td className="num">{fmt.n(m.word_count)}</td>
                            <td className="whitespace-nowrap text-muted">{fmt.date(m.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section title="Extracted across all meetings" aside="Rule-based candidates, not verified">
                <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                  {Object.entries(KIND_LABELS).map(([k, label]) => (
                    <li key={k}><span className="font-semibold tabular-nums">{fmt.n(d.extraction_totals[k])}</span> <span className="text-muted">{label.toLowerCase()}</span></li>
                  ))}
                </ul>
              </Section>

              {d.recent_actions.length > 0 && (
                <Section title="Latest candidate action items">
                  <ul className="divide-y divide-rule rounded border border-rule bg-sheet">
                    {d.recent_actions.map((a, i) => (
                      <li key={i} className="px-4 py-2.5 text-sm">
                        <p>{a.text}</p>
                        <p className="mt-0.5 text-xs text-muted">
                          <Link className="underline" to={`/meetings/${a.meeting_id}?tab=items`}>{a.meeting_title}</Link>
                          {a.owner && <span className="ml-3">Owner: {a.owner}</span>}
                          {a.deadline && <span className="ml-3">Due: {a.deadline}</span>}
                        </p>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          </div>
        )}
      </Loading>
    </>
  );
}
