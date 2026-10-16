import { useCallback, useEffect, useRef, useState } from "react";
import { type ApiClient, ApiError, type Submission } from "../api/client";
import { useResource } from "../use-resource";
import { Badge, Feedback, labels, outcomeTone, time } from "./shared";

export function SubmissionProgress({ record }: { record: Submission }) {
  return (
    <section className="submission-progress" aria-label="Submission progress">
      <div className="progress-heading">
        <Badge tone={record.complete ? "success" : record.blocked ? "warning" : "neutral"}>
          {record.complete
            ? "Accepted for submission"
            : record.blocked
              ? "Submission stopped"
              : "Submission pending"}
        </Badge>
        <span>
          {record.accepted_parts} / {record.parts.length} parts accepted
        </span>
      </div>
      <p className="muted">Acceptance does not confirm recipient delivery.</p>
      {record.truncated && (
        <p className="notice">
          The server shortened this message to fit the configured SMS budget.
        </p>
      )}
      <dl className="record-meta">
        <div>
          <dt>To</dt>
          <dd>{record.destination}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{time(record.created_at)}</dd>
        </div>
      </dl>
      {record.parts.map((part) => (
        <article className="part" key={part.message_id}>
          <div className="part-heading">
            <strong>Part {part.index + 1}</strong>
            <Badge tone={outcomeTone(part.state)}>{labels[part.state] || part.state}</Badge>
          </div>
          <p className="message-text">{part.text}</p>
          {part.attempts.map((attempt) => (
            <p className="muted small" key={attempt.id}>
              Attempt:{" "}
              {attempt.outcome ? labels[attempt.outcome] || attempt.outcome : "In progress"}
              {attempt.reason ? ` · ${attempt.reason.replaceAll("_", " ")}` : ""}
            </p>
          ))}
        </article>
      ))}
      {record.parts.some((part) => part.state === "unknown" || part.state === "in_progress") && (
        <p className="notice warning">
          An outcome is uncertain. Check existing progress; this console will not resend it.
        </p>
      )}
    </section>
  );
}

export function SubmissionLookup({
  api,
  deviceId,
  requestId,
  close,
}: {
  api: ApiClient;
  deviceId: string;
  requestId: string;
  close: () => void;
}) {
  const load = useCallback(
    (signal: AbortSignal) => api.submission(deviceId, requestId, signal),
    [api, deviceId, requestId],
  );
  const progress = useResource(load, 0);
  return (
    <section className="panel" aria-label="Selected submission">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Submission record</p>
          <h2>Request progress</h2>
        </div>
        <button type="button" className="button ghost" onClick={close}>
          Close
        </button>
      </div>
      <code className="request-id">{requestId}</code>
      <Feedback resource={progress} />
      {progress.data && <SubmissionProgress record={progress.data} />}
    </section>
  );
}

export function ManualSubmission({
  api,
  deviceId,
  onSubmitted,
}: {
  api: ApiClient;
  deviceId: string;
  onSubmitted: () => void;
}) {
  const [destination, setDestination] = useState("");
  const [text, setText] = useState("");
  const [requestId, setRequestId] = useState<string>();
  const [record, setRecord] = useState<Submission>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function send() {
    const id = crypto.randomUUID();
    setRequestId(id);
    setBusy(true);
    setError(undefined);
    controller.current = new AbortController();
    try {
      setRecord(
        await api.send(deviceId, { request_id: id, destination, text }, controller.current.signal),
      );
      onSubmitted();
    } catch (failure) {
      if (!controller.current.signal.aborted)
        setError(
          failure instanceof ApiError ? failure.message : "The submission response is unavailable.",
        );
    } finally {
      if (!controller.current.signal.aborted) setBusy(false);
    }
  }

  async function check() {
    if (!requestId) return;
    setBusy(true);
    setError(undefined);
    controller.current = new AbortController();
    try {
      setRecord(await api.submission(deviceId, requestId, controller.current.signal));
    } catch (failure) {
      if (!controller.current.signal.aborted)
        setError(failure instanceof ApiError ? failure.message : "Unable to check progress.");
    } finally {
      if (!controller.current.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="panel composer">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Outgoing SMS</p>
          <h2>Manual submission</h2>
        </div>
        <span className="section-number">03</span>
      </div>
      {!requestId ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <p className="muted">
            Submit an SMS directly. Assistant dry-run settings apply only to automatic replies.
          </p>
          <label htmlFor="destination">Destination</label>
          <input
            id="destination"
            type="tel"
            placeholder="+212…"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            pattern="\+[1-9][0-9]{2,14}"
            required
            autoComplete="off"
          />
          <label htmlFor="sms-text">Message</label>
          <textarea
            id="sms-text"
            rows={6}
            placeholder="Write a message…"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={10000}
            required
          />
          <div className="composer-meta">
            <span>{text.length.toLocaleString()} characters</span>
            <span>Server SMS limits apply</span>
          </div>
          <button
            className="button primary wide"
            type="submit"
            disabled={!text.trim() || !destination}
          >
            Submit SMS <span aria-hidden="true">↗</span>
          </button>
        </form>
      ) : (
        <>
          <label htmlFor="manual-request-id">Request ID — keep this to find progress later</label>
          <input id="manual-request-id" readOnly value={requestId} />
          {busy && (
            <p role="status" className="notice">
              Waiting for submission progress…
            </p>
          )}
          {error && (
            <div role="alert" className="notice error">
              {error} A request ID has been allocated. Check its progress before creating another
              submission.
            </div>
          )}
          {record && <SubmissionProgress record={record} />}
          <div className="actions">
            <button
              className="button secondary"
              type="button"
              disabled={busy}
              onClick={() => void check()}
            >
              Check progress
            </button>
            <button
              className="button ghost"
              type="button"
              disabled={busy}
              onClick={() => {
                setRequestId(undefined);
                setRecord(undefined);
                setError(undefined);
                setText("");
              }}
            >
              New draft
            </button>
          </div>
        </>
      )}
    </section>
  );
}
