import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  ChevronRight,
  Cpu,
  Filter,
  MessageSquare,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Signal,
  Sparkles,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { type ApiClient, ApiError, type Balance, type Device } from "../api/client";
import { useResource } from "../use-resource";
import { Badge, Empty, Feedback, labels, outcomeTone, time } from "./shared";
import { ManualSubmission, SubmissionLookup } from "./submission";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Input } from "./ui/input";

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
          <Button type="button" variant="outline" disabled={busy} onClick={() => void consult()}>
            {busy ? "Consulting…" : "Consult balance"}
          </Button>
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
        <Button
          type="button"
          variant="ghost"
          disabled={offset === 0}
          onClick={() => change(Math.max(0, offset - 25))}
        >
          Previous
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={count < 25}
          onClick={() => change(offset + 25)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

export function Dashboard({
  api,
  device,
  revision,
  refresh,
  view,
}: {
  api: ApiClient;
  device: Device;
  revision: number;
  refresh: () => void;
  view: string;
}) {
  const id = device.device_id;
  const caps = device.adapter.capabilities;
  const inboxSupported = caps.includes("sms.inbox.read");
  const sendSupported = caps.includes("sms.send");
  const [inboxOffset, setInboxOffset] = useState(0);
  const [jobsOffset, setJobsOffset] = useState(0);
  const [selectedRequest, setSelectedRequest] = useState<string>();
  const [selectedMessage, setSelectedMessage] = useState<string>();
  const [search, setSearch] = useState("");
  const [lookup, setLookup] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const reads = useMemo(
    () => ({
      status: (signal: AbortSignal) => api.status(id, signal),
      assistant: (signal: AbortSignal) => api.assistant(id, signal),
      messages: (signal: AbortSignal) => api.messages(id, inboxOffset, signal),
      jobs: (signal: AbortSignal) => api.jobs(id, jobsOffset, signal),
    }),
    [api, id, inboxOffset, jobsOffset],
  );
  const status = useResource(reads.status, revision, caps.includes("device.status.read"), 30_000);
  const assistant = useResource(reads.assistant, revision, true, 0);
  const inbox = useResource(reads.messages, revision, inboxSupported, 0);
  const jobs = useResource(reads.jobs, revision, inboxSupported && sendSupported, 0);
  const access = status.error
    ? "unreachable"
    : (status.data?.availability ?? device.observation?.availability ?? "unknown");
  const jobCount = Object.values(assistant.data?.jobs ?? {}).reduce(
    (total, value) => total + value,
    0,
  );
  const refreshAfterSubmit = useCallback(() => refresh(), [refresh]);
  const overview = view === "/overview";
  const inboxView = view === "/inbox";
  const jobsView = view === "/jobs";
  const deviceView = view === "/device";
  const filtered =
    inbox.data?.filter((message) =>
      `${message.sender.value} ${message.body}`.toLowerCase().includes(search.toLowerCase()),
    ) || [];
  const selected = inbox.data?.find((message) => message.id === selectedMessage);
  const mode = !assistant.data?.auto_reply
    ? "Auto-reply disabled"
    : assistant.data.dry_run
      ? "Dry run"
      : "Live replies";

  const policy = (
    <section className="panel assistant-panel">
      <div className="panel-heading">
        <div className="icon-heading">
          <span className="icon-tile violet">
            <Bot size={18} />
          </span>
          <h2>AI assistant</h2>
        </div>
        <Badge tone={assistant.data?.auto_reply ? "success" : "neutral"}>{mode}</Badge>
      </div>
      <p className="muted">
        {!assistant.data?.auto_reply
          ? "Automatic replies are disabled for this workspace."
          : assistant.data.dry_run
            ? "Replies are prepared for review without submitting SMS."
            : "Responding to eligible incoming messages automatically."}
      </p>
      <div className="assistant-flow">
        <span>
          <MessageSquare size={15} /> Receive
        </span>
        <ChevronRight size={13} />
        <span>
          <Sparkles size={15} /> Reason
        </span>
        <ChevronRight size={13} />
        <span>
          <Send size={15} /> Reply
        </span>
      </div>
      <div className="policy-foot">
        <ShieldCheck size={14} /> Policy managed by your server configuration
      </div>
    </section>
  );
  const identity = (
    <section className="panel identity">
      <div className="panel-heading">
        <div className="icon-heading">
          <span className="icon-tile">
            <Cpu size={18} />
          </span>
          <h2>Device details</h2>
        </div>
        <Badge>{device.observation?.compatibility || "No hardware verification"}</Badge>
      </div>
      <dl className="device-facts">
        <div>
          <dt>Logical device</dt>
          <dd>{id}</dd>
        </div>
        <div>
          <dt>Manufacturer</dt>
          <dd>{device.adapter.manufacturer}</dd>
        </div>
        <div>
          <dt>Adapter</dt>
          <dd>{device.adapter.adapter_id}</dd>
        </div>
        <div>
          <dt>Build version</dt>
          <dd>
            <code>v{device.adapter.version}</code>
          </dd>
        </div>
        {device.observation?.variant && (
          <>
            <div>
              <dt>Firmware</dt>
              <dd>{device.observation.variant.firmware || "Unknown"}</dd>
            </div>
            <div>
              <dt>Hardware revision</dt>
              <dd>{device.observation.variant.hardware_revision || "Unknown"}</dd>
            </div>
            <div>
              <dt>Operating mode</dt>
              <dd>{device.observation.variant.operating_mode || "Unknown"}</dd>
            </div>
          </>
        )}
      </dl>
      <div className="capability-heading">SUPPORTED CAPABILITIES</div>
      <section className="capabilities" aria-label="Supported capabilities">
        {caps.map((capability) => (
          <span key={capability} className="capability">
            <Check size={13} />
            {capabilityLabels[capability] || capability}
          </span>
        ))}
      </section>
      <p className="muted small">
        Support describes the adapter contract. Current availability is observed separately.
      </p>
      {status.data?.issue && (
        <p className="notice warning">
          Device observation: {status.data.issue.replaceAll("_", " ")}
        </p>
      )}
    </section>
  );
  const messages = (
    <section className="panel activity">
      <div className="panel-heading">
        <div>
          <h2>{overview ? "Recent messages" : "Message inbox"}</h2>
          <p className="muted small">
            {overview
              ? "The latest SMS received by this device."
              : "Messages committed to the device inbox ledger."}
          </p>
        </div>
        {overview ? (
          <Link className="text-link" to="/inbox">
            View inbox <ArrowUpRight size={14} />
          </Link>
        ) : (
          <Badge>{inbox.data?.length ?? "—"} on this page</Badge>
        )}
      </div>
      {inboxView && (
        <div className="table-toolbar">
          <div className="search-input">
            <Search size={16} />
            <Input
              aria-label="Search messages on this page"
              placeholder="Search sender or message on this page…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <span className="muted small">
            <Filter size={14} /> All messages
          </span>
        </div>
      )}
      {!inboxSupported ? (
        <Empty title="SMS inbox not supported">
          This cellular device does not declare an incoming SMS capability.
        </Empty>
      ) : (
        <>
          <Feedback resource={inbox} />
          {inbox.data?.length === 0 && (
            <Empty title="No stored messages">
              Incoming messages will appear here after the server ingests the device inbox.
            </Empty>
          )}
          {inbox.data && inbox.data.length > 0 && filtered.length === 0 && (
            <Empty title="No matching messages">
              Try another sender or phrase. Search applies to this page.
            </Empty>
          )}
          <div className="table-scroll">
            <table className="data-table message-table">
              <thead>
                <tr>
                  <th>Sender & message</th>
                  <th>State</th>
                  <th className="align-right">Received</th>
                  <th aria-label="Open message" />
                </tr>
              </thead>
              <tbody>
                {(overview ? filtered.slice(0, 5) : filtered).map((message) => (
                  <tr
                    className={`message ${selectedMessage === message.id ? "selected" : ""}`}
                    key={message.id}
                  >
                    <td>
                      <Button
                        variant="ghost"
                        className="message-open h-auto justify-start rounded-sm p-0 hover:bg-transparent"
                        type="button"
                        onClick={() => setSelectedMessage(message.id)}
                      >
                        <span className="sender-avatar">
                          <MessageSquare size={16} />
                        </span>
                        <span>
                          <strong>{message.sender.value}</strong>
                          <span className="message-preview">{message.body}</span>
                        </span>
                      </Button>
                    </td>
                    <td>
                      <Badge
                        tone={
                          !message.complete || message.subscription_uncertain
                            ? "warning"
                            : message.replyable
                              ? "success"
                              : "neutral"
                        }
                      >
                        {!message.complete
                          ? "Incomplete"
                          : message.subscription_uncertain
                            ? "SIM uncertain"
                            : message.baselined
                              ? "Existing at baseline"
                              : "Eligible for reply"}
                      </Badge>
                    </td>
                    <td className="align-right">
                      <time dateTime={message.observed_at}>{time(message.observed_at)}</time>
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Read message from ${message.sender.value}`}
                        onClick={() => setSelectedMessage(message.id)}
                      >
                        <ChevronRight size={16} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {inbox.data && !overview && (
            <Pagination offset={inboxOffset} count={inbox.data.length} change={setInboxOffset} />
          )}
        </>
      )}
    </section>
  );
  const jobList = (
    <section className="panel activity">
      <div className="panel-heading">
        <div>
          <h2>Reply workflow</h2>
          <p className="muted small">Follow each reply from generation to device acceptance.</p>
        </div>
        <Badge>{jobCount} total</Badge>
      </div>
      {!inboxSupported || !sendSupported ? (
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
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Workflow state</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {jobs.data?.map((job) => (
                  <tr className="job" key={job.record_id}>
                    <td>
                      <span className="job-icon">
                        <Workflow size={16} />
                      </span>
                      <code className="request-id">{job.request_id.slice(0, 8)}…</code>
                      {job.issue && <p className="muted small">{job.issue.replaceAll("_", " ")}</p>}
                    </td>
                    <td>
                      <Badge tone={outcomeTone(job.state)}>{labels[job.state] || job.state}</Badge>
                    </td>
                    <td className="small muted">{time(job.created_at)}</td>
                    <td>
                      {["submitting", "completed", "interrupted"].includes(job.state) && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedRequest(job.request_id)}
                        >
                          View submission <ArrowUpRight size={13} />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {jobs.data && (
            <Pagination offset={jobsOffset} count={jobs.data.length} change={setJobsOffset} />
          )}
        </>
      )}
    </section>
  );
  return (
    <>
      <header className="page-heading">
        <div>
          <div className="title-line">
            <h1>{device.adapter.model}</h1>
            <Badge tone={access === "ready" ? "success" : "warning"}>
              <span className="badge-dot" />
              {access}
            </Badge>
          </div>
          <p className="muted">
            {overview
              ? "Your cellular operations, at a glance."
              : inboxView
                ? "Read incoming messages and keep conversations moving."
                : jobsView
                  ? "Monitor every step of your assistant’s reply workflow."
                  : "Inspect your adapter, hardware and available operations."}
            <span className="heading-device">{id}</span>
          </p>
        </div>
        <div className="actions">
          <Button variant="outline" onClick={refresh}>
            <RefreshCw size={15} />
            Refresh
          </Button>
          {sendSupported && (
            <Button onClick={() => setComposeOpen(true)}>
              <Plus size={16} />
              Compose SMS
            </Button>
          )}
        </div>
      </header>
      <Feedback resource={status} />
      <Feedback resource={assistant} />
      {overview && (
        <>
          <div className="metrics">
            <section className="metric">
              <div className="metric-heading">
                <p>Network status</p>
                <span className="metric-icon blue">
                  <Radio size={18} />
                </span>
              </div>
              <strong className="capitalize">{status.data?.network_type || "—"}</strong>
              <span>
                <span className={`inline-dot ${access}`} />
                {status.data?.network_provider || "Carrier not observed"}
              </span>
            </section>
            <section className="metric">
              <div className="metric-heading">
                <p>Signal strength</p>
                <span className="metric-icon green">
                  <Signal size={18} />
                </span>
              </div>
              <strong>
                {status.data?.signal_percent ?? "—"}
                <small>{status.data?.signal_percent != null ? "%" : ""}</small>
              </strong>
              <div className="signal-track">
                <span style={{ width: `${status.data?.signal_percent ?? 0}%` }} />
              </div>
              <span>Latest device observation</span>
            </section>
            <section className="metric">
              <div className="metric-heading">
                <p>Automatic replies</p>
                <span className="metric-icon violet">
                  <Bot size={18} />
                </span>
              </div>
              <strong>
                {assistant.data ? (assistant.data.auto_reply ? "Enabled" : "Disabled") : "—"}
              </strong>
              <span>
                <span className={`inline-dot ${assistant.data?.auto_reply ? "ready" : ""}`} />
                {assistant.data?.dry_run ? "Dry run · no automatic SMS" : "Live submission mode"}
              </span>
            </section>
            <section className="metric">
              <div className="metric-heading">
                <p>Reply jobs</p>
                <span className="metric-icon amber">
                  <Workflow size={18} />
                </span>
              </div>
              <strong>{assistant.data ? jobCount : "—"}</strong>
              <span>
                {assistant.data?.jobs.completed || 0} accepted{" "}
                <span className="metric-separator">/</span> {assistant.data?.jobs.interrupted || 0}{" "}
                interrupted
              </span>
            </section>
          </div>
          <div className="overview-banner">
            <span className="banner-icon">
              <Sparkles size={21} />
            </span>
            <div>
              <strong>Your SMS workspace is connected.</strong>
              <p>Monitor incoming messages, reply workflows and submission progress.</p>
            </div>
            <Link to="/jobs">
              View workflows <ArrowRight size={16} />
            </Link>
          </div>
        </>
      )}
      <div
        className={overview ? "workspace-grid" : deviceView ? "device-grid" : "single-workspace"}
      >
        <div className="main-column">
          {(overview || inboxView) && messages}
          {jobsView && jobList}
          {deviceView && identity}
          {overview && (
            <div className="overview-device-summary">
              <span className="icon-tile">
                <Cpu size={18} />
              </span>
              <div>
                <strong>{device.adapter.adapter_id}</strong>
                <p>
                  {device.adapter.manufacturer} <span>·</span> Adapter v{device.adapter.version}{" "}
                  <span>·</span> {caps.length} capabilities
                </p>
              </div>
              <Link to="/device" className="text-link">
                Device details <ChevronRight size={14} />
              </Link>
            </div>
          )}
          {jobsView && (
            <section className="panel lookup-panel">
              <div className="panel-heading">
                <div>
                  <h2>Find submission progress</h2>
                  <p className="muted small">
                    Inspect an existing request without sending another SMS.
                  </p>
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
                <Input
                  id="lookup"
                  value={lookup}
                  placeholder="Paste a submission request UUID"
                  pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                  onChange={(event) => setLookup(event.target.value)}
                  required
                />
                <Button variant="outline" type="submit" disabled={!sendSupported}>
                  <Search size={15} />
                  Look up
                </Button>
              </form>
            </section>
          )}
        </div>
        {(overview || deviceView) && (
          <aside className="side-column">
            {policy}
            <BalancePanel
              api={api}
              deviceId={id}
              supported={caps.includes("carrier.balance.read")}
            />
            <div className="operator-note">
              <ShieldCheck size={17} />
              <p>
                Submission acceptance confirms the device took the message. Recipient delivery is
                tracked separately when supported.
              </p>
            </div>
          </aside>
        )}
      </div>
      <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
        <DialogContent className="compose-dialog">
          <DialogHeader>
            <DialogTitle>Compose SMS</DialogTitle>
            <DialogDescription>Send a message through {device.adapter.model}.</DialogDescription>
          </DialogHeader>
          {sendSupported && (
            <ManualSubmission api={api} deviceId={id} onSubmitted={refreshAfterSubmit} />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!selectedRequest}
        onOpenChange={(open) => {
          if (!open) setSelectedRequest(undefined);
        }}
      >
        <DialogContent className="progress-dialog">
          <DialogHeader>
            <DialogTitle>Submission details</DialogTitle>
            <DialogDescription>Durable request progress from your server.</DialogDescription>
          </DialogHeader>
          {selectedRequest && (
            <SubmissionLookup
              key={selectedRequest}
              api={api}
              deviceId={id}
              requestId={selectedRequest}
              close={() => setSelectedRequest(undefined)}
            />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelectedMessage(undefined);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.sender.value}</DialogTitle>
            <DialogDescription>Received {time(selected?.observed_at)}</DialogDescription>
          </DialogHeader>
          <p className="message-text full-message">{selected?.body}</p>
          <Badge tone={selected?.replyable ? "success" : "neutral"}>
            {selected?.replyable ? "Eligible for reply" : "Stored message"}
          </Badge>
        </DialogContent>
      </Dialog>
    </>
  );
}
