#!/usr/bin/env bash
# Proves the promise of phase 5 with the real image: the server can be deleted
# and brought back from the copy kept outside it.
#
#   docker build -t paso-backend backend
#   deploy/prueba-restauracion.sh
#
# It uses throwaway containers and volumes with their own names; nothing of a
# real install is touched. A folder stands in for the external storage.
set -euo pipefail

IMAGE="${1:-paso-backend}"
PORT=18000
TOKEN=prueba
NOTEBOOK=0b8f6c1e-2a47-4c5d-9e3f-1a2b3c4d5e6f
OFFSITE="$(mktemp -d)"
chmod 777 "$OFFSITE"

cleanup() {
  docker rm -f paso-prueba >/dev/null 2>&1 || true
  docker volume rm -f paso-prueba-data paso-prueba-backups >/dev/null 2>&1 || true
  rm -rf "$OFFSITE" 2>/dev/null || true
}
trap cleanup EXIT
cleanup; mkdir -p "$OFFSITE"; chmod 777 "$OFFSITE"

run=(-e APP_TOKEN=$TOKEN -e ANTHROPIC_API_KEY=unused -e BACKUP_REMOTE=/offsite
     -v paso-prueba-data:/data -v paso-prueba-backups:/backups -v "$OFFSITE":/offsite)
api() { curl -fsS -H "Authorization: Bearer $TOKEN" "$@"; }
start() {
  docker run -d --name paso-prueba -p $PORT:8000 "${run[@]}" "$IMAGE" >/dev/null
  for _ in $(seq 1 60); do
    curl -fsS "http://localhost:$PORT/api/ping" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "El API no arrancó:"; docker logs paso-prueba | tail -20; exit 1
}

echo "1. Arranca un servidor nuevo y guarda un cuaderno en él"
start
api -X PUT "http://localhost:$PORT/api/notebooks/$NOTEBOOK?semester=2026-2" \
  -H "Content-Type: application/json" \
  -d '{"format":"paso-notebook","format_version":1,"subject":{"name":"Ecuaciones Diferenciales"},
       "notebook":{"id":"'$NOTEBOOK'","title":"Tarea 3"},
       "pages":[{"page":{"id":"p1","background":"grid"},"strokes":[{"id":"s1","points":[[1,2,0.5]]}]}]}' >/dev/null

echo "2. Hace el respaldo y lo copia fuera del servidor"
docker exec paso-prueba python -m app.backup create
ls "$OFFSITE"/paso-*.tar.gz >/dev/null
api "http://localhost:$PORT/api/backup/status" | grep -q '"offsite":true'

echo "3. Borra el servidor: contenedor, datos y respaldos locales"
docker rm -f paso-prueba >/dev/null
docker volume rm paso-prueba-data paso-prueba-backups >/dev/null

echo "4. En un servidor vacío, trae el respaldo de fuera y lo restaura"
docker run --rm "${run[@]}" "$IMAGE" sh -c \
  'python -m app.backup fetch && python -m app.backup restore /backups/paso-*.tar.gz'

echo "5. Arranca y comprueba que el cuaderno está de vuelta"
start
api "http://localhost:$PORT/api/notebooks" | grep -q '"title":"Tarea 3"'
api "http://localhost:$PORT/api/notebooks/$NOTEBOOK" | grep -q '"paso-notebook"'
api "http://localhost:$PORT/api/notebooks" | grep -q '"semester_name":"2026-2"'

echo
echo "BIEN: el servidor se borró y volvió desde el respaldo externo."
