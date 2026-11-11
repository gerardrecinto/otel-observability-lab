# otel-observability-lab

A small service sends traces, metrics and logs over OpenTelemetry to a Collector. The Collector sends each signal to its own backend: metrics to Mimir, logs to Loki, traces to Tempo. Grafana reads all three. A test script asks every backend a real question and fails if the answer is wrong.

[![CI](https://github.com/gerardrecinto/otel-observability-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/gerardrecinto/otel-observability-lab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/gerardrecinto/otel-observability-lab)](LICENSE)
[![Release](https://img.shields.io/github/v/release/gerardrecinto/otel-observability-lab)](https://github.com/gerardrecinto/otel-observability-lab/releases)

**[Recorded results and charts](https://gerardrecinto.github.io/otel-observability-lab/)**

I built it to have a small, honest place to see the three signals line up: a failed request shows up as a counter in Mimir, an error line in Loki, and a red span in Tempo, and the log line carries the trace ID that leads to the span.

## Try it

You need Docker with Compose. The first run pulls five images and takes about three minutes.

```bash
git clone https://github.com/gerardrecinto/otel-observability-lab
cd otel-observability-lab
./scripts/test.sh
```

It starts the stack, waits for data, then prints one line per check. When it passes, open Grafana at http://localhost:3000 (no login). Mimir, Loki and Tempo are already added as data sources. Try these in Explore:

| Backend | Query |
| :--- | :--- |
| Mimir | `sum(rate(checkout_errors_total[1m])) / sum(rate(checkout_requests_total[1m]))` |
| Loki | `{service_name="checkout-demo"} \|= "checkout failed"` |
| Tempo | `{ resource.service.name="checkout-demo" && status=error }` |

Stop it with `docker compose down -v`.

## What the checks ask

| Backend | Question | Expected |
| :--- | :--- | :--- |
| Mimir | `sum(checkout_requests_total)` | greater than 0 |
| Mimir | `sum(checkout_errors_total)` | greater than 0, the service fails 1 in 5 on purpose |
| Mimir | p95 from `checkout_duration_seconds` | between 0 and 1 second |
| Loki | error lines for `service_name="checkout-demo"` | at least one stream |
| Tempo | search `service.name=checkout-demo` | at least one trace |
| Grafana | provisioned data sources | 3 |

## How it fits together

```
checkout-demo (Python, OpenTelemetry SDK)
      | OTLP over HTTP
      v
OpenTelemetry Collector
  |-- metrics --> prometheusremotewrite --> Mimir
  |-- logs    --> OTLP over HTTP         --> Loki
  `-- traces  --> OTLP over gRPC         --> Tempo
                                              |
                                           Grafana
```

Every request is a trace with two child spans, `charge-card` and `write-order`. One in five fails with "card declined", which sets the parent span to an error and writes an error log line.

## A bug that bit me

The first version reported a p95 of 4.75 seconds for requests that took about 40 milliseconds. The SDK's default histogram buckets are written for milliseconds (0, 5, 10, 25 and so on up to 10000). My metric is in seconds, so every request landed in the first bucket and the quantile was interpolated inside it. I fixed it with a `View` that sets buckets in seconds, and `scripts/test.sh` now fails if p95 is not under one second.

If you reuse the idea, check your bucket boundaries against your unit before you trust a latency chart.

## Image

The service is published as a small non-root image so the demo does not install packages on every start:

```bash
docker pull ghcr.io/gerardrecinto/otel-observability-lab-checkout-demo:latest
```

Releases are tagged `v*`. The workflow in `.github/workflows/release.yml` builds and pushes the image and creates the GitHub release.

## Layout

| Path | What it is |
| :--- | :--- |
| `docker-compose.yml` | the stack, image versions pinned |
| `config/` | Collector pipelines and single-node configs for Mimir, Loki and Tempo, plus the Grafana data sources |
| `app/` | the instrumented service and its Dockerfile |
| `scripts/test.sh` | the checks above |
| `scripts/record.py` | reads real numbers back from the stack and writes `docs/data.json` |
| `docs/` | the project page |

## Limits

One node, local disk, no authentication, no retention settings, no alert rules, no Kubernetes. The service is synthetic, so the numbers show that the pipeline works and not how a real checkout behaves. For a real deployment you would add sampling, object storage for Mimir, Loki and Tempo, and multi-tenancy.

MIT licensed.
