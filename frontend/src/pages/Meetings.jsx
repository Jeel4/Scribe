import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import DeleteButton from "../components/DeleteButton.jsx";
import { Badge, Empty, fmt, Loading, Notice, PageHeader, StatusBadge, useLoad } from "../components/ui.jsx";

const SOURCE = { upload: "Upload", sample: "Synthetic sample", ami: "AMI" };

export default function Meetings() {
  const state = useLoad(() => api.meetings(), []);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [error, setError] = useState(null);

  // Keep refreshing while anything is still being analysed.
  const busy = state.data?.meetings.some((m) => m.status === "pending" || m.status === "running");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(state.reload, 2500);
    return () => clearInterval(t);
  }, [busy, state.reload]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (state.data?.meetings || []).filter(
      (m) => (status === "all" || m.status === status) && (!q || m.title.toLowerCase().includes(q))
    );
  }, [state.data, query, status]);

  async function remove(id) {
    setError(null);
    try { await api.remove(id); } catch (e) { setError(e.message); }
    state.reload();
  }
  async function rerun(id) {
    setError(null);
    try { await api.reanalyze(id); } catch (e) { setError(e.message); }
    state.reload();
  }

  return (
    <>
      <PageHeader title="Meetings" actions={<Link className="btn" to="/">Upload a transcript</Link>}>
        Every stored meeting. Deleting one also removes it from search and evaluation.
      </PageHeader>
      <Loading state={state} label="Loading meetings">
        {(data) =>
          data.meetings.length === 0 ? (
            <Empty title="No meetings stored" action={<Link className="btn" to="/">Upload a transcript</Link>}>
              Uploaded transcripts and loaded samples will be listed here.
            </Empty>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap gap-3">
                <label className="sr-only" htmlFor="filter">Filter by title</label>
                <input id="filter" className="field max-w-xs" placeholder="Filter by title" value={query} onChange={(e) => setQuery(e.target.value)} />
                <label className="sr-only" htmlFor="status">Status</label>
                <select id="status" className="field w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
                  <option value="all">All statuses</option>
                  <option value="done">Analysed</option>
                  <option value="running">Analysing</option>
                  <option value="pending">Queued</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
              {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
              {rows.length === 0 ? (
                <Empty title="No meetings match this filter" />
              ) : (
                <div className="overflow-x-auto rounded border border-rule bg-sheet">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Title</th><th>Source</th><th>Status</th>
                        <th className="num">Words</th><th className="num">Speakers</th>
                        <th className="num" title="Candidate action items">Actions</th>
                        <th>Reference</th><th>Added</th><th><span className="sr-only">Manage</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((m) => (
                        <tr key={m.id}>
                          <td className="min-w-48">
                            <Link className="font-medium text-navy hover:underline" to={`/meetings/${m.id}`}>{m.title}</Link>
                            <span className="ml-2 text-xs text-muted">#{m.id}</span>
                            {m.status === "failed" && m.error && <p className="mt-1 text-xs text-bad">{m.error}</p>}
                            {m.status === "running" && m.stage && <p className="mt-1 text-xs text-muted">{m.stage}</p>}
                          </td>
                          <td><Badge tone={m.source === "sample" ? "warn" : "plain"}>{SOURCE[m.source] || m.source}</Badge></td>
                          <td><StatusBadge status={m.status} /></td>
                          <td className="num">{fmt.n(m.word_count)}</td>
                          <td className="num">{fmt.n(m.speaker_count)}</td>
                          <td className="num">{m.status === "done" ? m.extraction_counts.action : "—"}</td>
                          <td>{m.has_reference ? "Yes" : <span className="text-muted">No</span>}</td>
                          <td className="whitespace-nowrap text-muted">{fmt.date(m.created_at)}</td>
                          <td className="whitespace-nowrap text-right">
                            <span className="inline-flex gap-2">
                              {m.status === "failed" && <button className="btn-quiet" onClick={() => rerun(m.id)}>Re-run</button>}
                              <DeleteButton onDelete={() => remove(m.id)} />
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )
        }
      </Loading>
    </>
  );
}
