#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION_FILE="${REPO_ROOT}/VERSION"
OUTPUT_DIR="${REPO_ROOT}/dist"
VERSION=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [--version X.Y.Z] [--output-dir path]

Creates a versioned release tarball with install scripts and full runtime source.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${VERSION}" ]]; then
  if [[ ! -f "${VERSION_FILE}" ]]; then
    echo "Missing VERSION file at ${VERSION_FILE}" >&2
    exit 1
  fi
  VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}")"
fi

if [[ -z "${VERSION}" ]]; then
  echo "Version is empty" >&2
  exit 1
fi

BUNDLE_NAME="agentzero-governed-v${VERSION}"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agentzero-dist-build.XXXXXX")"
STAGE_DIR="${BUILD_ROOT}/${BUNDLE_NAME}"
ARCHIVE_PATH="${OUTPUT_DIR}/${BUNDLE_NAME}.tar.gz"

mkdir -p "${STAGE_DIR}"
mkdir -p "${OUTPUT_DIR}"

# Copy repository snapshot excluding machine-local/runtime artifacts.
# Use tar pipe to avoid requiring rsync in the container image.
(
  cd "${REPO_ROOT}"
  tar -cf - \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='.pytest_cache' \
    --exclude='.dist-build' \
    --exclude='dist' \
    --exclude='client-data' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='tmp' \
    --exclude='__pycache__' \
    --exclude='.mypy_cache' \
    --exclude='.ruff_cache' \
    --exclude='usr/chats' \
    --exclude='*.pyc' \
    . | (cd "${STAGE_DIR}" && tar -xf -)
)

# Keep runtime data excluded, but explicitly include required Temporal config seed.
if [[ -f "${REPO_ROOT}/data/temporal/dynamicconfig/development.yaml" ]]; then
  mkdir -p "${STAGE_DIR}/data/temporal/dynamicconfig"
  cp "${REPO_ROOT}/data/temporal/dynamicconfig/development.yaml" \
    "${STAGE_DIR}/data/temporal/dynamicconfig/development.yaml"
fi

# Ensure generated artifacts are fresh.
rm -f "${ARCHIVE_PATH}"
(
  cd "${BUILD_ROOT}"
  tar -czf "${ARCHIVE_PATH}" "${BUNDLE_NAME}"
)

SHA256="$(sha256sum "${ARCHIVE_PATH}" | awk '{print $1}')"
cat > "${OUTPUT_DIR}/${BUNDLE_NAME}.sha256" <<EOF
${SHA256}  ${BUNDLE_NAME}.tar.gz
EOF

cat <<EOF
{
  "ok": true,
  "version": "${VERSION}",
  "bundle": "${ARCHIVE_PATH}",
  "sha256": "${SHA256}"
}
EOF

rm -rf "${BUILD_ROOT}"
