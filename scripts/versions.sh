#!/bin/bash
# Wypisuje FAKTYCZNIE działające wersje usług ze stosu, a nie tagi z .env
# (część z nich to "latest"/"stable", więc same taggi nic nie mówią o tym,
# co realnie zostało wciągnięte przy ostatnim `docker compose pull`).
#
# Strategia per usługa: najpierw próba odpalenia binarki/CLI wewnątrz
# kontenera (--version), potem odczyt package.json aplikacji, a na końcu
# fallback do tagu obrazu + jego digest/data utworzenia, jeśli nic innego
# się nie uda (oznaczone jako "obraz" zamiast "app", żeby było jasne, że to
# niepotwierdzone binarnie).
set -uo pipefail

CONTAINERS_UP="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"

is_up() {
  grep -qx "$1" <<<"$CONTAINERS_UP"
}

# Zwraca pierwszy niepusty wynik z listy komend `docker exec` (jedna na linię
# w $2), albo pusty string jeśli żadna się nie powiedzie.
exec_probe() {
  local container="$1"
  shift
  local cmd
  for cmd in "$@"; do
    local out
    out="$(docker exec "$container" sh -c "$cmd" 2>/dev/null | head -1 | tr -d '\r')"
    if [ -n "$out" ]; then
      echo "$out"
      return 0
    fi
  done
  return 1
}

# Fallback: tag obrazu + skrócony digest + data utworzenia obrazu lokalnie.
image_fallback() {
  local container="$1"
  local image created
  image="$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null)"
  created="$(docker inspect --format '{{.Created}}' "$container" 2>/dev/null | cut -d'T' -f1)"
  if [ -n "$image" ]; then
    echo "obraz: ${image} (kontener utworzony ${created:-?})"
  else
    echo "brak danych"
  fi
}

row() {
  local service="$1" container="$2" version="$3"
  printf '%-14s %-12s %s\n' "$service" "$([ -n "$version" ] && echo "app" || echo "obraz")" "$version"
}

report() {
  local service="$1" container="$2"
  shift 2
  if ! is_up "$container"; then
    printf '%-14s %-12s %s\n' "$service" "-" "kontener nie działa"
    return
  fi
  local version
  version="$(exec_probe "$container" "$@")"
  if [ -z "$version" ]; then
    version="$(image_fallback "$container")"
    printf '%-14s %-12s %s\n' "$service" "obraz" "$version"
  else
    printf '%-14s %-12s %s\n' "$service" "app" "$version"
  fi
}

printf '%-14s %-12s %s\n' "USŁUGA" "ŹRÓDŁO" "WERSJA"
printf '%-14s %-12s %s\n' "------" "------" "------"

report "postgres"     "docker-postgres-1"     "postgres --version"
report "n8n"           "docker-n8n-1"          "n8n --version"
report "n8n-runner"    "docker-n8n-runner-1"   "n8n-task-runner --version" "cat /package.json | grep -m1 version"
report "nocodb"        "docker-nocodb-1"       "cat /usr/src/app/package.json | grep -m1 '\"version\"'" "find / -maxdepth 6 -iname package.json -path '*nocodb*' 2>/dev/null | head -1 | xargs cat | grep -m1 '\"version\"'"
report "minio"         "docker-minio-1"        "minio --version"
report "mongodb"       "docker-mongodb-1"      "mongod --version"
report "librechat"     "docker-librechat-1"    "cat /app/package.json | grep -m1 '\"version\"'"
report "uptime-kuma"   "docker-uptime-kuma-1"  "cat /app/package.json | grep -m1 '\"version\"'"
report "beszel"        "docker-beszel-1"       "beszel --version" "beszel version" "/beszel --version"
report "beszel-agent"  "docker-beszel-agent-1" "beszel-agent --version" "beszel-agent version" "/beszel-agent --version"
report "caddy"         "docker-caddy-1"        "caddy version"
report "autoheal"      "docker-autoheal-1"
