#!/usr/bin/env bash
#
# network_manager.sh - Manage routing priority between Wi-Fi and USB 4G Modem
#

set -e

# Identify the modem connection (Wired connection 1 or by interface enp3s0f3u3)
MODEM_CON="Wired connection 1"

show_status() {
    echo "=== Network Connections ==="
    nmcli -p con show --active
    echo ""
    echo "=== Default IPv4 Gateway / Route ==="
    ip route show default || echo "No default route found."
    echo ""
    echo "=== Modem Connection Settings ($MODEM_CON) ==="
    nmcli connection show "$MODEM_CON" 2>/dev/null | grep -E 'ipv4.never-default|ipv4.route-metric' || echo "Modem connection not found."
}

set_prefer_wifi() {
    echo "[*] Setting Wi-Fi as default (ignoring modem default gateway)..."
    nmcli connection modify "$MODEM_CON" ipv4.never-default yes
    nmcli connection up "$MODEM_CON" >/dev/null 2>&1 || true
    echo "[✓] Done! Wi-Fi will handle internet traffic. Modem is reachable locally."
}

set_prefer_modem() {
    echo "[*] Setting 4G Modem as primary internet (undoing never-default)..."
    nmcli connection modify "$MODEM_CON" ipv4.never-default no
    nmcli connection modify "$MODEM_CON" ipv4.route-metric 100
    nmcli connection up "$MODEM_CON" >/dev/null 2>&1 || true
    echo "[✓] Done! 4G Modem is now the default internet gateway."
}

set_fallback_modem() {
    echo "[*] Configuring Wi-Fi as primary with 4G Modem as automatic fallback..."
    nmcli connection modify "$MODEM_CON" ipv4.never-default no
    nmcli connection modify "$MODEM_CON" ipv4.route-metric 1000
    nmcli connection up "$MODEM_CON" >/dev/null 2>&1 || true
    echo "[✓] Done! Wi-Fi has metric ~600, Modem has metric 1000 (used when Wi-Fi drops)."
}

usage() {
    echo "Usage: $0 {status|prefer-wifi|prefer-modem|fallback-modem}"
    echo ""
    echo "Commands:"
    echo "  status          - Show active connections and current default gateway"
    echo "  prefer-wifi     - (Option A) Wi-Fi handles internet; modem is secondary (never-default=yes)"
    echo "  prefer-modem    - (Undo) Revert to 4G Modem as primary internet (never-default=no)"
    echo "  fallback-modem  - (Option B) Use Wi-Fi normally; fallback to 4G if Wi-Fi disconnects"
    echo ""
    echo "Raw CLI commands:"
    echo "  To make Wi-Fi primary:      nmcli connection modify \"$MODEM_CON\" ipv4.never-default yes && nmcli con up \"$MODEM_CON\""
    echo "  To undo (4G Modem primary): nmcli connection modify \"$MODEM_CON\" ipv4.never-default no && nmcli con up \"$MODEM_CON\""
    echo "  To set as fallback (B):     nmcli connection modify \"$MODEM_CON\" ipv4.route-metric 1000 && nmcli con up \"$MODEM_CON\""
}

case "$1" in
    status)
        show_status
        ;;
    prefer-wifi)
        set_prefer_wifi
        ;;
    prefer-modem|undo)
        set_prefer_modem
        ;;
    fallback-modem)
        set_fallback_modem
        ;;
    *)
        usage
        exit 1
        ;;
esac
