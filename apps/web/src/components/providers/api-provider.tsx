import { createContext, type ReactNode, useContext, useMemo } from "react";
import { ApiClient } from "@/api/client";

const ApiContext = createContext<ApiClient | null>(null);
export function ApiProvider({ token, children }: { token: string; children: ReactNode }) {
  const api = useMemo(() => new ApiClient(token), [token]);
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}
export function useApi() {
  const api = useContext(ApiContext);
  if (!api) throw new Error("ApiProvider is required");
  return api;
}
