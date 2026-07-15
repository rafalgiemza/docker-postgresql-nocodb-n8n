#!/bin/sh
set -e

# Runs once (docker-compose.yml service `minio-init`) against a healthy MinIO,
# then exits. Idempotent — safe to re-run on every `make up`.

mc alias set local http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

# Buckets from PRD §8.5. offers/templates are versioned (offer snapshots and
# uploaded templates are commercial documents, never overwritten silently).
mc mb --ignore-existing "local/${MINIO_BUCKET_ATTACHMENTS}"

mc mb --ignore-existing "local/${MINIO_BUCKET_OFFERS}"
mc version enable "local/${MINIO_BUCKET_OFFERS}"

mc mb --ignore-existing "local/${MINIO_BUCKET_TEMPLATES}"
mc version enable "local/${MINIO_BUCKET_TEMPLATES}"

mc mb --ignore-existing "local/${MINIO_BUCKET_RECORDINGS}"
mc ilm add --id recordings-expiry --expiry-days 90 "local/${MINIO_BUCKET_RECORDINGS}" 2>/dev/null || true

mc mb --ignore-existing "local/${MINIO_BUCKET_TRANSCRIPTS}"

mc mb --ignore-existing "local/${MINIO_BUCKET_BACKUPS}"
mc ilm add --id backups-expiry --expiry-days 30 "local/${MINIO_BUCKET_BACKUPS}" 2>/dev/null || true

# Least-privilege user for NocoDB — scoped to the attachments bucket only,
# never the root account (same pattern as nocodb_crm_user/n8n_crm_user in
# init-data.sh for Postgres).
cat > /tmp/nocodb-attachments-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${MINIO_BUCKET_ATTACHMENTS}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${MINIO_BUCKET_ATTACHMENTS}"]
    }
  ]
}
EOF

mc admin policy create local nocodb-attachments /tmp/nocodb-attachments-policy.json
mc admin user add local "${NOCODB_MINIO_ACCESS_KEY}" "${NOCODB_MINIO_SECRET_KEY}"
mc admin policy attach local nocodb-attachments --user "${NOCODB_MINIO_ACCESS_KEY}" 2>/dev/null || true

echo "MinIO buckets + nocodb user ready."
