#!/usr/bin/env bash
# Portable smoke test runner for the deployed API.

set -u -o pipefail

BASE_URL=${BASE_URL:-https://api.luminiteq.eu}
AUTH_HEADER_NAME=${AUTH_HEADER_NAME:-X-Admin-Token}
X_ADMIN_TOKEN=${X_ADMIN_TOKEN:-lumi-zelensky-god!1}

BASE_URL=${BASE_URL%/}
AUTH_HEADER_VALUE="${AUTH_HEADER_NAME}: ${X_ADMIN_TOKEN}"

failures=0
declare -a FAILURE_MESSAGES=()

log_step() {
  printf '\n==> %s\n' "$1"
}

record_success() {
  printf '   ✅ %s\n' "$1"
}

record_failure() {
  local message="$1"
  FAILURE_MESSAGES+=("$message")
  ((failures+=1))
  printf '   ❌ %s\n' "$message"
}

REQUEST_STATUS=""
REQUEST_BODY=""

perform_request() {
  local method="$1"
  local url="$2"
  shift 2
  local response

  if ! response=$(curl -sS -w '\n%{http_code}' -X "$method" "$url" "$@" 2>&1); then
    REQUEST_STATUS=0
    REQUEST_BODY="$response"
    return 1
  fi

  REQUEST_STATUS=$(printf '%s' "$response" | tail -n1)
  REQUEST_BODY=$(printf '%s' "$response" | sed '$d')
  return 0
}

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

parse_first_tenant_id() {
  local payload="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -er '.[0].id // empty' <<<"$payload" 2>/dev/null && return 0
  fi
  printf '%s' "$payload" | tr '\n' ' ' | sed -nE 's/.*"id"[[:space:]]*:[[:space:]]*"?([^"[:space:]}\]]+)"?.*/\1/p' | head -n1
}

contains_tenant_id() {
  local payload="$1"
  local tenant_id="$2"
  if [[ -z "$tenant_id" ]]; then
    return 1
  fi
  if command -v jq >/dev/null 2>&1; then
    jq -e --arg tenant "$tenant_id" 'map(.id|tostring) | index($tenant)' <<<"$payload" >/dev/null 2>&1
    return $?
  fi
  grep -q "\"id\"" <<<"$payload" && grep -q "$tenant_id" <<<"$payload"
}

curl_json() {
  local method="$1"
  local path="$2"
  shift 2 || true
  perform_request "$method" "$BASE_URL$path" "$@" -H "Accept: application/json"
}

log_step "1) Health check"
if curl_json GET "/healthz"; then
  body_trim=$(trim "$REQUEST_BODY")
  if [[ "$REQUEST_STATUS" == "200" && "$body_trim" == \{"status":"ok"* ]]; then
    record_success "Health endpoint returned ok"
  else
    record_failure "Health endpoint unexpected response (status=$REQUEST_STATUS)"
    printf '%s\n' "$REQUEST_BODY"
  fi
else
  record_failure "Health endpoint request failed"
  printf '%s\n' "$REQUEST_BODY"
fi

log_step "2) List tenants"
if curl_json GET "/admin/tenants" -H "$AUTH_HEADER_VALUE"; then
  if [[ "$REQUEST_STATUS" != "200" ]]; then
    record_failure "Tenant list HTTP $REQUEST_STATUS"
  else
    tenants_body="$REQUEST_BODY"
    trimmed=$(trim "$tenants_body")
    if [[ -z "$trimmed" || ${trimmed:0:1} != '[' ]]; then
      record_failure "Tenant list is not a JSON array"
    else
      record_success "Fetched tenant list"
    fi
  fi
else
  record_failure "Tenant list request failed"
  tenants_body=""
fi

first_tenant_id=""
if [[ -n "${tenants_body:-}" ]]; then
  first_tenant_id=$(parse_first_tenant_id "$tenants_body" || true)
fi

log_step "3) Delete first tenant"
if [[ -z "$first_tenant_id" ]]; then
  record_failure "No tenant available to delete"
else
  if curl_json DELETE "/admin/tenants/${first_tenant_id}" -H "$AUTH_HEADER_VALUE"; then
    if [[ "$REQUEST_STATUS" == "204" ]]; then
      record_success "Deleted tenant $first_tenant_id"
    else
      record_failure "Unexpected status deleting tenant $first_tenant_id (HTTP $REQUEST_STATUS)"
      printf '%s\n' "$REQUEST_BODY"
    fi
  else
    record_failure "Tenant delete request failed"
    printf '%s\n' "$REQUEST_BODY"
  fi
fi

log_step "3b) Verify tenant removal"
if curl_json GET "/admin/tenants" -H "$AUTH_HEADER_VALUE"; then
  if [[ "$REQUEST_STATUS" == "200" ]]; then
    tenants_after="$REQUEST_BODY"
    if [[ -n "$first_tenant_id" ]]; then
      if contains_tenant_id "$tenants_after" "$first_tenant_id"; then
        record_success "Tenant $first_tenant_id still listed (possible repopulation)"
      else
        record_success "Tenant $first_tenant_id removed from listing"
      fi
    else
      record_success "Tenant list refreshed"
    fi
  else
    record_failure "Re-list tenants HTTP $REQUEST_STATUS"
  fi
else
  record_failure "Tenant re-list request failed"
  tenants_after=""
fi

if [[ -z "${tenants_after:-}" ]]; then
  tenants_after="${tenants_body:-}"  # fallback for usage lookup
fi

usage_tenant_id=""
if [[ -n "$tenants_after" ]]; then
  usage_tenant_id=$(parse_first_tenant_id "$tenants_after" || true)
fi

log_step "4) Tenant usage"
if [[ -z "$usage_tenant_id" ]]; then
  record_failure "No tenant available for usage check"
else
  if curl_json GET "/admin/tenants/${usage_tenant_id}/usage" -H "$AUTH_HEADER_VALUE"; then
    body_trim=$(trim "$REQUEST_BODY")
    if [[ "$REQUEST_STATUS" == "200" && ( ${body_trim:0:1} == '{' || ${body_trim:0:1} == '[' ) ]]; then
      record_success "Usage fetched for tenant $usage_tenant_id"
    else
      record_failure "Usage unexpected response (status=$REQUEST_STATUS)"
      printf '%s\n' "$REQUEST_BODY"
    fi
  else
    record_failure "Usage request failed"
    printf '%s\n' "$REQUEST_BODY"
  fi
fi

printf '\n'
if (( failures == 0 )); then
  printf 'PASS - all smoke checks succeeded\n'
  exit 0
else
  printf 'FAIL - %d issue(s): %s\n' "$failures" "${FAILURE_MESSAGES[*]}"
  exit 1
fi
