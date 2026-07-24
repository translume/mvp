#!/bin/sh
set -eu

runtime_uid="${PRECISION_ONCOLOGY_UID:-1000}"
runtime_gid="${PRECISION_ONCOLOGY_GID:-1000}"

if [ ! -d /app/outputs ]; then
    mkdir -p /app/outputs
fi

groupmod --gid "${runtime_gid}" pipeline
usermod --uid "${runtime_uid}" --gid "${runtime_gid}" pipeline
chown "${runtime_uid}:${runtime_gid}" /app/outputs

exec runuser --user pipeline -- "$@"
