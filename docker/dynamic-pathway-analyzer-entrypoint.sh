#!/bin/sh
set -eu

runtime_uid="${DYNAMIC_PATHWAY_UID:-1000}"
runtime_gid="${DYNAMIC_PATHWAY_GID:-1000}"

groupmod --gid "${runtime_gid}" analyzer
usermod --uid "${runtime_uid}" --gid "${runtime_gid}" analyzer

if [ ! -d /app/outputs ]; then
    mkdir -p /app/outputs
fi

chown "${runtime_uid}:${runtime_gid}" /app/outputs

exec runuser --user analyzer -- "$@"
