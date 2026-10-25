import { useState } from "react";

/** Two-step delete: first click asks, second click confirms. */
export default function DeleteButton({ onDelete, label = "Delete" }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!asking) {
    return <button type="button" className="btn-quiet btn-danger" onClick={() => setAsking(true)}>{label}</button>;
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-sm">Delete permanently?</span>
      <button
        type="button"
        className="btn-quiet btn-danger"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try { await onDelete(); } finally { setBusy(false); setAsking(false); }
        }}
      >
        {busy ? "Deleting…" : "Yes, delete"}
      </button>
      <button type="button" className="btn-quiet" onClick={() => setAsking(false)}>Cancel</button>
    </span>
  );
}
