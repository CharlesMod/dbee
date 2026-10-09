#!/bin/sh
# Healthy: no https listener on :8443, or the certificate it serves has not expired.
if ss -ltn 'sport = :8443' | grep -q LISTEN; then
    end=$(echo | openssl s_client -connect 127.0.0.1:8443 -servername localhost 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null)
    if echo | openssl s_client -connect 127.0.0.1:8443 -servername localhost 2>/dev/null | openssl x509 -noout -checkend 0 >/dev/null 2>&1; then ok=1; else ok=0; fi
    echo ":8443 serves a cert, ${end:-no cert}; valid now: $ok"
    [ "$ok" = 1 ]
elif [ -e /etc/ssl/patient/server.crt ]; then
    echo ":8443 not listening but /etc/ssl/patient/server.crt is deployed"; exit 1
else
    echo "no https site on :8443"; exit 0
fi
