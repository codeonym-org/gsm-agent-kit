import { initTRPC, TRPCError } from "@trpc/server";
import { observable } from "@trpc/server/observable";
import WebSocket from "ws";

export type FeedEvent = { state: "live" | "reconnecting"; revision?: number };
export type Context = { token: string; backend: string };
const t = initTRPC.context<Context>().create({
  errorFormatter({ shape }) {
    // Do not expose backend bodies, tokens, stack traces or environment details.
    return {
      ...shape,
      message: shape.code === -32001 ? "API access denied" : "Live updates unavailable",
      data: { code: shape.data.code, httpStatus: shape.data.httpStatus },
    };
  },
});

export const appRouter = t.router({
  changes: t.procedure.subscription(({ ctx }) =>
    observable<FeedEvent>((emit) => {
      let disposed = false;
      let upstream: WebSocket | undefined;
      let retry: ReturnType<typeof setTimeout> | undefined;
      let watchdog: ReturnType<typeof setTimeout> | undefined;
      function heartbeat() {
        clearTimeout(watchdog);
        watchdog = setTimeout(() => upstream?.terminate(), 45_000);
      }
      function connect() {
        if (disposed) return;
        const url = new URL("/api/events", ctx.backend);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        upstream = new WebSocket(url, { handshakeTimeout: 5_000, maxPayload: 4096 });
        heartbeat();
        upstream.on("open", () => upstream?.send(JSON.stringify({ token: ctx.token })));
        upstream.on("message", (raw) => {
          heartbeat();
          try {
            const message = JSON.parse(raw.toString());
            if (message.type === "invalidate" && Number.isSafeInteger(message.revision)) {
              emit.next({ state: "live", revision: message.revision });
            }
          } catch {
            upstream?.close();
          }
        });
        upstream.on("error", () => {
          /* close drives reconnect, no sensitive errors logged */
        });
        upstream.on("close", (code) => {
          clearTimeout(watchdog);
          if (disposed) return;
          if (code === 4401) {
            emit.error(new TRPCError({ code: "UNAUTHORIZED", message: "API access denied" }));
            return;
          }
          emit.next({ state: "reconnecting" });
          retry = setTimeout(connect, 1_000);
        });
      }
      connect();
      return () => {
        disposed = true;
        clearTimeout(retry);
        clearTimeout(watchdog);
        upstream?.terminate();
      };
    }),
  ),
});
export type AppRouter = typeof appRouter;
