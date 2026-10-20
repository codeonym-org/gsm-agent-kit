# Host prerequisites and device ownership

## ZTE MF833T HTTP profile

The supported deployment path is Linux Docker Engine with an already configured
network interface/route to the MF833T management address (usually
`192.168.0.1`). The host must initialize USB/ECM networking and assign/obtain its
address. A container does not initialize USB mode switching, SIM PIN entry,
carrier registration, APN provisioning or the host route.

Before starting the profile, check the route with `ip route get 192.168.0.1`.
Verify that the management UI is reachable from the host, then from the container
network if needed. The production container needs outbound HTTP to the device
and HTTPS to OpenRouter. Host routing, firewall forwarding, VPNs and overlapping
Docker subnets may prevent bridge access even when the host browser works.
Choose a non-overlapping Docker network or fix the host route/firewall. Containers
never modify host network configuration. An optional NetworkManager helper is
described below.

Docker Desktop for macOS/Windows and rootless Docker add network namespaces or a
VM. USB reachability and host-to-VM routes are not validated by this profile;
configure and verify them explicitly. This is not universal plug-and-play USB
support. Installer media (including an `inwi 4G MF833T` mount) contains software,
not an HTTP or AT control interface. Mounting that directory into a container
cannot expose the cellular device's network or control endpoint.

Stop other SMS agents/device-management clients before starting this backend.
Operation ownership is process-local; neither a named volume nor a logical
device ID provides a distributed lock. One process must own each physical
device. The SQLite volume also belongs to that one process. API token
authentication is recommended even on loopback. Put a separate authenticated
TLS reverse proxy in front before exposing any API beyond the host.

After unplug/replug, the host must restore the management interface and route.
Inbox polling resumes on successful requests to the same address, but there is
no USB hotplug manager or automatic address discovery. Update `.env` and recreate
the container if the management address changes. Unknown SMS outcomes remain
uncertain; reconnecting or restarting does not establish acceptance or delivery,
and must not be used as an instruction to resend. Changing SIM/storage requires
new subscription/storage generation settings, as described in the server README.

## Prefer Wi-Fi and keep the USB device as fallback

A USB/ECM device often appears to NetworkManager as a wired connection, whose
automatic route metric can outrank Wi-Fi. Internet traffic and public DNS queries
can then use the cellular uplink while Wi-Fi is connected. The observed inwi
setup failed Docker/PyPI DNS resolution on that uplink and worked over Wi-Fi.
Changing Docker's package dependencies does not fix this host route selection.

The original `.v0/network_manager.sh` hardcodes `Wired connection 1` and only
adjusts IPv4. A different USB port may create `Wired connection 2`, leaving the
new profile unaffected. Use the explicit saved-profile UUID in the new helper:

```bash
nmcli -f NAME,UUID,TYPE,DEVICE connection show
bash deploy/host/network-manager.sh status YOUR_USB_PROFILE_UUID
bash deploy/host/network-manager.sh fallback-modem YOUR_USB_PROFILE_UUID --dry-run
sudo bash deploy/host/network-manager.sh fallback-modem YOUR_USB_PROFILE_UUID
```

`fallback-modem` keeps the device's directly connected management subnet and
default routes, with route metric 1000 and DNS priority 1000 for both IP families.
Wi-Fi must have lower route metrics and DNS priority: normal Wi-Fi defaults
(usually metric 600, effective DNS priority 100) satisfy this. Check custom
profiles before applying. Lower route metrics win within an IP family; IPv4
and IPv6 metrics are not compared with each other. A cellular IPv6 route can
still carry IPv6 traffic if Wi-Fi offers only IPv4. DNS priority orders existing
DNS configuration; the helper does not replace DNS servers or rewrite a foreign
`resolv.conf`.

Changes persist across reconnects of that saved profile. Active devices are
reapplied without deliberately dropping the connection; inactive profiles stay
inactive until their next activation. A reapply failure is reported; reconnect
that specific profile if needed. Moving ports or creating another profile may
require applying the setting to its new UUID. This helper requires NetworkManager
and sufficient Polkit/root permissions, and is never invoked automatically.

```bash
# Keep only the management network, with no cellular default route:
sudo bash deploy/host/network-manager.sh prefer-wifi YOUR_USB_PROFILE_UUID
# Prefer the cellular route instead:
sudo bash deploy/host/network-manager.sh prefer-modem YOUR_USB_PROFILE_UUID
# Return the selected profile to automatic route/DNS priorities:
sudo bash deploy/host/network-manager.sh reset YOUR_USB_PROFILE_UUID
```

`reset` sets `never-default=no`, route metric `-1` and DNS priority `0` for both
families; it does not restore arbitrary prior custom settings. Record the output
of `status` first if the profile already has custom values.

Verify the result with `ip route get 1.1.1.1` (Wi-Fi),
`ip route get 192.168.0.1` (the USB interface while connected),
`resolvectl status`, and `python scripts/smoke_containers.py`. Fallback applies
when Wi-Fi's route is withdrawn/disconnected; it is not an internet-health
monitor for a Wi-Fi connection that stays associated but loses upstream access.
If Docker retains stale DNS configuration, recreate only the affected containers
after the host network is corrected.

See NetworkManager's [IPv4](https://www.networkmanager.dev/docs/api/latest/settings-ipv4.html)
and [IPv6](https://www.networkmanager.dev/docs/api/latest/settings-ipv6.html)
settings reference for route metrics, DNS priority and `never-default` semantics.

## Future serial AT profile

This integration remains a scaffold. A future profile needs a stable host path
such as `/dev/serial/by-id/...`, a narrowly scoped `devices:` mapping, the
appropriate device GID or udev permissions, and exclusive ownership of the
correct control port. Mapping a tty does not itself provide USB mode switching,
hotplug rebinding or permission management. Re-enumeration may require container
recreation. Do not expose every `/dev` device or enable privileged mode as a
substitute for those requirements.

## Future ModemManager profile

This integration also remains a scaffold. Prefer a host-managed ModemManager
owning the device, with an adapter client using the host system D-Bus socket and
explicit D-Bus/Polkit permissions. The host service, SIM/network provisioning and
access policy remain host responsibilities. Mounting the bus exposes a broader
host control surface than one modem; it needs its own access design. Running a
second ModemManager in a generic container risks competing ownership and needs
udev/device hotplug integration. Neither profile is implemented or included in
the current HTTP image.
