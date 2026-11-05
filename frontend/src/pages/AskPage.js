import { useState } from "react";
import { api } from "../api/client";

// V3 assistant: quotes the project documentation with citations. It never computes
// routes, travel times or traffic; those stay on the Navigate and Traffic pages.
const EXAMPLES = [
  "What is a shortcut in Pulse?",
  "How are community shortcuts verified?",
  "When is a traffic reading considered stale?",
  "Does weather change the ETA?",
];

function Source({ citation }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(null);
  const [error, setError] = useState(null);

  async function toggle() {
    setOpen(!open);
    if (!open && text === null) {
      try {
        const src = await api(`/v1/assistant/sources/${citation.chunk_id}`);
        setText(src.text);
      } catch (err) {
        setError(err.message);
      }
    }
  }

  return (
    <li className="ask-source">
      <button type="button" className="link-btn" onClick={toggle} aria-expanded={open}>
        [{citation.n}] {citation.title} › {citation.heading}
      </button>
      <span className="muted small">
        {" "}
        {citation.source_ref}
        {citation.measured_on ? ` · documented ${citation.measured_on}` : ""}
      </span>
      {open && (error ? <div className="error-box">{error}</div> : <pre className="ask-passage">{text ?? "Loading…"}</pre>)}
    </li>
  );
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function submit(e, text) {
    if (e) e.preventDefault();
    const q = (text ?? question).trim();
    if (!q) return;
    setQuestion(q);
    setBusy(true);
    setError(null);
    try {
      setResult(await api("/v1/assistant/ask", { method: "POST", body: { question: q } }));
    } catch (err) {
      setResult(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">Assistant · documentation answers</p>
        <h2 className="page-title">Ask Pulse</h2>
        <p className="page-lede">
          Ask how Bengaluru Pulse works: routes, shortcuts, traffic data, forecasts, accounts. Answers quote the project
          documentation with sources. For live routes and traffic use Navigate and Traffic.
        </p>
      </header>

      <section className="panel">
        <form className="stack-form" onSubmit={submit}>
          <label>
            Your question
            <textarea
              rows={2}
              maxLength={500}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How are community shortcuts verified?"
            />
          </label>
          <button className="primary" disabled={busy || !question.trim()}>
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? "Searching…" : "Ask"}
          </button>
        </form>
        <div className="ask-examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" className="ghost-btn" disabled={busy} onClick={() => submit(null, ex)}>
              {ex}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}

      {result && (
        <section className="panel" aria-live="polite">
          {result.refused ? (
            <div className="ask-refusal" data-code={result.refusal_code}>
              <p>{result.answer}</p>
            </div>
          ) : (
            <div className="ask-answer">
              {result.answer.split("\n").map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          )}
          {result.citations && result.citations.length > 0 && (
            <>
              <h3 className="small">Sources</h3>
              <ol className="ask-sources">
                {result.citations.map((c) => (
                  <Source key={c.chunk_id} citation={c} />
                ))}
              </ol>
            </>
          )}
          <p className="muted small">{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
