import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { useApi } from "@/components/providers/api-provider";

export type Resource<T> = { data?: T; error?: ApiError; loading: boolean; updatedAt?: Date };
export function resource<T>(query: UseQueryResult<T, Error>): Resource<T> {
  const error =
    query.error instanceof ApiError
      ? query.error
      : query.error
        ? new ApiError(0, "Unable to load this view.")
        : undefined;
  return {
    data: error?.status === 401 ? undefined : query.data,
    error,
    loading: query.isFetching,
    updatedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : undefined,
  };
}
export function useDevices() {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["devices"],
      queryFn: ({ signal }) => api.devices(signal),
      refetchInterval: 30_000,
    }),
  );
}
export function useDeviceStatus(id: string, enabled: boolean) {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["device", id, "status"],
      queryFn: ({ signal }) => api.status(id, signal),
      enabled,
      refetchInterval: 30_000,
    }),
  );
}
export function useAssistant(id: string) {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["device", id, "assistant"],
      queryFn: ({ signal }) => api.assistant(id, signal),
    }),
  );
}
export function useMessages(id: string, offset: number, enabled: boolean) {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["device", id, "messages", offset],
      queryFn: ({ signal }) => api.messages(id, offset, signal),
      enabled,
    }),
  );
}
export function useReplyJobs(id: string, offset: number, enabled: boolean) {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["device", id, "jobs", offset],
      queryFn: ({ signal }) => api.jobs(id, offset, signal),
      enabled,
    }),
  );
}
export function useSubmission(id: string, requestId: string, enabled = true) {
  const api = useApi();
  return resource(
    useQuery({
      queryKey: ["device", id, "submission", requestId],
      queryFn: ({ signal }) => api.submission(id, requestId, signal),
      enabled,
    }),
  );
}
