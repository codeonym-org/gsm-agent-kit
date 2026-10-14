# Containerized cellular-device access on Linux

Investigated 2026-10-14 for [Establish host-access constraints for containerized device adapters](https://github.com/codeonym-org/gsm-agent-kit/issues/16), part of [Chart the first-release GSM Agent Kit architecture](https://github.com/codeonym-org/gsm-agent-kit/issues/11).

This note establishes prerequisites and limitations. It does not select the deployment design, declare an adapter compatible, or supply a tested container recipe. No hardware was accessed or changed during this research.

## Findings

Adapter libraries and command-line clients can live in an image. A container cannot supply a missing device interface or independently replace host kernel drivers: Linux containers share a kernel. Host device enumeration, routing and access policy remain prerequisites. Consequently, “keep application dependencies off the host” is achievable; “no host prerequisites for every cellular device” is not. The latter is an inference from the kernel-sharing and access mechanisms documented below. [Docker container fundamentals](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-a-container/)

| Access method | Dependencies that can live in the image | Host prerequisites | Resource exposed to the adapter |
| --- | --- | --- | --- |
| Device-managed HTTP | Python runtime, HTTP client, model-specific adapter | Working network interface and route to the management address | Reachable HTTP endpoint |
| Serial AT | Python runtime, serial library, model-specific adapter | Compatible driver, exposed control port, permissions and coordinated port ownership | Selected character device |
| Existing ModemManager daemon | D-Bus client library or `mmcli` and its runtime dependencies | Running compatible daemon, supported control interface, system bus and authorization | Authorized D-Bus connection |

The table summarizes the evidence in the following sections. Dependency packaging is distinct from deciding which process owns the cellular device.

## Device-managed HTTP

Docker bridge networking normally provides outgoing access through masquerading. **Inference:** an adapter can reach a device management address through ordinary bridge networking when the host route and firewall permit it and the container subnet does not conflict. Binding the USB storage volume is unrelated to this network path. Reachability must be verified from the actual deployment; host reachability alone does not establish container reachability. [Docker bridge networking](https://docs.docker.com/engine/network/drivers/bridge/)

Linux host networking is an alternative that shares the host network namespace. Published port mappings then have no effect. It is not inherently necessary for an outgoing HTTP client. Docker Desktop's opt-in host networking has different limitations, so a successful Linux Engine profile should not be described as portable without further verification. [Docker host networking](https://docs.docker.com/engine/network/drivers/host/)

The archived MF833T investigation records HTTP management at `192.168.0.1`, CDC ECM networking and working status/inbox requests. This is model-and-variant evidence, not a universal ZTE interface. HTTP credentials, endpoint addresses and timeouts belong to deployment configuration; the archived observations do not prove authentication behavior across all restarts. [Archived device capabilities](../../.v0/docs/modem-capabilities.md)

**Reconnect inference:** loss of the USB network link removes the path to the HTTP endpoint. A container image does not restore that host link. Deployment verification must cover route restoration, renewed HTTP sessions and device identity after reconnect; none was tested here.

## Serial AT

The kernel USB serial driver provides serial-device access for supported USB interfaces. Installing a serial client is downstream of that interface being present; it cannot turn a storage or network interface into an AT port. Relevant drivers depend on the device layout, rather than the manufacturer's name alone. [Linux USB serial documentation](https://cdn.kernel.org/doc/html/latest/usb/usb-serial.html)

Docker can expose a selected host device to an otherwise unprivileged container with `--device`. This controls access to the device node, not firmware capability. Docker documents that device assignment occurs at container creation; dynamic devices require additional handling. A broader cgroup device rule alone does not create a newly appeared node inside the container. **Inference:** unplug/replug must be tested explicitly; a static assignment and a restart policy are not proof of hotplug recovery. [Docker device assignment and dynamic devices](https://docs.docker.com/reference/cli/docker/container/run/#add-host-device-to-container---device)

Host udev manages device-node permissions and can create meaningful symlinks; kernel discovery names are not reliable identities. `OWNER`, `GROUP` and `MODE` are policy tools. **Inference:** use verified device properties to select the intended port and check actual numeric UID/GID access. A group called `dialout` inside an image does not establish equivalence with the host's group. Stable symlinks help selection but do not alone solve Docker's creation-time assignment. [udev manual distributed by Debian](https://manpages.debian.org/trixie/udev/udev.7.en.html)

pySerial exposes baud rate, flow control, read/write timeouts and POSIX exclusive mode. Exclusive mode is useful between cooperating openers, but its documented semantics should not be treated as a general ownership policy that excludes every other daemon. Port settings, disconnect errors and reacquisition behavior remain adapter concerns. [pySerial serial interface](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)

ModemManager detects ports through udev and may probe control ports. Its documented device/port-ignore tags can exclude devices from that detection. **Inference:** a direct AT adapter and ModemManager require a deliberate ownership arrangement; merely putting the AT process in a container does not coordinate shared ports. Applying ignore tags is host configuration, not an operation this investigation performs. [ModemManager port detection and ignore tags](https://mobile-broadband.pages.freedesktop.org/docs/modemmanager/port-and-device-detection/)

ModemManager inhibition closes its ports and removes the device from its D-Bus exports; the inhibition is tied to the caller's D-Bus connection. The `mmcli` manual also states that inhibition disables the device and stops an ongoing connection. Thus inhibition is not evidence that direct AT access can be added while normal connectivity continues unchanged. [Upstream inhibition contract](https://github.com/linux-mobile-broadband/ModemManager/blob/7f0bf17ab518cd78925cf7e53cc0d5c42f88b41a/introspection/org.freedesktop.ModemManager1.xml), [mmcli manual distributed by Debian](https://manpages.debian.org/trixie/modemmanager/mmcli.1.en.html)

## ModemManager through the host system bus

ModemManager requires an appropriate control interface. A device exposing only a network interface is not supported merely because it has a SIM. Different layouts may expose AT, QMI or MBIM control ports; hardware form factor alone does not determine the usable protocol. [ModemManager device types](https://mobile-broadband.pages.freedesktop.org/docs/modemmanager/wwan-device-types/)

For an adapter talking to an existing host daemon, the container needs a D-Bus client connection, not a second copy of the daemon. The system bus uses a Unix socket, conventionally `/run/dbus/system_bus_socket` or its `/var/run` equivalent, and supports an explicit `DBUS_SYSTEM_BUS_ADDRESS`. Unix authentication carries user identity; mounting a socket does not bypass authentication. [D-Bus system bus and authentication specification](https://dbus.freedesktop.org/doc/dbus-specification.html)

Authorization is additional to connection establishment. Upstream ModemManager's bus policy distinguishes readable methods from protected operations; its polkit policy includes separate messaging, USSD, voice and device-control actions. Actual distribution builds and installed rules matter. A headless container must not assume that interactive desktop authentication will succeed. [Upstream bus policy](https://github.com/linux-mobile-broadband/ModemManager/blob/7f0bf17ab518cd78925cf7e53cc0d5c42f88b41a/data/org.freedesktop.ModemManager1.conf.polkit), [Upstream polkit actions](https://github.com/linux-mobile-broadband/ModemManager/blob/7f0bf17ab518cd78925cf7e53cc0d5c42f88b41a/data/org.freedesktop.ModemManager1.policy.in.in)

**Inference:** a read-only bind of the system-bus socket does not make D-Bus method calls read-only. Policy governs permitted calls. Exposing the host bus must therefore be evaluated as access to host operations, not ordinary configuration-file sharing. Docker bind mounts refer to paths on the daemon host; a remote Docker client cannot thereby expose its own local bus. [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/), [Upstream bus policy](https://github.com/linux-mobile-broadband/ModemManager/blob/7f0bf17ab518cd78925cf7e53cc0d5c42f88b41a/data/org.freedesktop.ModemManager1.conf.polkit)

`mmcli` supports monitoring device additions/removals; its indexes and object paths are created when devices are plugged in. **Inference:** an adapter must rediscover objects after daemon or device restart rather than treating an index as logical cellular-device identity. Whether to use `mmcli` or a D-Bus library remains a design choice. Arbitrary AT passthrough in `mmcli` requires ModemManager debug mode, unlike its ordinary messaging operations. [mmcli manual](https://manpages.debian.org/trixie/modemmanager/mmcli.1.en.html)

Running the daemon itself inside a container is a different arrangement. It requires integrating control-port access and device addition/removal information, plus its D-Bus and authorization environment. ModemManager normally obtains events through udev, with explicit kernel-event reporting available in suitable configurations. **Inference:** installing its package in an image is not sufficient to demonstrate device discovery or reconnect. This research establishes neither impossibility nor a verified daemon-container recipe. [ModemManager detection](https://mobile-broadband.pages.freedesktop.org/docs/modemmanager/port-and-device-detection/), [Upstream kernel-event reporting contract](https://github.com/linux-mobile-broadband/ModemManager/blob/7f0bf17ab518cd78925cf7e53cc0d5c42f88b41a/introspection/org.freedesktop.ModemManager1.xml)

## Installer media and the attached MF833T variant

The archived read-only inventory found Windows setup programs and RNDIS network-driver files, with no discovered Linux utility, serial-driver INF, firmware image or AT manual. The tested `19d2:1405` variant exposed ECM and storage interfaces, no tty control port, and no ModemManager device. Its factory-mode acknowledgements did not produce a verified AT interface. These facts apply to the inspected variant and recorded tests only. [Archived AT and installation-media investigation](../../.v0/docs/at-access-investigation.md)

**Inference:** mounting that media can expose installer files to a container; it does not expose the device's HTTP endpoint or create missing serial interfaces. Mode-switch tooling is useful for some other layouts, but those layouts require their own evidence; the attached variant is not established as such a case. [ModemManager layout and mode-switch documentation](https://mobile-broadband.pages.freedesktop.org/docs/modemmanager/wwan-device-types/)

## Portability and remaining verification

Rootless Docker and user-namespace remapping change host/container identity mapping. Device and D-Bus access must be verified under the chosen runtime; being root inside a container is not a universal host authorization grant. This investigation does not claim rootless device access is impossible. [Docker rootless mode](https://docs.docker.com/engine/security/rootless/), [Docker user namespace remapping](https://docs.docker.com/engine/security/userns-remap/)

Docker Desktop adds a VM/USB forwarding arrangement. Its USB/IP documentation describes additional setup and does not guarantee every USB device. Linux Engine device-path recipes consequently need separate qualification before being offered for Desktop. [Docker Desktop USB/IP](https://docs.docker.com/desktop/features/usbip/)

Before declaring a deployment profile verified, future work needs evidence for: management-address reachability; the selected port or daemon and version; permission identity and authorization; ownership conflicts; unplug/replug and daemon restart; restoration of subscriptions or polling; and model/firmware-specific capabilities. These are open verification requirements, not results produced here. Packaging, daemon placement, reconnect policy and supported platforms remain decisions for the human design tickets.
