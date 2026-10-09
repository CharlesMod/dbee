#!/bin/sh
# nginx is enabled with a new site conf that does not parse, and started: it fails.
# Refused (exit 4) when nginx is not installed or conf.d is absent.
m=/run/.sim/seeded
command -v nginx >/dev/null || { echo "refused: nginx not installed"; exit 4; }
[ -d /etc/nginx/conf.d ] || { echo "refused: no /etc/nginx/conf.d"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim; touch "$m"
cat > /etc/nginx/conf.d/patient-proxy.conf <<'CONF'
server {
    lissten 8081;
    server_name patient.local;
    location / {
        proxy_pass http://127.0.0.1:8080
    }
}
CONF
systemctl enable nginx.service >/dev/null 2>&1
systemctl start nginx.service 2>/dev/null
sleep 2
echo "seeded: nginx $(systemctl is-active nginx.service); $(nginx -t 2>&1 | head -1)"
