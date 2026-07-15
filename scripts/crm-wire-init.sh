#!/bin/bash
set -e
source .env

# Łączy NocoDB i n8n z appdata/crm po hard-resecie (docs/hard-reset.md).
# Uruchamiane na żądanie: `make wire-apps`, PO `make migrate && make seed`.
#
# Wymaga ręcznego Kroku 0 (patrz docs/init-nocodb.md) już wykonanego:
#   - NocoDB: super-admin już się zalogował, NC_API_TOKEN w .env (Account →
#     API Tokens).
#   - n8n: owner account już przeszedł setup wizard, N8N_API_KEY w .env
#     (Settings → API → Create API Key).
# Bez tych dwóch tokenów w .env skrypt kończy się natychmiast z komunikatem —
# nie próbuje bootstrapować kont admina samodzielnie (kruche, wersja-zależne,
# ryzyko zablokowania się z własnego środowiska — patrz plan).
#
# Idempotentny: bezpieczny do wielokrotnego uruchamiania (GET, dopasuj po
# nazwie, pomiń jeśli istnieje — wzorem minio-init.sh).
#
# UWAGA: dokładny kształt endpointów NocoDB v2 meta API poniżej (ścieżki,
# pola payloadu dla source/grid/kanban/calendar/filter) jest zrekonstruowany
# z dokumentacji, NIE zweryfikowany na żywo przeciw działającemu kontenerowi
# (NOCODB_VERSION=latest — API się zmieniało między wersjami). Przed pierwszym
# uruchomieniem: otwórz Swagger UI działającego kontenera NocoDB
# (zwykle pod /api/v2 lub linkowany z poziomu UI) i zweryfikuj/skoryguj
# ścieżki + pola JSON poniżej.

: "${NC_API_TOKEN:?NC_API_TOKEN nie ustawiony w .env — wykonaj Krok 0 (docs/init-nocodb.md)}"
: "${N8N_API_KEY:?N8N_API_KEY nie ustawiony w .env — wykonaj Krok 0 (docs/init-n8n.md)}"

NC_URL="${NC_LOCAL_URL:-http://localhost:8081}"
N8N_URL="${N8N_LOCAL_URL:-http://localhost:5678}"
NC_BASE_TITLE="CoAction CRM"
NC_SOURCE_ALIAS="appdata (crm)"
N8N_CRED_NAME="appdata (n8n_crm_user)"

nc_api() {
  # nc_api METHOD PATH [BODY]
  local method="$1" path="$2" body="${3:-}"
  curl -sS -X "$method" "${NC_URL}${path}" \
    -H "xc-auth: ${NC_API_TOKEN}" \
    -H "Content-Type: application/json" \
    ${body:+-d "$body"}
}

echo "🔎 Szukam bazy '${NC_BASE_TITLE}' w NocoDB..."
BASE_ID=$(nc_api GET "/api/v2/meta/bases" | jq -r --arg t "$NC_BASE_TITLE" '.list[]? | select(.title==$t) | .id' | head -n1)

if [ -z "$BASE_ID" ] || [ "$BASE_ID" = "null" ]; then
  echo "➕ Tworzę bazę '${NC_BASE_TITLE}'..."
  BASE_ID=$(nc_api POST "/api/v2/meta/bases" "$(jq -n --arg t "$NC_BASE_TITLE" '{title:$t}')" | jq -r '.id')
else
  echo "✅ Baza już istnieje (id=${BASE_ID})."
fi

echo "🔎 Szukam źródła '${NC_SOURCE_ALIAS}' w bazie..."
SOURCE_ID=$(nc_api GET "/api/v2/meta/bases/${BASE_ID}/sources" | jq -r --arg a "$NC_SOURCE_ALIAS" '.list[]? | select(.alias==$a) | .id' | head -n1)

if [ -z "$SOURCE_ID" ] || [ "$SOURCE_ID" = "null" ]; then
  echo "➕ Podłączam źródło '${NC_SOURCE_ALIAS}' → appdata/crm (nocodb_crm_user)..."
  SOURCE_PAYLOAD=$(jq -n \
    --arg alias "$NC_SOURCE_ALIAS" \
    --arg user "$NOCODB_CRM_USER" \
    --arg password "$NOCODB_CRM_PASSWORD" \
    --arg database "$APP_DB" \
    '{
      alias: $alias,
      type: "pg",
      config: {
        client: "pg",
        connection: {
          host: "postgres",
          port: 5432,
          user: $user,
          password: $password,
          database: $database
        },
        searchPath: ["crm"]
      }
    }')
  SOURCE_ID=$(nc_api POST "/api/v2/meta/bases/${BASE_ID}/sources" "$SOURCE_PAYLOAD" | jq -r '.id')
else
  echo "✅ Źródło już istnieje (id=${SOURCE_ID})."
fi

echo "🔄 Synchronizuję metadane (meta-diff)..."
# Niektóre wersje NocoDB synchronizują tabele automatycznie przy tworzeniu
# źródła; ten krok jest zabezpieczeniem, żeby nowe widoki (np. v_opportunity_notes
# po migracji schematu) też się pojawiły bez ręcznego "Reload" w UI.
nc_api POST "/api/v2/meta/sources/${SOURCE_ID}/meta-diff/apply" >/dev/null || \
  echo "⚠️  meta-diff/apply nie powiodło się lub endpoint inny w tej wersji — odśwież ręcznie w UI (source → ⋮ → Reload)."

table_id_by_title() {
  local title="$1"
  nc_api GET "/api/v2/meta/bases/${BASE_ID}/tables" | jq -r --arg t "$title" '.list[]? | select(.title==$t) | .id' | head -n1
}

column_id_by_title() {
  local table_id="$1" title="$2"
  nc_api GET "/api/v2/meta/tables/${table_id}/columns" | jq -r --arg t "$title" '.list[]? | select(.title==$t) | .id' | head -n1
}

view_exists() {
  local table_id="$1" title="$2"
  nc_api GET "/api/v2/meta/tables/${table_id}/views" | jq -r --arg t "$title" '.list[]? | select(.title==$t) | .id' | head -n1
}

add_filter() {
  local view_id="$1" column_id="$2" value="$3"
  nc_api POST "/api/v2/meta/views/${view_id}/filters" \
    "$(jq -n --arg fk "$column_id" --arg v "$value" '{fk_column_id:$fk, comparison_op:"eq", value:$v}')" >/dev/null
}

echo "📋 Widoki na v_pipeline (Kanban wg stage)..."
V_PIPELINE_ID=$(table_id_by_title "v_pipeline")
if [ -n "$V_PIPELINE_ID" ]; then
  STAGE_COL_ID=$(column_id_by_title "$V_PIPELINE_ID" "stage")
  EXISTING=$(view_exists "$V_PIPELINE_ID" "Kanban: Etapy")
  if [ -z "$EXISTING" ] || [ "$EXISTING" = "null" ]; then
    nc_api POST "/api/v2/meta/tables/${V_PIPELINE_ID}/kanbans" \
      "$(jq -n --arg t "Kanban: Etapy" --arg fk "$STAGE_COL_ID" '{title:$t, fk_grp_col_id:$fk}')" >/dev/null
    echo "✅ Utworzono widok Kanban 'Kanban: Etapy'."
  else
    echo "✅ Widok Kanban już istnieje."
  fi
else
  echo "⚠️  Tabela 'v_pipeline' nie znaleziona w NocoDB — sprawdź sync źródła."
fi

echo "📝 Widok na v_opportunity_notes..."
V_NOTES_ID=$(table_id_by_title "v_opportunity_notes")
if [ -n "$V_NOTES_ID" ]; then
  EXISTING=$(view_exists "$V_NOTES_ID" "Notatki")
  if [ -z "$EXISTING" ] || [ "$EXISTING" = "null" ]; then
    nc_api POST "/api/v2/meta/tables/${V_NOTES_ID}/grids" "$(jq -n '{title:"Notatki"}')" >/dev/null
    echo "✅ Utworzono widok 'Notatki'."
  else
    echo "✅ Widok 'Notatki' już istnieje."
  fi
else
  echo "⚠️  Tabela 'v_opportunity_notes' nie znaleziona w NocoDB — czy make migrate było uruchomione przed tym skryptem?"
fi

echo "📅 Widoki 'Moje zadania' per osoba (v_tasks)..."
V_TASKS_ID=$(table_id_by_title "v_tasks")
if [ -n "$V_TASKS_ID" ]; then
  ASSIGNEE_COL_ID=$(column_id_by_title "$V_TASKS_ID" "assignee_name")
  DUE_AT_COL_ID=$(column_id_by_title "$V_TASKS_ID" "due_at")

  # Lista osób pochodzi z rzeczywistych danych (kto ma choć jedno zadanie),
  # nie ze stałej listy w .env — patrz plan, decyzja świadoma: nowa osoba bez
  # przypisanych zadań dostanie widok dopiero po ponownym uruchomieniu skryptu.
  ASSIGNEES=$(docker exec docker-postgres-1 psql -U "${NOCODB_CRM_USER}" -d "${APP_DB}" -At \
    -c "SELECT DISTINCT assignee_name FROM crm.v_tasks WHERE assignee_name IS NOT NULL ORDER BY 1;")

  echo "$ASSIGNEES" | while IFS= read -r NAME; do
    [ -z "$NAME" ] && continue

    GRID_TITLE="Moje zadania — ${NAME}"
    EXISTING=$(view_exists "$V_TASKS_ID" "$GRID_TITLE")
    if [ -z "$EXISTING" ] || [ "$EXISTING" = "null" ]; then
      GRID_ID=$(nc_api POST "/api/v2/meta/tables/${V_TASKS_ID}/grids" "$(jq -n --arg t "$GRID_TITLE" '{title:$t}')" | jq -r '.id')
      add_filter "$GRID_ID" "$ASSIGNEE_COL_ID" "$NAME"
      echo "✅ Utworzono widok listy '${GRID_TITLE}'."
    else
      echo "✅ Widok listy '${GRID_TITLE}' już istnieje."
    fi

    CAL_TITLE="Kalendarz — ${NAME}"
    EXISTING=$(view_exists "$V_TASKS_ID" "$CAL_TITLE")
    if [ -z "$EXISTING" ] || [ "$EXISTING" = "null" ]; then
      CAL_ID=$(nc_api POST "/api/v2/meta/tables/${V_TASKS_ID}/calendars" \
        "$(jq -n --arg t "$CAL_TITLE" --arg fk "$DUE_AT_COL_ID" '{title:$t, fk_cover_image_col_id:null, calendar_range:[{fk_from_column_id:$fk}]}')" | jq -r '.id')
      add_filter "$CAL_ID" "$ASSIGNEE_COL_ID" "$NAME"
      echo "✅ Utworzono widok kalendarza '${CAL_TITLE}'."
    else
      echo "✅ Widok kalendarza '${CAL_TITLE}' już istnieje."
    fi
  done
else
  echo "⚠️  Tabela 'v_tasks' nie znaleziona w NocoDB — sprawdź sync źródła."
fi

echo "🔐 Credential n8n → appdata (n8n_crm_user)..."
EXISTING_CRED_ID=$(curl -sS "${N8N_URL}/api/v1/credentials" -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
  | jq -r --arg n "$N8N_CRED_NAME" '.data[]? | select(.name==$n) | .id' | head -n1)

if [ -n "$EXISTING_CRED_ID" ] && [ "$EXISTING_CRED_ID" != "null" ]; then
  echo "♻️  Usuwam istniejący credential (id=${EXISTING_CRED_ID}) przed odtworzeniem — prostsze i pewniejsze niż PATCH między wersjami n8n."
  curl -sS -X DELETE "${N8N_URL}/api/v1/credentials/${EXISTING_CRED_ID}" -H "X-N8N-API-KEY: ${N8N_API_KEY}" >/dev/null
fi

CRED_PAYLOAD=$(jq -n \
  --arg name "$N8N_CRED_NAME" \
  --arg user "$N8N_CRM_USER" \
  --arg password "$N8N_CRM_PASSWORD" \
  --arg database "$APP_DB" \
  '{
    name: $name,
    type: "postgres",
    data: {
      host: "postgres",
      port: 5432,
      database: $database,
      user: $user,
      password: $password,
      ssl: "disable"
    }
  }')
curl -sS -X POST "${N8N_URL}/api/v1/credentials" \
  -H "X-N8N-API-KEY: ${N8N_API_KEY}" -H "Content-Type: application/json" \
  -d "$CRED_PAYLOAD" >/dev/null
echo "✅ Credential '${N8N_CRED_NAME}' utworzony."

echo ""
echo "✅ Gotowe. Pamiętaj, że poza zakresem tego skryptu (nadal ręczne):"
echo "   - import workflowów z n8n-workflows/*.json (Workflows → Import from File)"
echo "   - podpięcie credentiala '${N8N_CRED_NAME}' pod node'y w zaimportowanych workflowach"
echo "   - aktywacja workflowów"
echo "   - przypisanie ról NocoDB (Creator/Editor/Viewer) realnym osobom w UI"
