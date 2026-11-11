"""Tiny checkout service that emits traces, metrics and logs over OTLP.

Every request is a trace with two child spans. A fraction of requests fail on purpose,
so there is something to look at. Log lines carry the trace ID.
"""
import logging
import random
import time

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

resource = Resource.create({"service.name": "checkout-demo"})

tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(tracer_provider)

metrics.set_meter_provider(
    MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000)],
        # The SDK's default histogram buckets are meant for milliseconds (0, 5, 10 ... 10000).
        # This metric is in seconds, so without this view every request lands in the first
        # bucket and a p95 query reports seconds for a request that took 40 milliseconds.
        views=[
            View(
                instrument_name="checkout_duration_seconds",
                aggregation=ExplicitBucketHistogramAggregation((0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)),
            )
        ],
    )
)

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
set_logger_provider(logger_provider)
logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))
logging.getLogger().setLevel(logging.INFO)

tracer = trace.get_tracer("checkout")
meter = metrics.get_meter("checkout")
requests_total = meter.create_counter("checkout_requests_total", description="Checkout requests")
errors_total = meter.create_counter("checkout_errors_total", description="Failed checkouts")
latency = meter.create_histogram("checkout_duration_seconds", unit="s", description="Checkout latency")
log = logging.getLogger("checkout")


def handle_request() -> None:
    start = time.time()
    with tracer.start_as_current_span("POST /checkout") as span:
        requests_total.add(1)
        with tracer.start_as_current_span("charge-card"):
            time.sleep(random.uniform(0.01, 0.05))
        with tracer.start_as_current_span("write-order"):
            time.sleep(random.uniform(0.005, 0.02))
        if random.random() < 0.2:
            errors_total.add(1)
            span.set_status(Status(StatusCode.ERROR, "card declined"))
            log.error("checkout failed: card declined")
        else:
            log.info("checkout ok")
    latency.record(time.time() - start)


if __name__ == "__main__":
    while True:
        handle_request()
        time.sleep(random.uniform(0.1, 0.4))
