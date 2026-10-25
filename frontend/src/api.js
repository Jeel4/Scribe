// Thin wrapper around fetch: every backend error arrives as {error: "..."}
// and is thrown as an Error with that readable message.
async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("Cannot reach the Scribe backend. Is it running on port 5000?");
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON (e.g. proxy error page) */
  }
  if (!res.ok) {
    const msg = body?.error || `Request failed (${res.status}).`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return body;
}

const json = (method, data) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data ?? {}),
});

export const api = {
  health: () => request("/health"),
  dashboard: () => request("/dashboard"),
  meetings: () => request("/meetings"),
  meeting: (id) => request(`/meetings/${id}`),
  status: (id) => request(`/meetings/${id}/status`),
  upload: (formData) => request("/meetings", { method: "POST", body: formData }),
  remove: (id) => request(`/meetings/${id}`, { method: "DELETE" }),
  reanalyze: (id, abstractive) => request(`/meetings/${id}/analyze`, json("POST", { abstractive })),
  setReference: (id, text) => request(`/meetings/${id}/reference`, json("PUT", { reference_summary: text })),
  samples: () => request("/samples"),
  loadSample: (name, abstractive) => request(`/samples/${encodeURIComponent(name)}`, json("POST", { abstractive })),
  search: (params) => request(`/search?${new URLSearchParams(params)}`),
  evaluation: () => request("/evaluation"),
  evaluateRetrieval: (payload) => request("/evaluation/retrieval", json("POST", payload)),
  retryModels: () => request("/models/retry", { method: "POST" }),
};
