import { useCallback, useMemo, useState } from "react";
import { ApiClient } from "./api/client";
import { Dashboard } from "./components/dashboard";
import { Empty, Feedback } from "./components/shared";
import { useResource } from "./use-resource";

export default function App() {
  const [token, setToken] = useState("");
  const [draftToken, setDraftToken] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selected, setSelected] = useState("");
  const [revision, setRevision] = useState(0);
  const [connection, setConnection] = useState(0);
  const api = useMemo(() => new ApiClient(token), [token]);
  const loadDevices = useCallback((signal: AbortSignal) => api.devices(signal), [api]);
  const devices = useResource(loadDevices, revision, true, 10_000);
  const current =
    devices.data?.find((device) => device.device_id === selected) || devices.data?.[0];
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const authRequired = devices.error?.status === 401;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            G
          </span>
          <span>
            GSM Agent Kit<small>Operator console</small>
          </span>
        </a>
        <div className="sidebar-section">
          <p className="eyebrow">Workspace</p>
          <div className="nav-item active">
            <span aria-hidden="true">◉</span> Devices{" "}
            <span className="nav-count">{devices.data?.length ?? "—"}</span>
          </div>
        </div>
        <div className="sidebar-section">
          <p className="eyebrow">Configured devices</p>
          <label className="sr-only" htmlFor="device-picker">
            Cellular device
          </label>
          <select
            id="device-picker"
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
          <p className="sidebar-note">Each device exposes its own supported operations.</p>
        </div>
        <div className="sidebar-bottom">
          <span className="edition">Public source · All rights reserved</span>
          <span className="version">gsm-agent-kit / 0.1.0</span>
        </div>
      </aside>
      <div className="content-shell">
        <div className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> Devices
            {current && (
              <>
                <span>/</span>
                <strong>{current.device_id}</strong>
              </>
            )}
          </div>
          <button
            className="button ghost"
            type="button"
            onClick={() => setSettingsOpen((open) => !open)}
          >
            API connection <span aria-hidden="true">↗</span>
          </button>
        </div>
        <main>
          {(settingsOpen || authRequired) && (
            <section className="panel connection">
              <div>
                <p className="eyebrow">Server connection</p>
                <h2>API access</h2>
                <p className="muted">
                  Use the server's API access token if authentication is enabled. It stays in memory
                  until you reload or disconnect.
                </p>
              </div>
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
                <div className="lookup">
                  <input
                    id="api-token"
                    type="password"
                    autoComplete="off"
                    value={draftToken}
                    placeholder="Optional server API token"
                    onChange={(event) => setDraftToken(event.target.value)}
                  />
                  <button className="button primary" type="submit">
                    Connect
                  </button>
                  {token && (
                    <button
                      className="button secondary"
                      type="button"
                      onClick={() => {
                        setToken("");
                        setConnection((value) => value + 1);
                        setDraftToken("");
                      }}
                    >
                      Disconnect
                    </button>
                  )}
                </div>
              </form>
            </section>
          )}
          <Feedback resource={devices} />
          {devices.error && !devices.data && !authRequired && (
            <section className="panel">
              <Empty
                title={devices.error.status === 0 ? "Server is offline" : "Unable to load devices"}
              >
                Check the backend connection, then retry.
              </Empty>
              <button type="button" className="button secondary" onClick={refresh}>
                Retry connection
              </button>
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
            />
          )}
        </main>
      </div>
    </div>
  );
}
