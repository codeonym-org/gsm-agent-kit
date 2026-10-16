import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ApiClient, ApiError, type Balance, type Device } from "../api/client";
import { useResource } from "../use-resource";
import { Badge, Empty, Feedback, labels, outcomeTone, time } from "./shared";
import { ManualSubmission, SubmissionLookup } from "./submission";

const capabilityLabels: Record<string, string> = {
  "device.status.read": "Device status",
  "sms.inbox.read": "SMS inbox",
  "sms.send": "SMS submission",
  "carrier.balance.read": "Carrier balance",
};

function BalancePanel({
  api,
  deviceId,
  supported,
}: {
  api: ApiClient;
  deviceId: string;
  supported: boolean;
}) {
  const [balance, setBalance] = useState<Balance>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function consult() {
    setBusy(true);
    setError(undefined);
    setBalance(undefined);
    controller.current = new AbortController();
    try {
      setBalance(await api.balance(deviceId, controller.current.signal));
    } catch (failure) {
      if (!controller.current.signal.aborted)
        setError(failure instanceof ApiError ? failure.message : "Balance consultation failed.");
    } finally {
      if (!controller.current.signal.aborted) setBusy(false);
    }
  }
  return (
    <section className="panel balance-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Carrier account</p>
          <h2>Balance</h2>
        </div>
        {supported ? (
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => void consult()}
          >
            {busy ? "Consulting…" : "Consult balance"}
          </button>
        ) : (
          <Badge>Not supported</Badge>
        )}
      </div>
      {!supported && (
        <p className="muted">This device adapter does not offer balance consultation.</p>
      )}
      {supported && !balance && !error && (
        <p className="muted">Consult on demand using the server's configured carrier policy.</p>
      )}
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {balance && (
        <>
          <p className="message-text">{balance.raw_text}</p>
          <dl className="record-meta">
            <div>
              <dt>Credit</dt>
              <dd>
                {balance.credit
                  ? `${balance.credit.amount} ${balance.credit.currency}`
                  : "Not reported"}
              </dd>
            </div>
            <div>
              <dt>SMS allowance</dt>
              <dd>{balance.sms_allowance?.remaining ?? "Not reported"}</dd>
            </div>
          </dl>
          {balance.credit?.conditions && <p className="muted">{balance.credit.conditions}</p>}
          {balance.sms_allowance?.conditions && (
            <p className="muted">{balance.sms_allowance.conditions}</p>
          )}
          <p className="muted small">Observed {time(balance.observed_at)}</p>
        </>
      )}
    </section>
  );
}

function Pagination({
  offset,
  count,
  change,
}: {
  offset: number;
  count: number;
  change: (offset: number) => void;
}) {
  return (
    <div className="pagination">
      <span>{count ? `${offset + 1}–${offset + count}` : "0 records"}</span>
      <div className="actions">
        <button
          type="button"
          className="button ghost"
          disabled={offset === 0}
          onClick={() => change(Math.max(0, offset - 25))}
        >
          Previous
        </button>
        <button
          type="button"
          className="button ghost"
          disabled={count < 25}
          onClick={() => change(offset + 25)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Dashboard({
  api,
  device,
  revision,
  refresh,
}: {
  api: ApiClient;
  device: Device;
  revision: number;
  refresh: () => void;
}) {
  const id = device.device_id;
  const caps = device.adapter.capabilities;
  const inboxSupported = caps.includes("sms.inbox.read");
  const sendSupported = caps.includes("sms.send");
  const [tab, setTab] = useState("inbox");
  const [inboxOffset, setInboxOffset] = useState(0);
  const [jobsOffset, setJobsOffset] = useState(0);
  const [selectedRequest, setSelectedRequest] = useState<string>();
  const [lookup, setLookup] = useState("");
  const reads = useMemo(
    () => ({
      status: (signal: AbortSignal) => api.status(id, signal),
      assistant: (signal: AbortSignal) => api.assistant(id, signal),
      messages: (signal: AbortSignal) => api.messages(id, inboxOffset, signal),
      jobs: (signal: AbortSignal) => api.jobs(id, jobsOffset, signal),
    }),
    [api, id, inboxOffset, jobsOffset],
  );
  const status = useResource(reads.status, revision, caps.includes("device.status.read"));
  const assistant = useResource(reads.assistant, revision);
  const inbox = useResource(reads.messages, revision, inboxSupported);
  const jobs = useResource(reads.jobs, revision, inboxSupported && sendSupported);
  const access = status.error
    ? "unreachable"
    : (status.data?.availability ?? device.observation?.availability ?? "unknown");
  const jobCount = Object.values(assistant.data?.jobs ?? {}).reduce(
    (total, value) => total + value,
    0,
  );
  const refreshAfterSubmit = useCallback(() => refresh(), [refresh]);

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Device workspace</p>
          <h1>{device.adapter.model}</h1>
          <p className="muted">
            {id} <span aria-hidden="true">/</span> {device.adapter.manufacturer}
          </p>
        </div>
        <button className="button secondary" type="button" onClick={refresh}>
          <span aria-hidden="true">↻</span> Refresh
        </button>
      </header>
      <div className="metrics">
        <section className="metric">
          <p>Device access</p>
          <strong className={`access ${access}`}>{access}</strong>
          <span>
            {status.data?.network_provider || "Carrier not observed"}
            {status.data?.network_type ? ` · ${status.data.network_type}` : ""}
          </span>
        </section>
        <section className="metric">
          <p>Signal</p>
          <strong>
            {status.data?.signal_percent != null ? (
              <>
                {status.data.signal_percent}
                <small>%</small>
              </>
            ) : (
              "—"
            )}
          </strong>
          <span>
            {status.data ? `Observed ${time(status.data.observed_at)}` : "No signal observation"}
          </span>
        </section>
        <section className="metric">
          <p>Automatic replies</p>
          <strong>
            {assistant.data ? (assistant.data.auto_reply ? "Enabled" : "Disabled") : "—"}
          </strong>
          <span>
            {assistant.data
              ? assistant.data.dry_run
                ? "Dry run · no automatic SMS"
                : "Live submission mode"
              : "Loading configuration"}
          </span>
        </section>
        <section className="metric">
          <p>Reply jobs</p>
          <strong>{assistant.data ? jobCount : "—"}</strong>
          <span>
            {assistant.data
              ? `${assistant.data.jobs.completed || 0} accepted · ${assistant.data.jobs.interrupted || 0} interrupted`
              : "No workflow observation"}
          </span>
        </section>
      </div>
      <Feedback resource={status} />
      <Feedback resource={assistant} />
      <section className="panel identity">
        <div className="identity-heading">
          <div>
            <p className="eyebrow">Adapter identity</p>
            <strong>
              {device.adapter.adapter_id} <code>v{device.adapter.version}</code>
            </strong>
          </div>
          <Badge tone={device.observation?.compatibility === "verified" ? "success" : "neutral"}>
            {device.observation?.compatibility || "No hardware verification"}
          </Badge>
        </div>
        <section className="capabilities" aria-label="Supported capabilities">
          {caps.length ? (
            caps.map((capability) => (
              <span key={capability} className="capability">
                <span aria-hidden="true">✓</span>
                {capabilityLabels[capability] || capability}
              </span>
            ))
          ) : (
            <span className="muted">No capabilities declared</span>
          )}
        </section>
        <p className="muted small">
          Capabilities describe support. Device access and network observations do not establish SMS
          acceptance or delivery.
        </p>
        {device.observation?.variant && (
          <p className="muted small">
            Firmware: {device.observation.variant.firmware || "unknown"} · Hardware:{" "}
            {device.observation.variant.hardware_revision || "unknown"} · Mode:{" "}
            {device.observation.variant.operating_mode || "unknown"}
          </p>
        )}
        {status.data?.issue && (
          <p className="notice warning">
            Device observation: {status.data.issue.replaceAll("_", " ")}
          </p>
        )}
      </section>
      <div className="workspace-grid">
        <div className="main-column">
          <section className="panel activity">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Message activity</p>
                <h2>SMS workspace</h2>
              </div>
              <span className="section-number">01</span>
            </div>
            <nav className="tabs" aria-label="Activity views">
              <button type="button" aria-pressed={tab === "inbox"} onClick={() => setTab("inbox")}>
                Inbox
              </button>
              <button type="button" aria-pressed={tab === "jobs"} onClick={() => setTab("jobs")}>
                Reply jobs
              </button>
            </nav>
            {tab === "inbox" ? (
              !inboxSupported ? (
                <Empty title="SMS inbox not supported">
                  This cellular device does not declare an incoming SMS capability.
                </Empty>
              ) : (
                <>
                  <Feedback resource={inbox} />
                  {inbox.data?.length === 0 && (
                    <Empty title="No stored messages">
                      Messages appear after the server ingests the device inbox.
                    </Empty>
                  )}
                  <div className="message-list">
                    {inbox.data?.map((message) => (
                      <article className="message" key={message.id}>
                        <div className="message-heading">
                          <strong>{message.sender.value}</strong>
                          <time dateTime={message.observed_at}>{time(message.observed_at)}</time>
                        </div>
                        <p className="message-text">{message.body}</p>
                        <div className="message-tags">
                          {!message.complete && <Badge tone="warning">Incomplete</Badge>}
                          {message.baselined && <Badge>Existing at baseline</Badge>}
                          {message.subscription_uncertain && (
                            <Badge tone="warning">SIM attribution uncertain</Badge>
                          )}
                          {message.replyable && <Badge tone="success">Eligible for reply</Badge>}
                        </div>
                      </article>
                    ))}
                  </div>
                  {inbox.data && (
                    <Pagination
                      offset={inboxOffset}
                      count={inbox.data.length}
                      change={setInboxOffset}
                    />
                  )}
                </>
              )
            ) : !inboxSupported || !sendSupported ? (
              <Empty title="SMS replies not supported">
                Automatic SMS replies need both inbox and submission capabilities.
              </Empty>
            ) : (
              <>
                <Feedback resource={jobs} />
                {jobs.data?.length === 0 && (
                  <Empty title="No reply jobs">
                    Eligible incoming messages create jobs when automatic replies are enabled.
                  </Empty>
                )}
                <div className="job-list">
                  {jobs.data?.map((job) => (
                    <article className="job" key={job.record_id}>
                      <div>
                        <Badge tone={outcomeTone(job.state)}>
                          {labels[job.state] || job.state}
                        </Badge>
                        <p className="muted small">
                          {time(job.created_at)}
                          {job.issue ? ` · ${job.issue.replaceAll("_", " ")}` : ""}
                        </p>
                        <code className="request-id">{job.request_id}</code>
                      </div>
                      {["submitting", "completed", "interrupted"].includes(job.state) && (
                        <button
                          type="button"
                          className="button secondary"
                          onClick={() => setSelectedRequest(job.request_id)}
                        >
                          View submission
                        </button>
                      )}
                    </article>
                  ))}
                </div>
                {jobs.data && (
                  <Pagination offset={jobsOffset} count={jobs.data.length} change={setJobsOffset} />
                )}
              </>
            )}
          </section>
          {selectedRequest && (
            <SubmissionLookup
              key={selectedRequest}
              api={api}
              deviceId={id}
              requestId={selectedRequest}
              close={() => setSelectedRequest(undefined)}
            />
          )}
          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Existing request</p>
                <h2>Find submission progress</h2>
              </div>
            </div>
            <form
              className="lookup"
              onSubmit={(event) => {
                event.preventDefault();
                setSelectedRequest(lookup);
              }}
            >
              <label className="sr-only" htmlFor="lookup">
                Submission request ID
              </label>
              <input
                id="lookup"
                value={lookup}
                placeholder="Paste a submission request UUID"
                pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                onChange={(event) => setLookup(event.target.value)}
                required
              />
              <button className="button secondary" type="submit" disabled={!sendSupported}>
                Look up
              </button>
            </form>
          </section>
        </div>
        <aside className="side-column">
          <section className="panel assistant-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Assistant policy</p>
                <h2>Reply mode</h2>
              </div>
              <span className="section-number">02</span>
            </div>
            {assistant.data ? (
              <>
                <Badge
                  tone={
                    assistant.data.auto_reply
                      ? assistant.data.dry_run
                        ? "warning"
                        : "success"
                      : "neutral"
                  }
                >
                  {!assistant.data.auto_reply
                    ? "Auto-reply disabled"
                    : assistant.data.dry_run
                      ? "Dry run"
                      : "Live replies"}
                </Badge>
                <p className="muted">
                  {!assistant.data.auto_reply
                    ? "Incoming messages will not trigger automatic replies."
                    : assistant.data.dry_run
                      ? "The assistant prepares replies without submitting SMS."
                      : "Eligible incoming messages can trigger real SMS submissions."}
                </p>
                <p className="muted small">Reply mode is managed by the server configuration.</p>
              </>
            ) : (
              <Feedback resource={assistant} />
            )}
          </section>
          {sendSupported ? (
            <ManualSubmission api={api} deviceId={id} onSubmitted={refreshAfterSubmit} />
          ) : (
            <section className="panel">
              <Empty title="SMS submission not supported">
                This device does not declare an outgoing SMS capability.
              </Empty>
            </section>
          )}
          <BalancePanel api={api} deviceId={id} supported={caps.includes("carrier.balance.read")} />
        </aside>
      </div>
      <footer className="workspace-footer">
        <span>
          <span className="live-dot" /> Observations refresh every 5 seconds
        </span>
        <span>One logical device · explicit capabilities</span>
      </footer>
    </>
  );
}
