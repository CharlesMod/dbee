#!/bin/sh
# Healthy: nginx's config parses, and if nginx is enabled it is running.
t=$(nginx -t 2>&1 | tail -1)
nginx -t >/dev/null 2>&1 && ok=1 || ok=0
en=$(systemctl is-enabled nginx.service 2>/dev/null); act=$(systemctl is-active nginx.service)
echo "nginx $en/$act; config test: $t"
[ "$ok" = 1 ] && { [ "$en" != enabled ] || [ "$act" = active ]; }
