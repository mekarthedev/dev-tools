#!/usr/bin/env bash

set -e
set -x

SELF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPOSITORY_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPOSITORY_ROOT}/.git/hooks"

cp "${SELF_DIR}/commit-msg" "${HOOKS_DIR}"
chmod +x "${HOOKS_DIR}/commit-msg"
