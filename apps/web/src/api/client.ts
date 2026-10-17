import type { components } from "./schema";

type Schemas = components["schemas"];
export type Device = Schemas["DeviceResponse"];
export type Status = Schemas["StatusResponse"];
export type Message = Schemas["InboxRecordResponse"];
export type Assistant = Schemas["AssistantStatus"];
export type ReplyJob = Schemas["ReplyJobStatus"];
export type Submission = Schemas["SubmissionResponse"];
export type Balance = Schemas["BalanceObservation"];
export type SendRequest = Schemas["SendSmsRequest"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export class ApiClient {
  constructor(private readonly token: string) {}

  private async request<T>(
    path: string,
    signal?: AbortSignal,
    body?: SendRequest,
    timeout = 15_000,
  ): Promise<T> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    const timer = window.setTimeout(abort, timeout);
    try {
      const response = await fetch(`/api${path}`, {
        method: body ? "POST" : "GET",
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        headers: {
          Accept: "application/json",
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) {
        const errors: Record<number, string> = {
          401: "API access denied. Enter a valid server API token.",
          404: "This device or record could not be found.",
          409: "The device is busy, or the request conflicts with existing progress.",
          422: "The request is invalid. Check the destination and message.",
          501: "This operation is not supported by the selected device.",
          502: "The device returned an invalid response or could not complete the operation.",
          503: "This operation is disabled or temporarily unavailable on the server.",
          504: "The operation exceeded its deadline.",
        };
        throw new ApiError(
          response.status,
          errors[response.status] || "The server could not complete this request.",
        );
      }
      return (await response.json()) as T;
    } catch (error) {
      if (signal?.aborted) throw error;
      if (error instanceof ApiError) throw error;
      throw new ApiError(0, "Cannot reach the server. Check the connection and try again.");
    } finally {
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  }

  devices = (signal?: AbortSignal) => this.request<Device[]>("/devices", signal);
  status = (id: string, signal?: AbortSignal) =>
    this.request<Status>(`/devices/${encodeURIComponent(id)}/status`, signal);
  messages = (id: string, offset: number, signal?: AbortSignal) =>
    this.request<Message[]>(
      `/devices/${encodeURIComponent(id)}/messages?limit=25&offset=${offset}`,
      signal,
    );
  assistant = (id: string, signal?: AbortSignal) =>
    this.request<Assistant>(`/devices/${encodeURIComponent(id)}/assistant`, signal);
  jobs = (id: string, offset: number, signal?: AbortSignal) =>
    this.request<ReplyJob[]>(
      `/devices/${encodeURIComponent(id)}/assistant/jobs?limit=25&offset=${offset}`,
      signal,
    );
  submission = (id: string, requestId: string, signal?: AbortSignal) =>
    this.request<Submission>(
      `/devices/${encodeURIComponent(id)}/submissions/${encodeURIComponent(requestId)}`,
      signal,
    );
  send = (id: string, body: SendRequest, signal?: AbortSignal) =>
    this.request<Submission>(
      `/devices/${encodeURIComponent(id)}/submissions`,
      signal,
      body,
      125_000,
    );
  balance = (id: string, signal?: AbortSignal) =>
    this.request<Balance>(`/devices/${encodeURIComponent(id)}/balance`, signal, undefined, 130_000);
}
