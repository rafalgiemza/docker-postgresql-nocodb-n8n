#!/bin/bash
set -euo pipefail
source .env

# Reproduces the 2026-07-14 incident (post-mortem/logs.md) on demand: forces
# an *unclean* Postgres backend termination (SIGKILL, not pg_terminate_backend
# — only an abnormal exit makes the postmaster assume shared memory may be
# corrupted), which triggers the exact same cascade seen in that incident:
#   server process was terminated by signal ... -> terminating any other
#   active server processes -> crash recovery -> connections refused ->
#   n8n /healthz fails -> (once wired) Uptime Kuma alerts / docker healthcheck
#   flips unhealthy.
# Use this to verify monitoring/alerting and healthchecks actually fire,
# without needing to fake a real disk I/O stall.
#
# Only the throwaway backend opened by this script is killed — no real
# n8n/user connections are touched.

PG_CONTAINER="${PG_CONTAINER:-docker-postgres-1}"
N8N_CONTAINER="${N8N_CONTAINER:-docker-n8n-1}"
MONITOR_TIMEOUT="${MONITOR_TIMEOUT:-180}"   # seconds to watch recovery for
HOLD_SECONDS=300                            # how long the throwaway backend sleeps if never killed

if [ "${1:-}" != "--force" ]; then
  echo "⚠️  This forcibly crashes Postgres on THIS host (container: ${PG_CONTAINER})."
  echo "⚠️  It WILL cause real n8n 503s for anyone using it right now, same as the 2026-07-14 incident."
  echo "⚠️  Only run this against a VPS you intend to test, at a time you're prepared for the disruption."
  read -r -p "Type YES to proceed: " confirm
  if [ "$confirm" != "YES" ]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "🩺 Pre-check: n8n /healthz from inside its own container"
docker exec "$N8N_CONTAINER" wget -qO- http://localhost:5678/healthz || true
echo

echo "🧪 Opening a throwaway backend (SELECT pg_sleep(${HOLD_SECONDS})) to crash..."
docker exec -d "$PG_CONTAINER" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "SELECT pg_sleep(${HOLD_SECONDS});"

echo "⏳ Waiting for it to register in pg_stat_activity..."
PID=""
for _ in $(seq 1 10); do
  PID="$(docker exec "$PG_CONTAINER" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tA -c \
    "SELECT pid FROM pg_stat_activity WHERE query ILIKE 'SELECT pg_sleep%' AND pid <> pg_backend_pid() ORDER BY backend_start DESC LIMIT 1;")"
  [ -n "$PID" ] && break
  sleep 1
done

if [ -z "$PID" ]; then
  echo "❌ Could not find the throwaway backend PID — aborting without touching anything."
  exit 1
fi

echo "💥 Killing backend PID ${PID} with SIGKILL (simulates the crash from the incident)..."
docker exec "$PG_CONTAINER" kill -9 "$PID"

START_TS=$(date +%s)
echo "📡 Monitoring recovery for up to ${MONITOR_TIMEOUT}s (Ctrl+C to stop early)..."
echo "    timestamp            postgres accepts conns   n8n /healthz"
RECOVERED=""
while true; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TS))
  if [ "$ELAPSED" -ge "$MONITOR_TIMEOUT" ]; then
    echo "⏱️  Timeout reached without confirmed recovery — check logs manually:"
    echo "    docker logs --since ${MONITOR_TIMEOUT}s ${PG_CONTAINER}"
    break
  fi

  if docker exec "$PG_CONTAINER" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    PG_STATUS="up"
  else
    PG_STATUS="DOWN/recovering"
  fi

  if docker exec "$N8N_CONTAINER" wget -qO- http://localhost:5678/healthz >/dev/null 2>&1; then
    N8N_STATUS="ok"
  else
    N8N_STATUS="FAIL"
  fi

  printf "    %s   %-22s   %s\n" "$(date '+%H:%M:%S')" "$PG_STATUS" "$N8N_STATUS"

  if [ "$PG_STATUS" = "up" ] && [ "$N8N_STATUS" = "ok" ]; then
    RECOVERED="yes"
    echo "✅ Recovered after ~${ELAPSED}s."
    break
  fi

  sleep 2
done

echo
echo "📋 Container health status (as seen by docker's own healthcheck):"
docker inspect --format '  {{.Name}}: {{.State.Health.Status}} (restarts: {{.RestartCount}})' "$PG_CONTAINER" "$N8N_CONTAINER" 2>/dev/null || true

echo
if [ -n "$RECOVERED" ]; then
  echo "Now go check whatever you're testing (Uptime Kuma alert fired? healthcheck flipped unhealthy during the gap?)."
else
  echo "Did not confirm recovery within ${MONITOR_TIMEOUT}s — inspect manually before re-running."
fi
