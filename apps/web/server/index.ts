import { createServer } from "node:http";
import { fileURLToPath, URL } from "node:url";
import { TRPCError } from "@trpc/server";
import { applyWSSHandler } from "@trpc/server/adapters/ws";
import { config } from "dotenv";
import { WebSocketServer } from "ws";
import { appRouter } from "./router";

config({ path: fileURLToPath(new URL("../../../.env", import.meta.url)), quiet: true });
const backend = process.env.GSM_API_PROXY_TARGET || "http://127.0.0.1:8000";
const port = Number(process.env.GSM_REALTIME_PORT || 3001);
const host = process.env.GSM_REALTIME_HOST || "127.0.0.1";
if (!Number.isInteger(port) || port < 1 || port > 65535)
  throw new Error("Invalid GSM_REALTIME_PORT");
const server = createServer((_req, res) => {
  res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end('{"status":"ok"}');
});
const wss = new WebSocketServer({ noServer: true, maxPayload: 8192 });
server.on("upgrade", (req, socket, head) => {
  // Browser connections must be same-origin, including when Vite/reverse proxy forwards them.
  let allowed = false;
  try {
    allowed = new URL(req.headers.origin || "").host === req.headers.host;
  } catch {
    /* invalid */
  }
  if (!allowed || new URL(req.url || "/", "http://localhost").pathname !== "/trpc") {
    socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
});
const handler = applyWSSHandler({
  wss,
  router: appRouter,
  keepAlive: { enabled: true, pingMs: 15_000, pongWaitMs: 5_000 },
  createContext: async ({ info }) => {
    const token = info.connectionParams?.token || "";
    const response = await fetch(new URL("/api/adapters", backend), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: AbortSignal.timeout(5_000),
      redirect: "error",
    }).catch(() => undefined);
    if (!response?.ok)
      throw new TRPCError({
        code: response?.status === 401 ? "UNAUTHORIZED" : "SERVICE_UNAVAILABLE",
      });
    await response.body?.cancel();
    return { token, backend };
  },
});
server.on("error", (error: NodeJS.ErrnoException) => {
  console.error(
    `Realtime gateway could not listen on ${host}:${port} (${error.code || "UNKNOWN"})`,
  );
  process.exit(1);
});
server.listen(port, host, () => console.info(`Realtime gateway listening on ${host}:${port}`));
function shutdown() {
  handler.broadcastReconnectNotification();
  for (const client of wss.clients) client.terminate();
  wss.close();
  server.close();
}
process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
