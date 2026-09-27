#!/usr/bin/env bash
# Deploy frontend container and automatically restore the previous image on failure.
set -euo pipefail

ECR_REGISTRY="${ECR_REGISTRY:?ECR_REGISTRY is required}"
ECR_FRONTEND_REPO="${ECR_FRONTEND_REPO:-ai-recruiter-frontend}"
ECR_TAG="${ECR_TAG:?ECR_TAG is required}"
CONTAINER_NAME="ai-recruiter-web"
NETWORK_NAME="ai-recruiter"
IMAGE="${ECR_REGISTRY}/${ECR_FRONTEND_REPO}:${ECR_TAG}"

run_frontend() {
  local image="$1"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$NETWORK_NAME" \
    --restart unless-stopped \
    --pids-limit 128 \
    --log-opt max-size=10m \
    --log-opt max-file=3 \
    -p 80:80 \
    "$image"
}

verify_frontend() {
  local html=""
  local ready=false
  for _ in $(seq 1 15); do
    html=$(curl -fS http://127.0.0.1/ 2>/dev/null || true)
    if echo "$html" | grep -q 'id="root"'; then
      ready=true
      break
    fi
    sleep 1
  done
  [[ "$ready" == "true" ]]
  echo "$html" | grep -q 'id="root"'
}

OLD_IMAGE=""
if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  OLD_IMAGE=$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}')
fi

rollback_frontend() {
  local status=$?
  if [[ "$status" -ne 0 && -n "$OLD_IMAGE" ]]; then
    echo "Frontend deployment failed; restoring $OLD_IMAGE" >&2
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if run_frontend "$OLD_IMAGE" && verify_frontend; then
      echo "FRONTEND_ROLLBACK_OK=$OLD_IMAGE" >&2
    else
      echo "FRONTEND_ROLLBACK_FAILED=$OLD_IMAGE" >&2
    fi
  fi
  exit "$status"
}
trap rollback_frontend EXIT

docker pull "$IMAGE"
docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || docker network create "$NETWORK_NAME"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
run_frontend "$IMAGE"
verify_frontend

CURRENT_IMAGE=$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}')
[[ "$CURRENT_IMAGE" == "$IMAGE" ]]

trap - EXIT
echo "DEPLOY_FRONTEND_OK=$CURRENT_IMAGE"
