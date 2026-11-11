#!/usr/bin/env bash
# Starts the stack, waits for telemetry, then asks each backend a question and checks the answer.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
ok()   { echo "ok    $1"; }
bad()  { echo "FAIL  $1"; fail=1; }

docker compose up -d >/dev/null 2>&1 || { echo "docker compose up failed"; exit 1; }

wait_for() { # description, timeout seconds, command...
  local d=$1 t=$2; shift 2
  for _ in $(seq 1 "$t"); do "$@" >/dev/null 2>&1 && { ok "$d"; return 0; }; sleep 1; done
  bad "$d (waited ${t}s)"; return 1
}

mimir_has_metric() {
  curl -sG localhost:9009/prometheus/api/v1/query --data-urlencode 'query=sum(checkout_requests_total)' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; sys.exit(0 if r and float(r[0]["value"][1])>0 else 1)'
}
mimir_has_errors() {
  curl -sG localhost:9009/prometheus/api/v1/query --data-urlencode 'query=sum(checkout_errors_total)' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; sys.exit(0 if r and float(r[0]["value"][1])>0 else 1)'
}
loki_has_logs() {
  curl -sG localhost:3100/loki/api/v1/query_range --data-urlencode 'query={service_name="checkout-demo"} |= "checkout failed"' \
    --data-urlencode "start=$(( $(date +%s) - 600 ))000000000" \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; sys.exit(0 if r else 1)'
}
tempo_has_traces() {
  curl -sG localhost:3200/api/search --data-urlencode 'tags=service.name=checkout-demo' \
    | python3 -c 'import sys,json; sys.exit(0 if json.load(sys.stdin).get("traces") else 1)'
}
mimir_p95_is_sane() {
  # The request takes tens of milliseconds, so p95 must be well under a second.
  curl -sG localhost:9009/prometheus/api/v1/query \
    --data-urlencode 'query=histogram_quantile(0.95, sum by (le) (rate(checkout_duration_seconds_bucket[1m])))' \
    | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; sys.exit(0 if r and 0 < float(r[0]["value"][1]) < 1 else 1)'
}
grafana_has_sources() {
  [ "$(curl -s localhost:3000/api/datasources | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))')" = 3 ]
}

wait_for "Mimir answers a PromQL query for checkout_requests_total" 120 mimir_has_metric
wait_for "Mimir has checkout_errors_total (the deliberate failures)" 60 mimir_has_errors
wait_for "Mimir p95 latency is under one second (histogram buckets match the unit)" 120 mimir_p95_is_sane
wait_for "Loki returns the error log lines for the service" 90 loki_has_logs
wait_for "Tempo finds traces for service.name=checkout-demo" 90 tempo_has_traces
wait_for "Grafana has the three datasources provisioned" 60 grafana_has_sources
exit $fail
