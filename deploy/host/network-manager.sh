#!/usr/bin/env bash
# Opt-in host configuration. Never run by containers or the smoke test.
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: network-manager.sh MODE CONNECTION_UUID [--dry-run]

Modes:
  status          Show this profile's routing/DNS settings and active routes.
  fallback-modem  Keep a default route at metric 1000 and DNS priority 1000.
  prefer-wifi     Remove the modem's default routes; management network stays.
  prefer-modem    Prefer the modem with route metric 100 and DNS priority 10.
  reset           Return both IP families to automatic metrics/DNS priorities.

Find UUIDs with: nmcli -f NAME,UUID,TYPE,DEVICE connection show
Changes persist in NetworkManager. Active devices are reapplied without a
disconnect/reconnect. Inactive profiles take effect on their next activation.
Reset restores automatic defaults, not arbitrary prior custom settings.
USAGE
}

mode=${1:-}
connection_uuid=${2:-}
dry_run=${3:-}
if [[ $mode == --help || $mode == -h ]]; then
    usage
    exit 0
fi
case "$mode" in
    status|fallback-modem|prefer-wifi|prefer-modem|reset) ;;
    *) usage >&2; exit 2 ;;
esac
if [[ ! $connection_uuid =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]] \
    || [[ $# -gt 3 ]] || [[ -n $dry_run && $dry_run != --dry-run ]]; then
    usage >&2
    exit 2
fi

profile_type=$(nmcli -w 5 -g connection.type connection show uuid "$connection_uuid")
if [[ $profile_type != 802-3-ethernet ]]; then
    echo 'Expected a wired/USB-network profile; refusing to modify another connection type.' >&2
    exit 2
fi

fields=connection.id,connection.uuid,connection.interface-name
fields+=,ipv4.never-default,ipv4.route-metric,ipv4.dns-priority
fields+=,ipv6.never-default,ipv6.route-metric,ipv6.dns-priority
nmcli -w 5 -f "$fields" connection show uuid "$connection_uuid"
if [[ $mode == status ]]; then
    ip -4 route show default
    ip -6 route show default
    exit 0
fi

never_default=no
case "$mode" in
    fallback-modem) metric=1000; dns_priority=1000 ;;
    prefer-wifi) never_default=yes; metric=1000; dns_priority=1000 ;;
    prefer-modem) metric=100; dns_priority=10 ;;
    reset) metric=-1; dns_priority=0 ;;
esac
command=(nmcli -w 10 connection modify uuid "$connection_uuid"
    ipv4.never-default "$never_default" ipv4.route-metric "$metric" ipv4.dns-priority "$dns_priority"
    ipv6.never-default "$never_default" ipv6.route-metric "$metric" ipv6.dns-priority "$dns_priority")
if [[ $dry_run == --dry-run ]]; then
    printf 'Would run: '
    printf '%q ' "${command[@]}"
    printf '\nThen reapply active devices; inactive profiles stay inactive.\n'
    exit 0
fi

"${command[@]}"
devices=$(nmcli -w 5 -g GENERAL.DEVICES connection show uuid "$connection_uuid")
if [[ -z $devices || $devices == -- ]]; then
    echo 'Profile saved. It will take effect when this connection is activated.'
else
    while IFS= read -r device; do
        if ! nmcli -w 10 device reapply "$device"; then
            echo 'Profile saved, but live reapply failed. Reactivate this profile to apply it.' >&2
            exit 1
        fi
    done <<< "$devices"
fi
