import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api.js";
import { useLoad } from "./components/ui.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Meetings from "./pages/Meetings.jsx";
import Meeting from "./pages/Meeting.jsx";
import Search from "./pages/Search.jsx";
import Evaluation from "./pages/Evaluation.jsx";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/meetings", label: "Meetings" },
  { to: "/search", label: "Search" },
  { to: "/evaluation", label: "Evaluation" },
];

const MODEL_LABELS = { spacy: "spaCy", summarizer: "DistilBART", embedder: "MiniLM", keybert: "KeyBERT" };
const DOT = { loaded: "bg-ok", unavailable: "bg-bad", not_loaded: "bg-rule" };
const STATE_TEXT = { loaded: "loaded", unavailable: "unavailable", not_loaded: "loads on first use" };

function ModelStatus() {
  const health = useLoad(() => api.health(), []);
  if (health.error) return <p className="text-xs text-bad">Backend not reachable.</p>;
  if (!health.data) return null;
  const m = health.data.models;
  const anyFailed = Object.keys(MODEL_LABELS).some((k) => m[k].state === "unavailable");
  return (
    <div className="text-xs text-muted">
      <p className="mb-1.5 font-medium text-ink">Models</p>
      <ul className="space-y-1">
        {Object.entries(MODEL_LABELS).map(([k, label]) => (
          <li key={k} className="flex items-center gap-2" title={m[k].error || m[k].model}>
            <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[m[k].state]}`} aria-hidden />
            <span>{label}</span>
            <span className="ml-auto">{STATE_TEXT[m[k].state]}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1.5">Device: {m.device === "not_resolved" ? "not chosen yet" : m.device}</p>
      <div className="mt-2 flex gap-3">
        <button className="underline hover:text-ink" onClick={health.reload}>Refresh</button>
        {anyFailed && (
          <button className="underline hover:text-ink" onClick={() => api.retryModels().finally(health.reload)}>
            Retry loading
          </button>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-rule bg-sheet md:sticky md:top-0 md:flex md:h-screen md:w-56 md:shrink-0 md:flex-col md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-5 py-4 md:block">
          <p className="text-xl font-semibold tracking-tight">
            <span className="bg-[linear-gradient(transparent_55%,var(--color-marker)_55%)] px-0.5">Scribe</span>
          </p>
          <p className="hidden text-xs text-muted md:mt-1 md:block">Meeting analysis and search</p>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded px-3 py-1.5 text-sm ${
                  isActive ? "bg-navy-soft font-medium text-navy" : "text-ink/80 hover:bg-paper"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden border-t border-rule px-5 py-4 md:block">
          <ModelStatus />
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-6xl">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/meetings" element={<Meetings />} />
            <Route path="/meetings/:id" element={<Meeting />} />
            <Route path="/search" element={<Search />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="*" element={<p className="text-muted">This page does not exist.</p>} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
