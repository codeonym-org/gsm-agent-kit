import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { Workspace } from "./app/workspace";
import { ApiProvider } from "./components/providers/api-provider";
import { QueryProvider } from "./components/providers/query-provider";
import { ThemeProvider } from "./components/providers/theme-provider";
import { TooltipProvider } from "./components/ui/tooltip";
import { useDrafts } from "./stores/drafts";
import { useWorkspace } from "./stores/workspace";

export default function App() {
  const [session, setSession] = useState({ token: "", epoch: 0 });
  function connect(token: string) {
    useDrafts.setState({ drafts: {} });
    useWorkspace.setState({ selectedDevice: "", composeOpen: false, selectedRequest: undefined });
    setSession((current) => ({ token, epoch: current.epoch + 1 }));
  }
  return (
    <BrowserRouter>
      <ThemeProvider>
        <TooltipProvider>
          <ApiProvider token={session.token}>
            <QueryProvider key={session.epoch}>
              <Workspace token={session.token} connect={connect} />
            </QueryProvider>
          </ApiProvider>
        </TooltipProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
