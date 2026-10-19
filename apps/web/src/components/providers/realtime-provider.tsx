import { useQueryClient } from "@tanstack/react-query";
import { createTRPCClient, createWSClient, wsLink } from "@trpc/client";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import type { AppRouter } from "../../../server/router";

const LiveContext = createContext({ revision: 0, state: "connecting" });
export function RealtimeProvider({
  token,
  children,
  enabled,
}: {
  token: string;
  children: ReactNode;
  enabled: boolean;
}) {
  const queries = useQueryClient();
  const [attempt, setAttempt] = useState(0);
  const [feed, setFeed] = useState({ revision: 0, state: "connecting" });
  useEffect(() => {
    if (!enabled) {
      setFeed({ revision: 0, state: "offline" });
      return;
    }
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const bump = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        if (!disposed) {
          setFeed((current) => ({ state: "live", revision: current.revision + 1 }));
          void queries.invalidateQueries({
            predicate: (query) => query.queryKey[0] === "device" && query.queryKey[2] !== "status",
          });
        }
      }, 80);
    };
    const ws = createWSClient({
      url: `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/trpc`,
      connectionParams: { token },
      onOpen: () => {
        if (!disposed) setFeed((current) => ({ ...current, state: "connecting" }));
      },
      onClose: () => {
        if (!disposed) setFeed((current) => ({ ...current, state: "reconnecting" }));
      },
    });
    const client = createTRPCClient<AppRouter>({ links: [wsLink({ client: ws })] });
    const subscription = client.changes.subscribe(undefined, {
      onData(event) {
        if (disposed) return;
        if (event.state === "live") bump();
        else setFeed((current) => ({ ...current, state: event.state }));
      },
      onError(error) {
        if (disposed) return;
        const unauthorized = error.data?.code === "UNAUTHORIZED";
        if (unauthorized) void queries.invalidateQueries();
        setFeed((current) => ({
          revision: current.revision + 1,
          state: unauthorized ? "unauthorized" : "offline",
        }));
        if (!unauthorized)
          retry = setTimeout(
            () => setAttempt((current) => current + 1),
            Math.min(30_000, 2000 * 2 ** Math.min(attempt, 4)),
          );
      },
    });
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(retry);
      subscription.unsubscribe();
      ws.close();
    };
  }, [token, enabled, attempt, queries]);
  return <LiveContext.Provider value={feed}>{children}</LiveContext.Provider>;
}
export const useRealtime = () => useContext(LiveContext);
