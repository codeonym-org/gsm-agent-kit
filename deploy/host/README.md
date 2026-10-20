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
Choose a non-overlapping Docker network or fix the host route/firewall. No host
network configuration is modified by this repository.

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
