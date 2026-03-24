#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DEFAULT_VERSION="$(sed -n 's/  "version": "\(.*\)",/\1/p' install.json | head -n 1)"
if [[ -z "${DEFAULT_VERSION}" ]]; then
  echo "Unable to resolve version from install.json" >&2
  exit 1
fi

REGISTRY_HOST="${REGISTRY_HOST:-registry.maxsale.vn}"
IMAGE_REPO="${IMAGE_REPO:-${REGISTRY_HOST}/tools/cpa-x}"
IMAGE_TAG="${IMAGE_TAG:-v${DEFAULT_VERSION}}"
REGISTRY_USERNAME="${REGISTRY_USERNAME:-}"
REGISTRY_PASSWORD="${REGISTRY_PASSWORD:-}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
PUSH_LATEST="${PUSH_LATEST:-false}"

if [[ -z "${REGISTRY_USERNAME}" || -z "${REGISTRY_PASSWORD}" ]]; then
  echo "REGISTRY_USERNAME and REGISTRY_PASSWORD are required to publish ${IMAGE_REPO}:${IMAGE_TAG}" >&2
  exit 1
fi

printf '%s' "${REGISTRY_PASSWORD}" | docker login "${REGISTRY_HOST}" -u "${REGISTRY_USERNAME}" --password-stdin

if docker buildx inspect cpax-publisher >/dev/null 2>&1; then
  docker buildx use cpax-publisher >/dev/null
else
  docker buildx create --name cpax-publisher --use >/dev/null
fi

TAGS=(-t "${IMAGE_REPO}:${IMAGE_TAG}")
if [[ "${PUSH_LATEST}" == "true" ]]; then
  TAGS+=(-t "${IMAGE_REPO}:latest")
fi

docker buildx build \
  --platform "${PLATFORMS}" \
  --build-arg "PANEL_VERSION=${IMAGE_TAG#v}" \
  "${TAGS[@]}" \
  --push \
  .

echo "Published ${IMAGE_REPO}:${IMAGE_TAG}"
if [[ "${PUSH_LATEST}" == "true" ]]; then
  echo "Published ${IMAGE_REPO}:latest"
fi
