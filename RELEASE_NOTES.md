First tagged release.

- The stack: OpenTelemetry Collector, Mimir, Loki, Tempo and Grafana in Docker Compose, with the three data sources provisioned.
- `ghcr.io/gerardrecinto/otel-observability-lab-checkout-demo`: the instrumented service as a small non-root image, so the demo no longer installs packages every time it starts.
- `scripts/test.sh` asks each backend a PromQL, LogQL or trace-search question and exits non-zero on a wrong answer. It runs in CI on every push.
- `scripts/record.py` rewrites `docs/data.json`, the data behind the project page.

Fixed before tagging: the latency histogram used the SDK's millisecond buckets for a metric in seconds, so p95 read 4.75 seconds for a 40 millisecond request. The test now checks it.

Not covered: Kubernetes, authentication, retention, alert rules, object storage.
