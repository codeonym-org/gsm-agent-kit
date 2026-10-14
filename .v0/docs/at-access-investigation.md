# MF833T AT access investigation

Inspected and tested on 2026-10-13 against the attached inwi MF833T,
firmware `BD_WANAMARMF833TV1.0.0B04`, hardware `djtA`.

## Verified on this device

- USB ID `19d2:1405`, one configuration, three interfaces: CDC ECM
  control/data and USB mass storage. No vendor serial or ADB interface.
- No `/dev/ttyUSB*` or `/dev/ttyACM*`; ModemManager finds no modem.
- TCP connection attempts to 22, 23, 2323, 4719 and 5555 did not succeed;
  HTTP port 80 is reachable. This is not a scan of every possible port.
- Read requests for `debug_enable`, `usb_mode` and `device_mode` returned
  empty values, so the original setting cannot be read through these keys.
- POST `SET_DEVICE_MODE` with `debug_enable=1` acknowledged success but
  produced no new USB interfaces, no ADB device, and no reachable network
  ADB/Telnet port. Sent `debug_enable=0` afterward; it also acknowledged
  success. Acknowledgements do not prove this firmware implements the toggle.
- POST `USB_MODE_SWITCH` with `usb_mode=6` returned `result: failure`.
- Final verification: USB ID and interfaces unchanged, no serial ports,
  no ModemManager device; status and inbox APIs still work. No SMS was sent,
  marked read, or deleted by these probes.

AT command access was **not achieved**. Installing a terminal or serial
library cannot create a missing device interface. Forcing a serial driver
onto the existing ECM/storage interfaces is not justified by their descriptors.

## Sources and applicability

- [ZTE debug toggle reference](https://github.com/riuzenn/zte-4g-portable-wifi-advanced-webui):
  maintainer tests F30A Pro only. It documents enable/disable requests and
  an AT utility running inside the device. This is not MF833T support.
- [MF823 USB mode reference](https://github.com/zetxx/router-rpi-4G/blob/master/zte-mf-823-cmd.md):
  mode 6 includes Ethernet, diagnostic, command and ADB interfaces on that
  model. The attached MF833T rejected it. Mode numbers are firmware-specific.
- [First-hand MF833T diagnostic-mode report](https://forum.dc-unlocker.com/forum/modems-and-phones/zte/168885-unable-to-exit-the-diagnostic-mode):
  owner reports USB-AT and USB-LOG after enabling diagnostics, but inability
  to return to normal mode. Their recovery commands failed; this does not
  establish a usable reversible procedure for our inwi variant.

## Authorized factory-mode experiment

The user subsequently explicitly authorized factory diagnostic experimentation
after being informed of the missing recovery procedure.

- POST and GET `goform_set_cmd_process` with `USB_MODE_SWITCH` and
  `usb_mode=FACTORY` both returned `result: failure`.
- GET `goform_process` with `goformId=MODE_SWITCH` and `switchCmd=FACTORY`
  returned `result: FACTORY:ok`. This alternative appears in
  [bkerler's diagnostic tooling](https://github.com/bkerler/edl/blob/master/edlclient/Tools/boottodwnload.py).
- No interfaces changed after waiting. Sent one `REBOOT_DEVICE` request,
  acknowledged success, to test whether the setting applies at startup.
- A probe during restart encountered an HTTP redirect to HTTPS. Once the
  modem route returned, identity/status/inbox probes succeeded again over HTTP.
- Final USB ID remains `19d2:1405`; ECM and storage interfaces remain,
  no USB serial ports appeared, and ModemManager still finds no modem.
- No AT commands could be sent without an AT interface. No firmware was
  flashed, no driver was rebound, and no SMS was sent or deleted by the probes.

The `FACTORY:ok` acknowledgement is not proof of a working mode switch. We
cannot verify an internal persistent setting through the mode query keys.
No download/bootloader transition was attempted.

## Mounted installation media

Inspected all 32 files at `/run/media/codeonym/inwi 4G MF833T` read-only.
No Windows executable was run.

- The volume contains Windows autorun/setup programs, icons, a web launcher,
  two architecture-specific driver installers, and RNDIS INF/catalog files.
- `Data/CONFIG.INI` identifies the package as
  `PCW_WANAMRCMF833TV1.0.0B02`, points to `http://192.168.0.1`, and sets
  `RNDISPORT_PID=PID_1403`. This is the host software version, not the modem's
  installed `BD_...B04` firmware.
- `AutoRun.dat` references `USB\\Vid_19D2&Pid_0016`; that is an installer
  matching hint, not proof that our device exposes a usable diagnostic mode.
- Both `zterndis.inf` files install a network-class driver for
  `19d2:1403` and `19d2:1404`, interface 00. They do not install a COM/AT driver.
- `ResetCDROM.exe` imports `mciSendCommandA` and contains `ejectdisk` class
  names, consistent with a CD eject/reset helper rather than an AT terminal.
  Its behavior was not tested by execution.
- ASCII/UTF-16 string inspection of all bundled executables found no explicit
  AT-command or factory-switch instructions. No ZIP/CAB/7z signatures were
  found in these executables; `Setup.exe` is not recognized as an archive by
  `bsdtar`. These checks are not exhaustive reverse engineering.
- No firmware image, Linux utility, serial-driver INF, or AT manual was found
  in the mounted file inventory.

The additional USB IDs are useful clues for future interface investigation,
but this media does not supply the missing AT interface or a verified switch.

Shell access, if obtained, could instead allow inspection of internal AT devices
without replacing the current USB network configuration. No shell access exists
through the ports tested above.
