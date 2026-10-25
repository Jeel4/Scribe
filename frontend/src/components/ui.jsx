import { useCallback, useEffect, useRef, useState } from "react";

/** Load data on mount (and when deps change); exposes loading/error/reload. */
export function useLoad(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const alive = useRef(true);
  const run = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    return loader()
      .then((data) => alive.current && setState({ data, error: null, loading: false }))
      .catch((error) => alive.current && setState({ data: null, error, loading: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    alive.current = true;
    run();
    return () => { alive.current = false; };
  }, [run]);
  return { ...state, reload: run };
}

const STATUS = {
  done: ["Analysed", "bg-ok-soft text-ok"],
  running: ["Analysing", "bg-navy-soft text-navy"],
  pending: ["Queued", "bg-navy-soft text-navy"],
  failed: ["Failed", "bg-bad-soft text-bad"],
  ok: ["Model output", "bg-ok-soft text-ok"],
  fallback: ["Fallback — not DistilBART", "bg-warn-soft text-warn"],
  skipped: ["Skipped", "bg-paper text-muted"],
};

export function Badge({ tone = "plain", children, title }) {
  const tones = {
    plain: "bg-paper text-muted border border-rule",
    navy: "bg-navy-soft text-navy",
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    bad: "bg-bad-soft text-bad",
    marker: "bg-marker-soft text-ink",
  };
  return (
    <span title={title} className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const [label, cls] = STATUS[status] || [status, "bg-paper text-muted"];
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}>{label}</span>;
}

export function Notice({ tone = "info", title, children, action }) {
  const tones = {
    info: "border-navy/30 bg-navy-soft/60",
    warn: "border-warn/40 bg-warn-soft",
    error: "border-bad/40 bg-bad-soft",
    ok: "border-ok/40 bg-ok-soft",
  };
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded border-l-4 px-4 py-3 text-sm ${tones[tone]}`}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={title ? "mt-1 text-ink/85" : ""}>{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-rule border-t-navy" aria-hidden />
      {label}
    </span>
  );
}

export function Loading({ state, children, label }) {
  if (state.loading && !state.data) return <div className="py-10"><Spinner label={label} /></div>;
  if (state.error) {
    return (
      <Notice tone="error" title="Could not load this page" action={<button className="btn-quiet" onClick={state.reload}>Try again</button>}>
        {state.error.message}
      </Notice>
    );
  }
  return children(state.data);
}

export function Empty({ title, children, action }) {
  return (
    <div className="rounded border border-dashed border-rule bg-sheet px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, children, actions }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-rule pb-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Section({ title, aside, children, className = "" }) {
  return (
    <section className={`mb-8 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        {aside && <div className="text-sm text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

/** Accessible tabs (arrow keys move between tabs). */
export function Tabs({ tabs, active, onChange, label }) {
  const refs = useRef({});
  const onKey = (e, i) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    onChange(next.id);
    refs.current[next.id]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-rule">
      {tabs.map((t, i) => {
        const on = t.id === active;
        return (
          <button
            key={t.id}
            ref={(el) => (refs.current[t.id] = el)}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={on}
            aria-controls={`panel-${t.id}`}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              on ? "border-navy text-navy" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.count !== undefined && <span className="ml-1.5 text-xs tabular-nums text-muted">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, children }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="pt-5">
      {children}
    </div>
  );
}

export const fmt = {
  n: (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString()),
  score: (v, d = 3) => (v === null || v === undefined ? "—" : Number(v).toFixed(d)),
  pct: (v) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`),
  date: (s) => {
    if (!s) return "—";
    const d = new Date(s.replace(" ", "T") + "Z");
    return isNaN(d) ? s : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  },
};
