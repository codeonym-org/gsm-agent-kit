import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSubmission } from "@/queries/devices";
import { emptyDraft, useDrafts } from "@/stores/drafts";
import { ApiError, type Submission } from "../api/client";
import { useApi } from "./providers/api-provider";
import { Badge, Feedback, labels, outcomeTone, time } from "./shared";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";

export function SubmissionProgress({ record }: { record: Submission }) {
  return (
    <section className="space-y-4" aria-label="Submission progress">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
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
      <p className="text-sm text-muted-foreground">
        Acceptance does not confirm recipient delivery.
      </p>
      {record.truncated && (
        <p className="rounded-lg border bg-muted/40 p-3 text-sm">
          The server shortened this message to fit the configured SMS budget.
        </p>
      )}
      <dl className="grid grid-cols-2 gap-4 text-sm [&_dt]:text-muted-foreground [&_dd]:mt-1">
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
        <article className="space-y-3 rounded-lg border bg-muted/20 p-4" key={part.message_id}>
          <div className="flex items-center justify-between gap-2 text-sm">
            <strong>Part {part.index + 1}</strong>
            <Badge tone={outcomeTone(part.state)}>{labels[part.state] || part.state}</Badge>
          </div>
          <p className="whitespace-pre-wrap wrap-anywhere text-sm leading-relaxed">{part.text}</p>
          {part.attempts.map((attempt) => (
            <p className="text-xs text-muted-foreground" key={attempt.id}>
              Attempt:{" "}
              {attempt.outcome ? labels[attempt.outcome] || attempt.outcome : "In progress"}
              {attempt.reason ? ` · ${attempt.reason.replaceAll("_", " ")}` : ""}
            </p>
          ))}
        </article>
      ))}
      {record.parts.some((part) => part.state === "unknown" || part.state === "in_progress") && (
        <p className="rounded-lg border border-amber-600/20 p-3 text-sm text-amber-700 dark:text-amber-400">
          An outcome is uncertain. Check existing progress; this console will not resend it.
        </p>
      )}
    </section>
  );
}

export function SubmissionLookup({
  deviceId,
  requestId,
  close,
}: {
  deviceId: string;
  requestId: string;
  close: () => void;
}) {
  const progress = useSubmission(deviceId, requestId);
  return (
    <section className="space-y-4" aria-label="Selected submission">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">Submission record</p>
          <h2>Request progress</h2>
        </div>
        <Button type="button" variant="ghost" onClick={close}>
          Close
        </Button>
      </div>
      <code className="block break-all text-xs text-muted-foreground">{requestId}</code>
      <Feedback resource={progress} />
      {progress.data && <SubmissionProgress record={progress.data} />}
    </section>
  );
}

export function ManualSubmission({
  deviceId,
  onSubmitted,
}: {
  deviceId: string;
  onSubmitted: () => void;
}) {
  const api = useApi();
  const draft = useDrafts((state) => state.drafts[deviceId] || emptyDraft);
  const update = useDrafts((state) => state.update);
  const clear = useDrafts((state) => state.clear);
  const queries = useQueryClient();
  const send = useMutation({
    mutationFn: (body: { request_id: string; destination: string; text: string }) =>
      api.send(deviceId, body),
    onSuccess(record) {
      queries.setQueryData(["device", deviceId, "submission", record.request_id], record);
      onSubmitted();
    },
  });
  const progress = useSubmission(
    deviceId,
    draft.requestId || "",
    !!draft.requestId && !send.isPending,
  );
  function submit() {
    if (useDrafts.getState().drafts[deviceId]?.requestId) return;
    const requestId = crypto.randomUUID();
    update(deviceId, { requestId });
    send.mutate({ request_id: requestId, destination: draft.destination, text: draft.text });
  }
  return (
    <section className="composer space-y-5">
      <h2 className="text-sm font-medium">Manual submission</h2>
      {!draft.requestId ? (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <p className="text-sm text-muted-foreground">
            Submit an SMS directly. Assistant dry-run settings apply only to automatic replies.
          </p>
          <div className="space-y-2">
            <Label htmlFor="destination">Destination</Label>
            <Input
              id="destination"
              type="tel"
              placeholder="+212…"
              value={draft.destination}
              onChange={(event) => update(deviceId, { destination: event.target.value })}
              pattern="\+[1-9][0-9]{2,14}"
              required
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sms-text">Message</Label>
            <Textarea
              id="sms-text"
              rows={6}
              placeholder="Write a message…"
              value={draft.text}
              onChange={(event) => update(deviceId, { text: event.target.value })}
              maxLength={10000}
              required
            />
            <div className="flex justify-between gap-2 text-xs text-muted-foreground">
              <span>{draft.text.length.toLocaleString()} characters</span>
              <span>Server SMS limits apply</span>
            </div>
          </div>
          <Button
            className="w-full"
            type="submit"
            disabled={!draft.text.trim() || !draft.destination}
          >
            Submit SMS
          </Button>
        </form>
      ) : (
        <>
          <div className="space-y-2">
            <Label htmlFor="manual-request-id">Request ID — keep this to find progress later</Label>
            <Input
              id="manual-request-id"
              readOnly
              value={draft.requestId}
              className="font-mono text-xs"
            />
          </div>
          {send.isPending && (
            <p role="status" className="text-sm text-muted-foreground">
              Waiting for submission progress…
            </p>
          )}
          {send.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {send.error instanceof ApiError
                  ? send.error.message
                  : "The submission response is unavailable."}{" "}
                Check this request's progress before creating another submission.
              </AlertDescription>
            </Alert>
          )}
          {!send.isPending && <Feedback resource={progress} />}
          {progress.data && <SubmissionProgress record={progress.data} />}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={send.isPending || progress.loading}
              onClick={() =>
                void queries.invalidateQueries({
                  queryKey: ["device", deviceId, "submission", draft.requestId],
                })
              }
            >
              Check progress
            </Button>
            <Button
              variant="ghost"
              disabled={send.isPending}
              onClick={() => {
                clear(deviceId);
                send.reset();
              }}
            >
              New draft
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
