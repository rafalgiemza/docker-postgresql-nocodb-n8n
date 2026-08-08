#!/bin/sh
set -eu

# Renders SeaweedFS's S3 identity config (root + nocodb, scoped to the
# attachments bucket) from env vars, then chains into the image's own
# /entrypoint.sh — SeaweedFS has no dynamic admin API like MinIO's `mc admin
# user/policy`, identities are static config loaded at startup instead (see
# .ai/migrate-from-minio-to-SeaweedFS.md). Chaining into the original
# entrypoint (rather than exec'ing `weed` directly) preserves its /data
# chown-to-seaweed-user + privilege-drop logic — verified locally that
# skipping it would leave /data root-owned and unwritable by the `weed`
# process.

mkdir -p /etc/seaweedfs
cat > /etc/seaweedfs/s3.json <<EOF
{
  "identities": [
    {
      "name": "root",
      "credentials": [
        { "accessKey": "${SEAWEEDFS_ROOT_ACCESS_KEY}", "secretKey": "${SEAWEEDFS_ROOT_SECRET_KEY}" }
      ],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    },
    {
      "name": "nocodb",
      "credentials": [
        { "accessKey": "${NOCODB_SEAWEEDFS_ACCESS_KEY}", "secretKey": "${NOCODB_SEAWEEDFS_SECRET_KEY}" }
      ],
      "actions": [
        "Read:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "Write:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "List:${SEAWEEDFS_BUCKET_ATTACHMENTS}",
        "Tagging:${SEAWEEDFS_BUCKET_ATTACHMENTS}"
      ]
    }
  ]
}
EOF

exec /entrypoint.sh server -dir=/data -filer -s3 \
  -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json \
  -ip=seaweedfs
