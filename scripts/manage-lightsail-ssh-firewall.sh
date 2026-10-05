#!/usr/bin/env bash
# Temporarily expose Lightsail SSH only to the current GitHub runner.
set -euo pipefail

MODE="${1:?usage: manage-lightsail-ssh-firewall.sh open <ipv4>|close}"
RUNNER_IP="${2:-}"
INSTANCE_NAME="${INSTANCE_NAME:?INSTANCE_NAME is required}"
AWS_REGION="${AWS_REGION:-us-east-2}"

command -v aws >/dev/null 2>&1
command -v jq >/dev/null 2>&1

valid_ipv4() {
  local value="$1"
  local o1 o2 o3 o4 extra
  IFS=. read -r o1 o2 o3 o4 extra <<< "$value"
  [[ -z "${extra:-}" && -n "${o1:-}" && -n "${o2:-}" && -n "${o3:-}" && -n "${o4:-}" ]] || return 1
  local octet
  for octet in "$o1" "$o2" "$o3" "$o4"; do
    [[ "$octet" =~ ^[0-9]+$ ]] || return 1
    ((10#$octet >= 0 && 10#$octet <= 255)) || return 1
  done
}

CURRENT_PORTS="$(
  aws lightsail get-instance \
    --instance-name "$INSTANCE_NAME" \
    --region "$AWS_REGION" \
    --query 'instance.networking.ports' \
    --output json
)"

# Refuse to alter a broad TCP range that happens to include port 22.
echo "$CURRENT_PORTS" | jq -e '
  all(.[];
    if (.protocol == "tcp" and .fromPort <= 22 and .toPort >= 22)
    then (.fromPort == 22 and .toPort == 22)
    else true
    end
  )
' >/dev/null

PORT_INFOS="$(
  echo "$CURRENT_PORTS" | jq '
    [
      .[]
      | {
          fromPort,
          toPort,
          protocol,
          cidrs: (.cidrs // []),
          ipv6Cidrs: (.ipv6Cidrs // []),
          cidrListAliases: (.cidrListAliases // [])
        }
    ]
  '
)"

case "$MODE" in
  open)
    valid_ipv4 "$RUNNER_IP" || {
      echo "A valid IPv4 runner address is required." >&2
      exit 2
    }
    RUNNER_CIDR="$RUNNER_IP/32"
    PORT_INFOS="$(
      echo "$PORT_INFOS" | jq --arg cidr "$RUNNER_CIDR" '
        map(
          if (.protocol == "tcp" and .fromPort == 22 and .toPort == 22)
          then .cidrs = [$cidr] | .ipv6Cidrs = [] | .cidrListAliases = []
          else .
          end
        )
        | if any(.[]; .protocol == "tcp" and .fromPort == 22 and .toPort == 22)
          then .
          else . + [{
            fromPort: 22,
            toPort: 22,
            protocol: "tcp",
            cidrs: [$cidr],
            ipv6Cidrs: [],
            cidrListAliases: []
          }]
          end
      '
    )"
    ;;
  close)
    PORT_INFOS="$(
      echo "$PORT_INFOS" | jq '
        map(select(
          (.protocol == "tcp" and .fromPort == 22 and .toPort == 22) | not
        ))
      '
    )"
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    exit 2
    ;;
esac

test "$(echo "$PORT_INFOS" | jq 'length')" -gt 0

aws lightsail put-instance-public-ports \
  --instance-name "$INSTANCE_NAME" \
  --region "$AWS_REGION" \
  --port-infos "$PORT_INFOS" \
  >/dev/null

VERIFY="$(
  aws lightsail get-instance \
    --instance-name "$INSTANCE_NAME" \
    --region "$AWS_REGION" \
    --query 'instance.networking.ports' \
    --output json
)"

if [[ "$MODE" == "open" ]]; then
  echo "$VERIFY" | jq -e --arg cidr "$RUNNER_CIDR" '
    [
      .[]
      | select(.protocol == "tcp" and .fromPort == 22 and .toPort == 22)
    ] as $ssh
    | ($ssh | length) == 1
      and $ssh[0].cidrs == [$cidr]
      and ($ssh[0].ipv6Cidrs // []) == []
      and ($ssh[0].cidrListAliases // []) == []
  ' >/dev/null
  echo "LIGHTSAIL_SSH_RESTRICTED=$RUNNER_CIDR"
else
  echo "$VERIFY" | jq -e '
    all(.[];
      (.protocol == "tcp" and .fromPort <= 22 and .toPort >= 22) | not
    )
  ' >/dev/null
  echo "LIGHTSAIL_SSH_CLOSED"
fi
