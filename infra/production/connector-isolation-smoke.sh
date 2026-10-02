#!/bin/bash
# Synthetic-only EC2 network prerequisite probe. Run after EC2 IMDS is disabled.
set -euo pipefail
exec > >(tee /var/log/neraium-connector-isolation.log /dev/console) 2>&1

echo NERAIUM_CONNECTOR_BOOTSTRAP_READY
for attempt in $(seq 1 120); do
  if ! curl --noproxy '*' --fail --max-time 1 -sS -o /dev/null -X PUT \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
    http://169.254.169.254/latest/api/token 2>/dev/null; then
    break
  fi
  sleep 2
done

useradd --system --no-create-home --shell /sbin/nologin connector-probe
if ! command -v iptables >/dev/null; then
  echo 'NERAIUM_CONNECTOR_POLICY_FAIL: iptables unavailable'
  exit 1
fi
# This owner rule applies to the process that performs connector HTTP, including
# direct sockets that bypass application URL validation. DNS remains available
# to the VPC resolver; DNS answers are checked again by the application policy.
iptables -I OUTPUT 1 -m owner --uid-owner connector-probe -d 169.254.0.0/16 -j REJECT
iptables -I OUTPUT 2 -m owner --uid-owner connector-probe -d 127.0.0.53/32 -p udp --dport 53 -j ACCEPT
iptables -I OUTPUT 3 -m owner --uid-owner connector-probe -d 127.0.0.0/8 -j REJECT
iptables -I OUTPUT 4 -m owner --uid-owner connector-probe -d 10.40.0.2/32 -p udp --dport 53 -j ACCEPT
iptables -I OUTPUT 5 -m owner --uid-owner connector-probe -d 10.0.0.0/8 -j REJECT
iptables -I OUTPUT 6 -m owner --uid-owner connector-probe -d 172.16.0.0/12 -j REJECT
iptables -I OUTPUT 7 -m owner --uid-owner connector-probe -d 192.168.0.0/16 -j REJECT
mapfile -t synthetic_ips < <(getent ahostsv4 bfzcudq5o2.execute-api.us-east-2.amazonaws.com | awk '{print $1}' | sort -u)
if [ "${#synthetic_ips[@]}" -eq 0 ]; then
  echo 'NERAIUM_CONNECTOR_POLICY_FAIL: synthetic DNS unavailable'
  exit 1
fi
for ip in "${synthetic_ips[@]}"; do
  iptables -I OUTPUT 8 -m owner --uid-owner connector-probe -d "$ip"/32 -p tcp --dport 443 -j ACCEPT
done
iptables -A OUTPUT -m owner --uid-owner connector-probe -p tcp --dport 443 -j REJECT

failures=0
probe() {
  local label="$1" url="$2" expected="$3" status
  status=$(runuser -u connector-probe -- curl --noproxy '*' --max-time 5 --connect-timeout 2 -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null) && result=0 || result=$?
  if [ "$expected" = allow ] && [ "$result" -eq 0 ] && [ "$status" = 200 ]; then
    echo "$label: PASS"
  elif [ "$expected" = deny ] && [ "$result" -ne 0 ]; then
    echo "$label: PASS"
  else
    echo "$label: FAIL (curl_exit=$result http_status=$status)"
    failures=$((failures + 1))
  fi
}

probe APPROVED_SYNTHETIC_HTTPS https://bfzcudq5o2.execute-api.us-east-2.amazonaws.com/telemetry allow
probe UNAPPROVED_PUBLIC_HTTPS https://example.com/ deny
probe PRIVATE_INTERNAL https://10.40.0.1/ deny
probe EC2_METADATA http://169.254.169.254/latest/meta-data/ deny
probe ECS_FARGATE_METADATA http://169.254.170.2/v2/metadata deny
echo NERAIUM_CONNECTOR_PROBES_COMPLETE
exit "$failures"
