#!/bin/sh
# Healthy: resolv.conf no longer names the unreachable nameserver. Prints what it read.
ns=$(grep -E '^nameserver' /etc/resolv.conf | tr '\n' ' ')
f=$(systemctl is-failed patient-fetch.service 2>/dev/null)
echo "resolv.conf: ${ns:-no nameserver}; patient-fetch ${f:-absent}"
! grep -qE '^nameserver[[:space:]]+192\.0\.2\.1' /etc/resolv.conf
