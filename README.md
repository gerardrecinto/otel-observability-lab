# otel-observability-lab

A small service sends traces, metrics and logs over OpenTelemetry to a Collector, which routes them to Mimir (metrics), Loki (logs) and Tempo (traces), with Grafana in front. A test script asks each backend a question and checks the answer.

## Run it

Needs Docker with Compose. About 3 minutes the first time (image pulls and a pip install).

```
./scripts/test.sh          # starts everything, waits for data, checks each backend
open http://localhost:3000  # Grafana, no login; Mimir, Loki and Tempo are already added as data sources
docker compose down -v
```

## What the test checks

| Backend | Question | Expected |
|---|---|---|
| Mimir | PromQL `sum(checkout_requests_total)` | greater than 0 |
| Mimir | PromQL `sum(checkout_errors_total)` | greater than 0 (the service fails 1 in 5 requests on purpose) |
| Loki | LogQL `{service_name="checkout-demo"} \|= "checkout failed"` | at least one stream |
| Tempo | search `service.name=checkout-demo` | at least one trace |
| Grafana | provisioned data sources | 3 |

I also looked at one result by hand: a failed-checkout log line in Loki carries `trace_id` and `span_id`, and that trace in Tempo has 3 spans (`POST /checkout`, `charge-card`, `write-order`). In Grafana you can jump from the log line to the trace.

## How it fits together

```
checkout-demo (Python, OpenTelemetry SDK)
        | OTLP over HTTP
        v
OpenTelemetry Collector
   |-- metrics --> prometheusremotewrite --> Mimir   (query with PromQL)
   |-- logs    --> OTLP/HTTP              --> Loki   (query with LogQL)
   `-- traces  --> OTLP/gRPC              --> Tempo  (search by service or trace ID)
                                                 |
                                              Grafana
```

## Files

- `docker-compose.yml`: the stack, with pinned image versions
- `config/otel-collector.yaml`: one pipeline per signal
- `config/mimir.yaml`, `config/loki.yaml`, `config/tempo.yaml`: single-node, local filesystem storage
- `app/checkout_demo.py`: the instrumented service
- `scripts/test.sh`: the checks above

## Scope

Local, single node, local disk, no authentication, no retention settings and no alert rules. This shows the pipeline and the queries, not a production deployment. For the Kubernetes side of the same stack see my other labs.
