#!/usr/bin/env bash
# Pruebas de la API de tareas (Práctica 5).
# Uso:  ./test_api.sh            (por defecto http://localhost:5001)
#       BASE_URL=http://otra:5001 ./test_api.sh

set -u
BASE_URL="${BASE_URL:-http://localhost:5001}"
PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
title() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

# request <MÉTODO> <RUTA> [BODY_JSON]  -> deja el cuerpo en $BODY y el código en $STATUS
request() {
  local method="$1" path="$2" data="${3:-}"
  local out
  if [[ -n "$data" ]]; then
    out=$(curl -s -w '\n%{http_code}' -X "$method" \
          -H "Content-Type: application/json" -d "$data" "$BASE_URL$path")
  else
    out=$(curl -s -w '\n%{http_code}' -X "$method" "$BASE_URL$path")
  fi
  STATUS="${out##*$'\n'}"
  BODY="${out%$'\n'*}"
  echo "$method $path -> $STATUS"
  [[ -n "$BODY" ]] && echo "$BODY"
}

# expect <CÓDIGO_ESPERADO> <DESCRIPCIÓN>
expect() {
  if [[ "$STATUS" == "$1" ]]; then
    green "  ✔ $2"; PASS=$((PASS + 1))
  else
    red "  ✘ $2 (esperado $1, recibido $STATUS)"; FAIL=$((FAIL + 1))
  fi
}

title "Crear tarea (POST /tasks)"
request POST /tasks '{"title": "Configurar sistema multi-contenedor", "description": "Usar Docker Compose"}'
expect 201 "La tarea se crea correctamente"
TASK_ID=$(printf '%s' "$BODY" | sed -n 's/.*"id": *\([0-9][0-9]*\).*/\1/p')
echo "  ID creado: ${TASK_ID:-<no encontrado>}"

title "Listar tareas (GET /tasks)"
request GET /tasks
expect 200 "Se obtiene el listado"

if [[ -n "${TASK_ID:-}" ]]; then
  title "Obtener tarea (GET /tasks/$TASK_ID)"
  request GET "/tasks/$TASK_ID"
  expect 200 "Se obtiene la tarea creada"

  title "Completar tarea (PUT /tasks/$TASK_ID/complete)"
  request PUT "/tasks/$TASK_ID/complete"
  expect 200 "La tarea se marca como completada"

  title "Borrar tarea (DELETE /tasks/$TASK_ID)"
  request DELETE "/tasks/$TASK_ID"
  expect 204 "La tarea se elimina"

  title "Tarea borrada (GET /tasks/$TASK_ID)"
  request GET "/tasks/$TASK_ID"
  expect 404 "La tarea ya no existe"
fi

title "Validaciones"
request POST /tasks '{"description": "sin título"}'
expect 400 "Rechaza tarea sin title"
request POST /tasks 'esto no es json'
expect 400 "Rechaza cuerpo que no es JSON"
request POST /tasks '{"title": "Tarea", "description": 123}'
expect 400 "Rechaza description no string"
request GET /tasks/999999
expect 404 "Devuelve 404 para tarea inexistente"
request PUT /tasks/999999/complete
expect 404 "Devuelve 404 al completar tarea inexistente"

printf '\nResultado: '
green "$PASS correctas" | tr -d '\n'; printf ' / '; red "$FAIL fallidas"
[[ "$FAIL" -eq 0 ]]
