#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/neraium-connector-executor-bootstrap.log | logger -t user-data -s 2>/dev/console) 2>&1

REGION='__REGION__'
IMAGE='__IMAGE__'
AUTH_SECRET_ARN='__AUTH_SECRET_ARN__'
TLS_SECRET_ARN='__TLS_SECRET_ARN__'
APPROVED_HOST='bfzcudq5o2.execute-api.us-east-2.amazonaws.com'

for bin in aws docker iptables ip6tables jq curl; do command -v "$bin" >/dev/null; done
systemctl disable --now ecs || true
install -d -m 0700 /var/lib/neraium-connector /run/neraium-connector-cert

# Only the root broker can use instance credentials or read secrets. Connector
# child processes (uid 10002) may reach DNS and the pinned approved endpoint.
TLS_JSON="$(aws secretsmanager get-secret-value --region "$REGION" --secret-id "$TLS_SECRET_ARN" --query SecretString --output text)"
printf '%s' "$TLS_JSON" | jq -er '.key_pem' > /run/neraium-connector-cert/server.key
printf '%s' "$TLS_JSON" | jq -er '.cert_pem' > /run/neraium-connector-cert/server.crt
unset TLS_JSON
chmod 0600 /run/neraium-connector-cert/server.key
chmod 0644 /run/neraium-connector-cert/server.crt

cat >/usr/local/sbin/neraium-connector-egress-firewall <<'FIREWALL'
#!/bin/bash
set -euo pipefail
APPROVED_HOST='bfzcudq5o2.execute-api.us-east-2.amazonaws.com'
mapfile -t approved_ips < <(getent ahostsv4 "$APPROVED_HOST" | awk '{print $1}' | sort -u)
if [ "${#approved_ips[@]}" -eq 0 ]; then
  echo 'Connector egress policy update failed: approved destination DNS unavailable.' >&2
  exit 1
fi

active=''
if iptables -C OUTPUT -m owner --uid-owner 10002 -j NERAIUM_CONNECTOR_A 2>/dev/null; then
  active=A
elif iptables -C OUTPUT -m owner --uid-owner 10002 -j NERAIUM_CONNECTOR_B 2>/dev/null; then
  active=B
fi
next=A
if [ "$active" = A ]; then next=B; fi
chain="NERAIUM_CONNECTOR_${next}"
iptables -N "$chain" 2>/dev/null || true
iptables -F "$chain"
iptables -A "$chain" -d 127.0.0.53/32 -p udp --dport 53 -j ACCEPT
iptables -A "$chain" -d 127.0.0.53/32 -p tcp --dport 53 -j ACCEPT
iptables -A "$chain" -d 10.40.0.2/32 -p udp --dport 53 -j ACCEPT
iptables -A "$chain" -d 10.40.0.2/32 -p tcp --dport 53 -j ACCEPT
iptables -A "$chain" -d 169.254.0.0/16 -j REJECT
iptables -A "$chain" -d 127.0.0.0/8 -j REJECT
iptables -A "$chain" -d 10.0.0.0/8 -j REJECT
iptables -A "$chain" -d 172.16.0.0/12 -j REJECT
iptables -A "$chain" -d 192.168.0.0/16 -j REJECT
valid_ip_count=0
for ip in "${approved_ips[@]}"; do
  if python3 -c 'import ipaddress,sys; raise SystemExit(0 if ipaddress.ip_address(sys.argv[1]).is_global else 1)' "$ip"; then
    iptables -A "$chain" -d "$ip"/32 -p tcp --dport 443 -j ACCEPT
    valid_ip_count=$((valid_ip_count + 1))
  fi
done
if [ "$valid_ip_count" -eq 0 ]; then
  echo 'Connector egress policy update failed: approved destination DNS was unsafe.' >&2
  exit 1
fi
iptables -A "$chain" -j REJECT
if [ -n "$active" ]; then
  # Match the actual owner hook; never assume another owner's rule index.
  # Both chains deny by default during replacement, so failure stays closed.
  iptables -I OUTPUT 1 -m owner --uid-owner 10002 -j "$chain"
  iptables -D OUTPUT -m owner --uid-owner 10002 -j "NERAIUM_CONNECTOR_${active}"
else
  iptables -I OUTPUT 1 -m owner --uid-owner 10002 -j "$chain"
fi
iptables -D OUTPUT -m owner --uid-owner 10002 -j NERAIUM_CONNECTOR 2>/dev/null || true
iptables -F NERAIUM_CONNECTOR 2>/dev/null || true
iptables -X NERAIUM_CONNECTOR 2>/dev/null || true
ip6tables -N NERAIUM_CONNECTOR 2>/dev/null || true
ip6tables -C NERAIUM_CONNECTOR -j REJECT 2>/dev/null || ip6tables -A NERAIUM_CONNECTOR -j REJECT
ip6tables -C OUTPUT -m owner --uid-owner 10002 -j NERAIUM_CONNECTOR 2>/dev/null || ip6tables -I OUTPUT 1 -m owner --uid-owner 10002 -j NERAIUM_CONNECTOR

# Root broker needs instance identity and reviewed AWS services, but no general
# outbound sockets or database access. Endpoint policies/IAM constrain AWS API
# privileges independently. Private DNS activation also needs qualified NACLs.
root_active=''
for suffix in A B; do
  if iptables -C OUTPUT -m owner --uid-owner 0 -j "NERAIUM_BROKER_${suffix}" 2>/dev/null; then root_active="$suffix"; fi
done
root_next=A
if [ "$root_active" = A ]; then root_next=B; fi
root_chain="NERAIUM_BROKER_${root_next}"
iptables -N "$root_chain" 2>/dev/null || true
iptables -F "$root_chain"
iptables -A "$root_chain" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
for resolver in 127.0.0.53 10.40.0.2; do
  iptables -A "$root_chain" -d "$resolver"/32 -p udp --dport 53 -j ACCEPT
  iptables -A "$root_chain" -d "$resolver"/32 -p tcp --dport 53 -j ACCEPT
done
iptables -A "$root_chain" -d 169.254.169.254/32 -p tcp --dport 80 -j ACCEPT
iptables -A "$root_chain" -d 10.40.32.20/32 -p tcp --dport 8443 -j ACCEPT
for hostname in api.ecr.us-east-2.amazonaws.com \
  680779862188.dkr.ecr.us-east-2.amazonaws.com \
  prod-us-east-2-starport-layer-bucket.s3.us-east-2.amazonaws.com \
  logs.us-east-2.amazonaws.com secretsmanager.us-east-2.amazonaws.com; do
  mapfile -t service_ips < <(getent ahostsv4 "$hostname" | awk '{print $1}' | sort -u)
  service_ip_count=0
  for ip in "${service_ips[@]}"; do
    if python3 -c 'import ipaddress,sys; a=ipaddress.ip_address(sys.argv[1]); raise SystemExit(0 if a.is_global or a in ipaddress.ip_network("10.40.0.0/16") else 1)' "$ip"; then
      iptables -A "$root_chain" -d "$ip"/32 -p tcp --dport 443 -j ACCEPT
      service_ip_count=$((service_ip_count + 1))
    fi
  done
  if [ "$service_ip_count" -eq 0 ]; then exit 1; fi
done
iptables -A "$root_chain" -j REJECT
iptables -I OUTPUT 1 -m owner --uid-owner 0 -j "$root_chain"
if [ -n "$root_active" ]; then
  iptables -D OUTPUT -m owner --uid-owner 0 -j "NERAIUM_BROKER_${root_active}"
fi
ip6tables -N NERAIUM_BROKER 2>/dev/null || true
ip6tables -C NERAIUM_BROKER -j REJECT 2>/dev/null || ip6tables -A NERAIUM_BROKER -j REJECT
ip6tables -C OUTPUT -m owner --uid-owner 0 -j NERAIUM_BROKER 2>/dev/null || ip6tables -I OUTPUT 1 -m owner --uid-owner 0 -j NERAIUM_BROKER
FIREWALL
chmod 0755 /usr/local/sbin/neraium-connector-egress-firewall
cat >/etc/systemd/system/neraium-connector-firewall.service <<'UNIT'
[Unit]
Description=Neraium isolated connector process egress policy
DefaultDependencies=no
After=network-online.target
Before=docker.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/neraium-connector-egress-firewall
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now neraium-connector-firewall.service
cat >/etc/systemd/system/neraium-connector-firewall.timer <<'TIMER'
[Unit]
Description=Refresh the approved synthetic connector destination IP allowlist

[Timer]
OnBootSec=60s
OnUnitActiveSec=60s
Unit=neraium-connector-firewall.service

[Install]
WantedBy=timers.target
TIMER
systemctl daemon-reload
systemctl enable --now neraium-connector-firewall.timer

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "680779862188.dkr.ecr.${REGION}.amazonaws.com"
docker pull "$IMAGE"
docker run -d --name neraium-connector-executor --restart unless-stopped \
  --network host --user 0:0 --cap-drop ALL --cap-add SETUID --cap-add SETGID \
  --security-opt no-new-privileges --read-only --pids-limit 128 \
  --mount type=bind,src=/var/lib/neraium-connector,dst=/var/lib/neraium-connector \
  --mount type=bind,src=/run/neraium-connector-cert,dst=/run/neraium-connector-cert,readonly \
  -e AWS_REGION="$REGION" -e NERAIUM_CONNECTOR_EXECUTOR_AUTH_SECRET_ARN="$AUTH_SECRET_ARN" \
  -e AWS_EC2_METADATA_V1_DISABLED=true \
  -e NERAIUM_CONNECTOR_EXECUTOR_REPLAY_DB=/var/lib/neraium-connector/replay.sqlite3 \
  "$IMAGE" python -c 'import uvicorn; from app.services.connector_execution import build_executor_app; uvicorn.run(build_executor_app(), host="0.0.0.0", port=8443, ssl_keyfile="/run/neraium-connector-cert/server.key", ssl_certfile="/run/neraium-connector-cert/server.crt", access_log=False, log_level="warning")'

for _ in $(seq 1 30); do
  if curl --fail --silent --cacert /run/neraium-connector-cert/server.crt https://10.40.32.20:8443/health >/dev/null; then exit 0; fi
  sleep 2
done
exit 1
