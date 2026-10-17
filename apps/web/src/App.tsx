import {
  Activity,
  ArrowUpRight,
  ChevronDown,
  Command,
  Cpu,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Radio,
  Settings2,
  ShieldCheck,
  Workflow,
  Zap,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ApiClient } from "./api/client";
import { Dashboard } from "./components/dashboard";
import { Empty, Feedback } from "./components/shared";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./components/ui/dialog";
import { Input } from "./components/ui/input";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "./components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./components/ui/tooltip";
import { RealtimeProvider, useRealtime } from "./realtime";
import { useResource } from "./use-resource";

const navigation = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/inbox", label: "Inbox", icon: MessageSquare },
  { to: "/jobs", label: "Reply jobs", icon: Workflow },
  { to: "/device", label: "Device & capabilities", icon: Cpu },
];

function LiveIndicator() {
  const { state } = useRealtime();
  return (
    <span className={`connection-status ${state}`} role="status">
      <span className="live-dot" />
      {state === "live"
        ? "Live updates"
        : state === "connecting"
          ? "Connecting live…"
          : state === "unauthorized"
            ? "Live access denied"
            : "Reconnecting live…"}
    </span>
  );
}

function Console() {
  const [token, setToken] = useState("");
  const [draftToken, setDraftToken] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selected, setSelected] = useState("");
  const [revision, setRevision] = useState(0);
  const [connection, setConnection] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const api = useMemo(() => new ApiClient(token), [token]);
  const loadDevices = useCallback((signal: AbortSignal) => api.devices(signal), [api]);
  const devices = useResource(loadDevices, revision, true, 30_000);
  const current =
    devices.data?.find((device) => device.device_id === selected) || devices.data?.[0];
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const authRequired = devices.error?.status === 401;
  const location = useLocation();
  const section = navigation.find((item) => item.to === location.pathname)?.label || "Overview";
  const sidebar = (
    <>
      <a className="brand" href="/overview">
        <span className="brand-mark">
          <Radio size={21} strokeWidth={2.2} />
        </span>
        <span>
          gsm<span className="brand-light"> / agent kit</span>
          <small>OPERATOR WORKSPACE</small>
        </span>
      </a>
      <div className="workspace-switch">
        <span className="workspace-avatar">
          <Command size={17} />
        </span>
        <span>
          My workspace<small>Local environment</small>
        </span>
        <ChevronDown size={14} />
      </div>
      <p className="nav-label">WORKSPACE</p>
      <nav className="primary-nav" aria-label="Main navigation">
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon size={17} />
            <span>{label}</span>
            {to === "/inbox" && <span className="nav-live" />}
          </NavLink>
        ))}
      </nav>
      <p className="nav-label device-label">
        CONNECTED HARDWARE <span>{devices.data?.length ?? "—"}</span>
      </p>
      <div className="device-switch">
        <Radio size={16} />
        <select
          aria-label="Cellular device"
          value={current?.device_id || ""}
          onChange={(event) => setSelected(event.target.value)}
          disabled={!devices.data?.length}
        >
          <option value="" disabled>
            Choose a device
          </option>
          {devices.data?.map((device) => (
            <option key={device.device_id} value={device.device_id}>
              {device.device_id} · {device.adapter.model}
            </option>
          ))}
        </select>
      </div>
      <div className="sidebar-bottom">
        <div className="local-note">
          <ShieldCheck size={18} />
          <div>
            Your hardware. Your data.<p>Device operations stay on your server.</p>
          </div>
        </div>
        <button
          className="sidebar-settings"
          type="button"
          onClick={() => {
            setSettingsOpen(true);
            setMobileOpen(false);
          }}
        >
          <Settings2 size={17} /> API connection <ArrowUpRight size={14} />
        </button>
        <div className="sidebar-version">
          <span>GSM Agent Kit</span>
          <code>v0.1.0</code>
        </div>
      </div>
    </>
  );
  return (
    <RealtimeProvider key={connection} token={token} enabled={!!devices.data && !authRequired}>
      <div className="app-shell">
        <aside className="sidebar">{sidebar}</aside>
        <div className="content-shell">
          <header className="topbar">
            <div className="breadcrumb">
              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="mobile-menu"
                    aria-label="Open navigation"
                  >
                    <Menu size={18} />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="mobile-sidebar">
                  <SheetTitle className="sr-only">Workspace navigation</SheetTitle>
                  {sidebar}
                </SheetContent>
              </Sheet>
              <span>Workspace</span>
              <span className="breadcrumb-slash">/</span>
              <strong>{section}</strong>
            </div>
            <div className="topbar-actions">
              <LiveIndicator />
              <span className="topbar-divider" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="API connection"
                    onClick={() => setSettingsOpen(true)}
                  >
                    <Settings2 size={17} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>API connection</TooltipContent>
              </Tooltip>
              <span className="operator-avatar">OP</span>
            </div>
          </header>
          <main className="main-content">
            <div className="workspace-context">
              <span>
                <span className="context-dot" /> LOCAL WORKSPACE
              </span>
              <span>
                <Activity size={13} /> Cellular operations
              </span>
            </div>
            <Feedback resource={devices} />
            {devices.error && !devices.data && !authRequired && (
              <section className="panel">
                <Empty
                  title={
                    devices.error.status === 0 ? "Server is offline" : "Unable to load devices"
                  }
                >
                  Check the backend connection, then retry.
                </Empty>
                <Button variant="outline" onClick={refresh}>
                  Retry connection
                </Button>
              </section>
            )}
            {devices.data?.length === 0 && (
              <section className="panel">
                <Empty title="No configured devices">
                  Add a logical cellular device to the server configuration to start.
                </Empty>
              </section>
            )}
            {current && (
              <Dashboard
                key={`${current.device_id}-${connection}`}
                api={api}
                device={current}
                revision={revision}
                refresh={refresh}
                view={location.pathname}
              />
            )}
            {!current && authRequired && (
              <div className="welcome">
                <span className="welcome-mark">
                  <Radio size={36} />
                </span>
                <h1>Your cellular workspace</h1>
                <p>Connect to your server to manage devices, messages and AI replies.</p>
                <Button onClick={() => setSettingsOpen(true)}>
                  <Zap size={16} /> Connect to server
                </Button>
              </div>
            )}
          </main>
          <footer className="app-footer">
            <span>
              <ShieldCheck size={13} /> Local device ownership
            </span>
            <span>
              GSM Agent Kit <span>·</span> Operator console
            </span>
          </footer>
        </div>
      </div>
      <Dialog open={settingsOpen || authRequired} onOpenChange={setSettingsOpen}>
        <DialogContent className="connection-dialog">
          <DialogHeader>
            <span className="dialog-icon">
              <Settings2 size={21} />
            </span>
            <DialogTitle>API access</DialogTitle>
            <DialogDescription>
              Connect to your GSM Agent server. Your access token stays in memory until you reload
              or disconnect.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setToken(draftToken.trim());
              setConnection((value) => value + 1);
              setDraftToken("");
              setSettingsOpen(false);
              refresh();
            }}
          >
            <label htmlFor="api-token">API access token</label>
            <Input
              id="api-token"
              type="password"
              autoComplete="off"
              value={draftToken}
              placeholder="Enter your server API token"
              onChange={(event) => setDraftToken(event.target.value)}
            />
            <div className="dialog-actions">
              {token && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setToken("");
                    setConnection((value) => value + 1);
                    setDraftToken("");
                  }}
                >
                  Disconnect
                </Button>
              )}
              <Button type="submit">
                <Zap size={15} />
                Connect
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </RealtimeProvider>
  );
}
export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/*" element={<Console />} />
        </Routes>
      </TooltipProvider>
    </BrowserRouter>
  );
}
