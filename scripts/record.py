#!/usr/bin/env python3
"""Ask the running stack for real numbers and write docs/data.json for the project page.

Run ./scripts/test.sh first (or leave the stack up for a few minutes), then:
    python3 scripts/record.py
Standard library only.
"""
import json
import time
import urllib.parse
import urllib.request

MIMIR = "http://localhost:9009/prometheus"
LOKI = "http://localhost:3100"
TEMPO = "http://localhost:3200"


def get(url, **params):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def mimir_range(query, minutes=10, step=15):
    end = int(time.time())
    data = get(MIMIR + "/api/v1/query_range", query=query, start=end - minutes * 60, end=end, step=step)
    series = data["data"]["result"]
    return [[float(t), float(v)] for t, v in series[0]["values"]] if series else []


def mimir_now(query):
    r = get(MIMIR + "/api/v1/query", query=query)["data"]["result"]
    return float(r[0]["value"][1]) if r else None


def main():
    now = int(time.time())
    out = {"recorded_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now))}

    out["totals"] = {
        "requests": mimir_now("sum(checkout_requests_total)"),
        "errors": mimir_now("sum(checkout_errors_total)"),
        "p50_s": mimir_now("histogram_quantile(0.5, sum by (le) (rate(checkout_duration_seconds_bucket[5m])))"),
        "p95_s": mimir_now("histogram_quantile(0.95, sum by (le) (rate(checkout_duration_seconds_bucket[5m])))"),
    }
    out["rate"] = mimir_range("sum(rate(checkout_requests_total[1m]))")
    out["error_ratio"] = mimir_range("sum(rate(checkout_errors_total[1m])) / sum(rate(checkout_requests_total[1m]))")
    out["p95"] = mimir_range("histogram_quantile(0.95, sum by (le) (rate(checkout_duration_seconds_bucket[1m])))")

    logs = get(LOKI + "/loki/api/v1/query_range", query='{service_name="checkout-demo"} |= "checkout failed"',
               start=(now - 600) * 10**9, limit=5, direction="backward")["data"]["result"]
    lines = []
    for stream in logs:
        for ts, line in stream["values"]:
            lines.append({"ts": int(ts) / 1e9, "line": line, "trace_id": stream["stream"].get("trace_id"),
                          "span_id": stream["stream"].get("span_id"), "severity": stream["stream"].get("severity_text")})
    lines.sort(key=lambda x: -x["ts"])
    out["error_logs"] = lines[:5]
    out["log_counts"] = {
        "errors_10m": int(sum(float(v[1]) for s in get(LOKI + "/loki/api/v1/query", query='sum(count_over_time({service_name="checkout-demo"} |= "checkout failed" [10m]))')["data"]["result"] for v in [s["value"]])),
        "all_10m": int(sum(float(v[1]) for s in get(LOKI + "/loki/api/v1/query", query='sum(count_over_time({service_name="checkout-demo"} [10m]))')["data"]["result"] for v in [s["value"]])),
    }

    # the trace that the first error log line points at
    tid = next((l["trace_id"] for l in lines if l["trace_id"]), None)
    out["trace"] = None
    if tid:
        t = get(TEMPO + "/api/traces/" + tid)
        spans = []
        for b in t["batches"]:
            for ss in b["scopeSpans"]:
                for sp in ss["spans"]:
                    spans.append({"name": sp["name"], "start": int(sp["startTimeUnixNano"]),
                                  "end": int(sp["endTimeUnixNano"]),
                                  "error": sp.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")})
        t0 = min(s["start"] for s in spans)
        for s in spans:
            s["offset_ms"] = round((s["start"] - t0) / 1e6, 2)
            s["duration_ms"] = round((s["end"] - s["start"]) / 1e6, 2)
            del s["start"], s["end"]
        spans.sort(key=lambda s: s["offset_ms"])
        out["trace"] = {"trace_id": tid, "spans": spans}

    with open("docs/data.json", "w") as f:
        json.dump(out, f, indent=1)
    print("wrote docs/data.json", out["totals"], out["log_counts"], "trace" if out["trace"] else "no trace")


if __name__ == "__main__":
    main()
