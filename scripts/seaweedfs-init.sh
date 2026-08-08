#!/bin/sh
set -e

# Runs once (docker-compose.yml service `seaweedfs-init`) against a healthy
# SeaweedFS S3 gateway, then exits. Idempotent — safe to re-run on every
# `make up`. Unlike MinIO's minio-init.sh, this no longer creates a
# user/policy — the `nocodb` identity is now static config loaded by
# `seaweedfs` itself at startup (see scripts/seaweedfs-entrypoint.sh and
# .ai/migrate-from-minio-to-SeaweedFS.md). This script only owns buckets +
# their versioning/lifecycle rules, using the `mc` client against SeaweedFS's
# S3 API (confirmed compatible for mb/version/ilm — see FAZA 0 in the
# migration doc).

mc alias set local http://seaweedfs:8333 "${SEAWEEDFS_ROOT_ACCESS_KEY}" "${SEAWEEDFS_ROOT_SECRET_KEY}"

# `seaweedfs`'s healthcheck (master :9333/cluster/status) can report healthy
# slightly before the S3 gateway sub-server finishes binding :8333 — observed
# locally (FAZA 2, connection refused on the first mc call right after
# depends_on: service_healthy). Retry until the S3 API actually answers,
# rather than fight the race with an earlier/different healthcheck target.
i=0
until mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_ATTACHMENTS}"; do
  i=$((i + 1))
  if [ "$i" -ge 15 ]; then
    echo "SeaweedFS S3 API still unreachable after 15 attempts, giving up." >&2
    exit 1
  fi
  sleep 1
done

# Unlike MinIO's `mc ilm add --id <name>` (idempotent by construction — same
# ID = same rule), this mc version's `mc ilm rule add` against SeaweedFS has
# no --id flag: every call creates a NEW rule with an auto-generated ID.
# Re-running this script unguarded would pile up duplicate expiry rules on
# every `make up`. Guard: `mc ilm rule ls` exits 1 ("does not exist") when a
# bucket has no lifecycle config yet, 0 once one is set — verified locally.
ilm_expire_once() {
  bucket="$1"
  days="$2"
  if ! mc ilm rule ls "local/${bucket}" >/dev/null 2>&1; then
    mc ilm rule add --expire-days "${days}" "local/${bucket}"
  fi
}

# Buckets from PRD §8.5 (attachments already created by the retry loop
# above). offers/templates are versioned (offer snapshots and uploaded
# templates are commercial documents, never overwritten silently).
mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_OFFERS}"
mc version enable "local/${SEAWEEDFS_BUCKET_OFFERS}"

mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_TEMPLATES}"
mc version enable "local/${SEAWEEDFS_BUCKET_TEMPLATES}"

mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_RECORDINGS}"
ilm_expire_once "${SEAWEEDFS_BUCKET_RECORDINGS}" 90

mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_TRANSCRIPTS}"

mc mb --ignore-existing "local/${SEAWEEDFS_BUCKET_BACKUPS}"
ilm_expire_once "${SEAWEEDFS_BUCKET_BACKUPS}" 30

echo "SeaweedFS buckets ready."
