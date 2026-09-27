#!/usr/bin/env bash
# Deploy the API container from an immutable ECR image with automatic rollback.
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"
EXPECTED_AWS_ACCOUNT="${EXPECTED_AWS_ACCOUNT:-$AWS_ACCOUNT_ID}"
ECR_REPO="ai-recruiter-api"
ECR_TAG="${ECR_TAG:-latest}"
CONTAINER_NAME="ai-recruiter-api"
NETWORK_NAME="ai-recruiter"
DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
IMPORT_STAGING_BUCKET="${IMPORT_STAGING_BUCKET:?IMPORT_STAGING_BUCKET is required}"
IMPORT_QUEUE_URL="${IMPORT_QUEUE_URL:?IMPORT_QUEUE_URL is required}"
TRAINING_CONTENT_BUCKET="${TRAINING_CONTENT_BUCKET:?TRAINING_CONTENT_BUCKET is required}"
IMPORT_EVALUATION_CONCURRENCY="${IMPORT_EVALUATION_CONCURRENCY:-1}"
PG_POOL_SIZE="${PG_POOL_SIZE:-2}"
PG_MAX_OVERFLOW="${PG_MAX_OVERFLOW:-2}"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET is required}"
KNOWLEDGE_BASE_ID="${KNOWLEDGE_BASE_ID:?KNOWLEDGE_BASE_ID is required}"
DATA_SOURCE_ID="${DATA_SOURCE_ID:?DATA_SOURCE_ID is required}"
COGNITO_USER_POOL_ID="${COGNITO_USER_POOL_ID:?COGNITO_USER_POOL_ID is required}"
COGNITO_CLIENT_ID="${COGNITO_CLIENT_ID:?COGNITO_CLIENT_ID is required}"
ALLOW_PUBLIC_REGISTRATION="${ALLOW_PUBLIC_REGISTRATION:-false}"
RBAC_BOOTSTRAP_ADMIN_EMAILS="${RBAC_BOOTSTRAP_ADMIN_EMAILS:-}"
RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS="${RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS:-}"

HOST_AWS_CONFIG="/opt/ai-recruiter/aws/config"
HOST_SIGNING_HELPER="/usr/local/bin/aws_signing_helper"
HOST_CLIENT_CRT="/opt/ai-recruiter/rolesanywhere/client.crt"
HOST_CLIENT_KEY="/opt/ai-recruiter/rolesanywhere/client.key"
CONTAINER_AWS_CONFIG="/root/.aws/config"
CONTAINER_SIGNING_HELPER="/usr/local/bin/aws_signing_helper"
CONTAINER_CLIENT_CRT="/run/rolesanywhere/client.crt"
CONTAINER_CLIENT_KEY="/run/rolesanywhere/client.key"
BEDROCK_PROFILE="ai-recruiter-bedrock"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_IMAGE="${ECR_REGISTRY}/${ECR_REPO}:${ECR_TAG}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

run_api() {
  local image="$1"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network "$NETWORK_NAME" \
    --add-host=host.docker.internal:host-gateway \
    --pids-limit 256 \
    --log-opt max-size=10m \
    --log-opt max-file=3 \
    -e "DATABASE_URL=$DATABASE_URL" \
    -e "AWS_REGION=$AWS_REGION" \
    -e "BEDROCK_AWS_PROFILE=$BEDROCK_PROFILE" \
    -e "IMPORT_STAGING_BUCKET=$IMPORT_STAGING_BUCKET" \
    -e "IMPORT_QUEUE_URL=$IMPORT_QUEUE_URL" \
    -e "TRAINING_CONTENT_BUCKET=$TRAINING_CONTENT_BUCKET" \
    -e "IMPORT_EVALUATION_CONCURRENCY=$IMPORT_EVALUATION_CONCURRENCY" \
    -e "PG_POOL_SIZE=$PG_POOL_SIZE" \
    -e "PG_MAX_OVERFLOW=$PG_MAX_OVERFLOW" \
    -e "S3_BUCKET=$S3_BUCKET" \
    -e "KNOWLEDGE_BASE_ID=$KNOWLEDGE_BASE_ID" \
    -e "DATA_SOURCE_ID=$DATA_SOURCE_ID" \
    -e "COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID" \
    -e "COGNITO_CLIENT_ID=$COGNITO_CLIENT_ID" \
    -e "ALLOW_PUBLIC_REGISTRATION=$ALLOW_PUBLIC_REGISTRATION" \
    -e "RBAC_BOOTSTRAP_ADMIN_EMAILS=$RBAC_BOOTSTRAP_ADMIN_EMAILS" \
    -e "RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS=$RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS" \
    -v "${HOST_AWS_CONFIG}:${CONTAINER_AWS_CONFIG}:ro" \
    -v "${HOST_SIGNING_HELPER}:${CONTAINER_SIGNING_HELPER}:ro" \
    -v "${HOST_CLIENT_CRT}:${CONTAINER_CLIENT_CRT}:ro" \
    -v "${HOST_CLIENT_KEY}:${CONTAINER_CLIENT_KEY}:ro" \
    "$image"
}

verify_api() {
  [[ "$(docker inspect "$CONTAINER_NAME" --format '{{.State.Status}}' 2>/dev/null || true)" == "running" ]]

  local ready=false
  for _ in $(seq 1 15); do
    if docker exec "$CONTAINER_NAME" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:80/ready', timeout=2).read()" \
      >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  [[ "$ready" == "true" ]] || {
    docker logs --tail 100 "$CONTAINER_NAME" 2>&1 || true
    return 1
  }

  local container_env
  container_env=$(docker inspect "$CONTAINER_NAME" --format '{{range .Config.Env}}{{println .}}{{end}}')
  for required in \
    "BEDROCK_AWS_PROFILE=$BEDROCK_PROFILE" \
    "IMPORT_STAGING_BUCKET=$IMPORT_STAGING_BUCKET" \
    "IMPORT_QUEUE_URL=$IMPORT_QUEUE_URL" \
    "TRAINING_CONTENT_BUCKET=$TRAINING_CONTENT_BUCKET" \
    "IMPORT_EVALUATION_CONCURRENCY=$IMPORT_EVALUATION_CONCURRENCY" \
    "PG_POOL_SIZE=$PG_POOL_SIZE" \
    "PG_MAX_OVERFLOW=$PG_MAX_OVERFLOW" \
    "S3_BUCKET=$S3_BUCKET" \
    "KNOWLEDGE_BASE_ID=$KNOWLEDGE_BASE_ID" \
    "DATA_SOURCE_ID=$DATA_SOURCE_ID" \
    "COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID" \
    "COGNITO_CLIENT_ID=$COGNITO_CLIENT_ID" \
    "ALLOW_PUBLIC_REGISTRATION=$ALLOW_PUBLIC_REGISTRATION" \
    "RBAC_BOOTSTRAP_ADMIN_EMAILS=$RBAC_BOOTSTRAP_ADMIN_EMAILS" \
    "RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS=$RBAC_BOOTSTRAP_SUPER_ADMIN_EMAILS"; do
    echo "$container_env" | grep -Fqx "$required" || {
      echo "Missing runtime env ${required%%=*}" >&2
      return 1
    }
  done

  local caller
  caller=$(docker exec "$CONTAINER_NAME" python -c \
    "from app.infrastructure.bedrock.session import get_cached_session; r=get_cached_session().client('sts', region_name='$AWS_REGION').get_caller_identity(); print(f\"{r['Account']}|{r['Arn']}\")")
  echo "$caller" | grep -q "$EXPECTED_AWS_ACCOUNT" || {
    echo "AWS account mismatch: $caller" >&2
    return 1
  }
  echo "$caller" | grep -q "AiRecruiterBedrockRuntimeRole" || {
    echo "AWS role mismatch: $caller" >&2
    return 1
  }
}

for file in "$HOST_AWS_CONFIG" "$HOST_SIGNING_HELPER" "$HOST_CLIENT_CRT" "$HOST_CLIENT_KEY"; do
  [[ -f "$file" ]] || { echo "Missing required file: $file" >&2; exit 1; }
done
grep -q "$BEDROCK_PROFILE" "$HOST_AWS_CONFIG" || { echo "Missing profile $BEDROCK_PROFILE" >&2; exit 1; }

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY RUN] pull $ECR_IMAGE"
  echo "[DRY RUN] deploy $CONTAINER_NAME with rollback to current image"
  exit 0
fi

AWS_CONFIG_FILE="$HOST_AWS_CONFIG" aws ecr get-login-password --region "$AWS_REGION" --profile "$BEDROCK_PROFILE" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$ECR_IMAGE"
docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || docker network create "$NETWORK_NAME"

OLD_IMAGE=""
if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  OLD_IMAGE=$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}')
fi

rollback_api() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && -n "$OLD_IMAGE" ]]; then
    echo "API deployment failed; restoring $OLD_IMAGE" >&2
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if run_api "$OLD_IMAGE" && verify_api; then
      echo "API_ROLLBACK_OK=$OLD_IMAGE" >&2
    else
      echo "API_ROLLBACK_FAILED=$OLD_IMAGE" >&2
    fi
  fi
  exit "$status"
}
trap rollback_api EXIT

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
run_api "$ECR_IMAGE"
verify_api

trap - EXIT
echo "DEPLOY_API_OK=$ECR_IMAGE"
