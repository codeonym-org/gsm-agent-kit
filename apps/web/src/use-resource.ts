import { useEffect, useState } from "react";
import { ApiError } from "./api/client";
import { useRealtime } from "./realtime";

export type Resource<T> = {
  data?: T;
  error?: ApiError;
  loading: boolean;
  updatedAt?: Date;
};

export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  revision: number,
  active = true,
  interval = 30_000,
): Resource<T> {
  const { revision: liveRevision } = useRealtime();
  const observedRevision = revision + liveRevision;
  const [resource, setResource] = useState<Resource<T> & { load: typeof load; revision: number }>({
    loading: active,
    load,
    revision: observedRevision,
  });
  useEffect(() => {
    if (!active) {
      setResource({ loading: false, load, revision: observedRevision });
      return;
    }
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const data = await load(controller.signal);
        if (!disposed)
          setResource({
            data,
            loading: false,
            updatedAt: new Date(),
            load,
            revision: observedRevision,
          });
      } catch (error) {
        if (!disposed) {
          const failure =
            error instanceof ApiError ? error : new ApiError(0, "Unable to load this view.");
          setResource((previous) => ({
            ...(failure.status === 401 ? {} : previous),
            load,
            revision: observedRevision,
            loading: false,
            error: failure,
          }));
        }
      }
      if (!disposed && interval > 0) timer = setTimeout(poll, interval);
    };
    setResource((previous) => ({
      ...(previous.load === load ? previous : {}),
      loading: true,
      load,
      revision: observedRevision,
    }));
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, observedRevision, active, interval]);
  return resource.load === load ? resource : { loading: active };
}
