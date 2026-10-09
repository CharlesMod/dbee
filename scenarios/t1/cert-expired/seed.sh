#!/bin/sh
mkdir -p /run/.sim
# nginx serves https on :8443 with a self-signed certificate that has already expired
# (trusted by the system, as an internal CA cert would be); patient-fetch curls it and fails.
# Refused (exit 4) without openssl, nginx or update-ca-certificates.
m=/run/.sim/seeded
for c in openssl nginx update-ca-certificates; do command -v $c >/dev/null || { echo "refused: no $c"; exit 4; }; done
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim /etc/ssl/patient; touch "$m"
# valid for zero days: notBefore = notAfter = now, so it is expired a second later
openssl req -new -newkey rsa:2048 -nodes -subj "/CN=localhost" \
    -keyout /etc/ssl/patient/server.key -out /etc/ssl/patient/server.csr 2>/dev/null
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\n' > /etc/ssl/patient/san.cnf
openssl x509 -req -in /etc/ssl/patient/server.csr -signkey /etc/ssl/patient/server.key -days 0 \
    -extfile /etc/ssl/patient/san.cnf -out /etc/ssl/patient/server.crt 2>/dev/null
rm -f /etc/ssl/patient/server.csr /etc/ssl/patient/san.cnf
chmod 600 /etc/ssl/patient/server.key
sleep 2
cp /etc/ssl/patient/server.crt /usr/local/share/ca-certificates/patient.crt
update-ca-certificates >/dev/null 2>&1
cat > /etc/nginx/conf.d/patient-tls.conf <<'CONF'
server {
    listen 8443 ssl;
    server_name localhost;
    ssl_certificate /etc/ssl/patient/server.crt;
    ssl_certificate_key /etc/ssl/patient/server.key;
    location / { proxy_pass http://127.0.0.1:8080; }
}
CONF
systemctl enable nginx.service >/dev/null 2>&1
systemctl start nginx.service 2>/dev/null
cat > /etc/systemd/system/patient-fetch.service <<'UNIT'
[Unit]
Description=Patient fetch: pull the day's file from our own https site

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -fsS --max-time 8 -o /dev/null https://localhost:8443/
UNIT
systemctl daemon-reload
systemctl start patient-fetch.service 2>/dev/null
echo "seeded: nginx $(systemctl is-active nginx.service); cert $(openssl x509 -in /etc/ssl/patient/server.crt -noout -enddate); patient-fetch $(systemctl is-failed patient-fetch.service)"
