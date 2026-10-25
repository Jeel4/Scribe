import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Notice } from "./ui.jsx";

export default function UploadForm({ maxMb = 2 }) {
  const navigate = useNavigate();
  const input = useRef(null);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [abstractive, setAbstractive] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  function choose(f) {
    setError(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".txt")) return setError("Choose a .txt file. Other formats are not supported.");
    if (f.size === 0) return setError("That file is empty.");
    if (f.size > maxMb * 1024 * 1024) return setError(`That file is larger than ${maxMb} MB.`);
    setFile(f);
  }

  async function submit(e) {
    e.preventDefault();
    if (!file) return setError("Choose a transcript first.");
    const fd = new FormData();
    fd.append("file", file);
    if (title.trim()) fd.append("title", title.trim());
    if (reference.trim()) fd.append("reference_summary", reference.trim());
    fd.append("abstractive", abstractive ? "true" : "false");
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.upload(fd);
      navigate(`/meetings/${id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded border border-rule bg-sheet p-5" noValidate>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); choose(e.dataTransfer.files?.[0]); }}
        className={`rounded border-2 border-dashed px-4 py-6 text-center ${dragging ? "border-navy bg-navy-soft/50" : "border-rule"}`}
      >
        <input ref={input} id="transcript" type="file" accept=".txt,text/plain" className="sr-only"
               onChange={(e) => choose(e.target.files?.[0])} />
        {file ? (
          <p className="text-sm">
            <span className="font-medium">{file.name}</span>{" "}
            <span className="text-muted">({(file.size / 1024).toFixed(1)} KB)</span>{" "}
            <button type="button" className="ml-2 text-navy underline" onClick={() => input.current?.click()}>Change</button>
          </p>
        ) : (
          <>
            <p className="text-sm">Drop a transcript here, or{" "}
              <button type="button" className="font-medium text-navy underline" onClick={() => input.current?.click()}>choose a file</button>
            </p>
            <p className="mt-1 text-xs text-muted">Plain text (.txt, UTF-8), up to {maxMb} MB. Speaker lines like “Maya: …” or “[A] …” are recognised.</p>
          </>
        )}
      </div>

      <div>
        <label htmlFor="title" className="mb-1 block text-sm font-medium">Title <span className="font-normal text-muted">(optional)</span></label>
        <input id="title" className="field" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)}
               placeholder="Defaults to the file name" />
      </div>

      <div>
        <label htmlFor="reference" className="mb-1 block text-sm font-medium">Reference summary <span className="font-normal text-muted">(optional)</span></label>
        <textarea id="reference" className="field min-h-20" value={reference} onChange={(e) => setReference(e.target.value)}
                  placeholder="A human-written summary of this meeting. Only used to compute ROUGE." />
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={abstractive} onChange={(e) => setAbstractive(e.target.checked)} />
        <span>
          Also generate a DistilBART summary
          <span className="block text-xs text-muted">Slow on CPU (often 20–60 seconds for a long meeting). The TF-IDF summary is always produced.</span>
        </span>
      </label>

      {error && <Notice tone="error">{error}</Notice>}
      <button className="btn" disabled={busy || !file}>{busy ? "Uploading…" : "Upload and analyse"}</button>
    </form>
  );
}
