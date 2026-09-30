from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"


def percentile(values: list[float | int], p: float) -> float:
    if not values:
        return 0.0
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    d = k - f
    sorted_v = sorted(values)
    return round(sorted_v[f] + d * (sorted_v[c] - sorted_v[f]), 2)


def compute_dashboard_metrics(window_minutes: int = 60) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(minutes=window_minutes)

    records: list[dict[str, Any]] = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except Exception:
                continue

    # Parse timestamps and filter
    window_records: list[dict[str, Any]] = []
    for rec in records:
        ts_str = rec.get("ts")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            rec["_dt"] = ts
            # If logs are within window (or fallback to all if recent test)
            if ts >= cutoff_utc:
                window_records.append(rec)
        except Exception:
            window_records.append(rec)

    # If window records are few or empty (e.g. clock differences), fallback to latest 200 records
    if not window_records and records:
        window_records = records[-200:]

    # 1. Latency Panel (response_sent)
    response_events = [r for r in window_records if r.get("event") == "response_sent"]
    latencies = [r["latency_ms"] for r in response_events if "latency_ms" in r]
    ttfts = [r["ttft_ms"] for r in response_events if "ttft_ms" in r]

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    ttft_p95 = percentile(ttfts, 95)

    latency_threshold = 3000
    latency_status = "PASS" if p95 <= latency_threshold else "BREACH"

    # Latency time series
    latency_series = []
    for r in response_events[-30:]:
        latency_series.append({
            "time": r.get("ts", "")[11:19] if r.get("ts") else "",
            "latency": r.get("latency_ms", 0),
            "ttft": r.get("ttft_ms", 0),
            "correlation_id": r.get("correlation_id", "N/A"),
        })

    # 2. Traffic Panel (request_received)
    request_events = [r for r in window_records if r.get("event") == "request_received"]
    total_requests = len(request_events)
    # Minute buckets
    buckets = defaultdict(int)
    for r in request_events:
        dt = r.get("_dt")
        key = dt.strftime("%H:%M") if dt else "recent"
        buckets[key] += 1

    active_minutes = max(1, len(buckets))
    rate_per_minute = round(total_requests / active_minutes, 2)
    traffic_status = "PASS" if rate_per_minute >= 1.0 else "BREACH"

    traffic_series = [{"time": k, "count": v} for k, v in sorted(buckets.items())]

    # 3. Errors Panel (request_received, request_failed)
    failed_events = [r for r in window_records if r.get("event") == "request_failed"]
    total_received = len(request_events)
    total_failed = len(failed_events)
    error_rate_pct = round((total_failed / total_received * 100), 2) if total_received > 0 else 0.0

    # Tool success (all events having tool_success field)
    tool_events = [r for r in window_records if "tool_success" in r and r["tool_success"] is not None]
    tool_success_count = sum(1 for r in tool_events if r.get("tool_success") is True)
    tool_success_rate_pct = round((tool_success_count / len(tool_events) * 100), 2) if tool_events else 100.0

    error_breakdown = defaultdict(int)
    for r in failed_events:
        error_breakdown[r.get("error_type", "UnknownError")] += 1

    error_status = "PASS" if error_rate_pct <= 2.0 else "BREACH"

    # 4. Cost Panel (response_sent)
    costs = [r.get("cost_usd", 0.0) for r in response_events]
    total_cost = round(sum(costs), 6)
    cost_threshold = 2.5
    cost_status = "PASS" if total_cost <= cost_threshold else "BREACH"

    cost_buckets = defaultdict(float)
    for r in response_events:
        dt = r.get("_dt")
        key = dt.strftime("%H:%M") if dt else "recent"
        cost_buckets[key] += r.get("cost_usd", 0.0)
    cost_series = [{"time": k, "cost": round(v, 6)} for k, v in sorted(cost_buckets.items())]

    # 5. Tokens Panel (response_sent)
    tokens_in_sum = sum(r.get("tokens_in", 0) for r in response_events)
    tokens_out_sum = sum(r.get("tokens_out", 0) for r in response_events)
    total_tokens = tokens_in_sum + tokens_out_sum
    token_threshold = 50000
    token_status = "PASS" if total_tokens <= token_threshold else "BREACH"

    token_buckets = defaultdict(lambda: {"in": 0, "out": 0})
    for r in response_events:
        dt = r.get("_dt")
        key = dt.strftime("%H:%M") if dt else "recent"
        token_buckets[key]["in"] += r.get("tokens_in", 0)
        token_buckets[key]["out"] += r.get("tokens_out", 0)
    token_series = [{"time": k, "in": v["in"], "out": v["out"]} for k, v in sorted(token_buckets.items())]

    # 6. Quality Panel (response_sent)
    quality_scores = [r.get("quality_score", 0.0) for r in response_events if "quality_score" in r]
    mean_quality = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0.0
    quality_threshold = 0.75
    quality_status = "PASS" if mean_quality >= quality_threshold else "BREACH"

    quality_series = []
    for r in response_events[-30:]:
        quality_series.append({
            "time": r.get("ts", "")[11:19] if r.get("ts") else "",
            "score": r.get("quality_score", 0.0),
            "correlation_id": r.get("correlation_id", "N/A"),
        })

    # Recent activity
    recent_logs = []
    for r in reversed(window_records[-20:]):
        recent_logs.append({
            "ts": r.get("ts", ""),
            "event": r.get("event", ""),
            "correlation_id": r.get("correlation_id", ""),
            "user_id_hash": r.get("user_id_hash", ""),
            "feature": r.get("feature", ""),
            "latency_ms": r.get("latency_ms", "-"),
            "tool_success": r.get("tool_success", "-"),
            "status": "Failed" if r.get("event") == "request_failed" else "OK",
        })

    return {
        "timestamp_utc": now_utc.isoformat(),
        "window_minutes": window_minutes,
        "summary": {
            "total_requests": total_requests,
            "total_failed": total_failed,
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "p95_latency": p95,
            "error_rate_pct": error_rate_pct,
            "mean_quality": mean_quality,
        },
        "panels": {
            "latency": {
                "title": "Latency percentiles and TTFT",
                "unit": "ms",
                "p50": p50,
                "p95": p95,
                "p99": p99,
                "ttft_p95": ttft_p95,
                "threshold": latency_threshold,
                "operator": "lte",
                "status": latency_status,
                "series": latency_series,
            },
            "traffic": {
                "title": "Request traffic",
                "unit": "requests_per_minute",
                "total_requests": total_requests,
                "rate_per_minute": rate_per_minute,
                "threshold": 1.0,
                "operator": "gte",
                "status": traffic_status,
                "series": traffic_series,
            },
            "errors": {
                "title": "Error rate and retrieval success",
                "unit": "percent",
                "error_rate_pct": error_rate_pct,
                "tool_success_rate_pct": tool_success_rate_pct,
                "breakdown": dict(error_breakdown),
                "threshold": 2.0,
                "operator": "lte",
                "status": error_status,
            },
            "cost": {
                "title": "Cost over time",
                "unit": "usd",
                "total": total_cost,
                "threshold": cost_threshold,
                "operator": "lte",
                "status": cost_status,
                "series": cost_series,
            },
            "tokens": {
                "title": "Input and output tokens",
                "unit": "tokens",
                "tokens_in": tokens_in_sum,
                "tokens_out": tokens_out_sum,
                "total": total_tokens,
                "threshold": token_threshold,
                "operator": "lte",
                "status": token_status,
                "series": token_series,
            },
            "quality": {
                "title": "Quality proxy",
                "unit": "score_0_to_1",
                "mean": mean_quality,
                "threshold": quality_threshold,
                "operator": "gte",
                "status": quality_status,
                "series": quality_series,
            },
        },
        "recent_logs": recent_logs,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>K4-L3B Day 13 Monitoring & LLMOps Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 26, 44, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(30, 42, 70, 0.85);
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.25);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: radial-gradient(circle at 10% 20%, rgba(56, 189, 248, 0.05) 0%, transparent 40%),
                        radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.05) 0%, transparent 40%);
      color: var(--text);
      font-family: 'Outfit', sans-serif;
      min-height: 100vh;
      padding: 24px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
    }
    .header-left h1 {
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .header-left .subtitle {
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: 'JetBrains Mono', monospace;
    }
    .header-right {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--success);
    }
    .badge.breach {
      background: rgba(239, 68, 68, 0.12);
      border-color: rgba(239, 68, 68, 0.3);
      color: var(--danger);
    }
    .badge .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 8px currentColor;
    }
    .btn {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent);
      padding: 8px 16px;
      border-radius: 8px;
      font-family: 'Outfit', sans-serif;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover {
      background: rgba(56, 189, 248, 0.25);
      border-color: var(--accent);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
      transition: transform 0.2s, border-color 0.2s;
      display: flex;
      flex-direction: column;
    }
    .card:hover {
      border-color: rgba(56, 189, 248, 0.3);
      transform: translateY(-2px);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
    }
    .card-meta {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 2px;
      font-family: 'JetBrains Mono', monospace;
    }
    .stat-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .stat-box {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 10px;
      padding: 10px 12px;
      text-align: left;
    }
    .stat-label {
      font-size: 11px;
      color: var(--text-muted);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .stat-value {
      font-size: 20px;
      font-weight: 700;
      color: var(--text);
      margin-top: 4px;
      font-family: 'JetBrains Mono', monospace;
    }
    .chart-container {
      position: relative;
      height: 180px;
      width: 100%;
      margin-top: auto;
    }
    .threshold-indicator {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 12px;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
    }
    th {
      text-align: left;
      padding: 12px 14px;
      color: var(--text-muted);
      border-bottom: 1px solid var(--card-border);
      font-weight: 600;
    }
    td {
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .status-ok { color: var(--success); font-weight: 600; }
    .status-fail { color: var(--danger); font-weight: 600; }
  </style>
</head>
<body>
  <div class="header">
    <div class="header-left">
      <h1>
        <span>⚡ K4-L3B LLMOps Monitoring Dashboard</span>
      </h1>
      <div class="subtitle">
        Project: <span style="color: var(--accent);">day13-k4-l3b-2A202602694</span> | Window: Last 60m UTC | Refresh: 15s | Target: FastAPI Live
      </div>
    </div>
    <div class="header-right">
      <div class="badge" id="overallStatus">
        <span class="dot"></span>
        <span id="overallStatusText">ALL CONTRACTS HEALTHY</span>
      </div>
      <button class="btn" onclick="fetchMetrics()">🔄 Refresh Now</button>
    </div>
  </div>

  <div class="grid">
    <!-- Panel 1: Latency -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">1. Latency Percentiles & TTFT</div>
          <div class="card-meta">events: [response_sent] | unit: ms</div>
        </div>
        <div class="badge" id="latencyBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">P50</div>
          <div class="stat-value" id="valP50">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">P95 (Target)</div>
          <div class="stat-value" id="valP95">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">P99</div>
          <div class="stat-value" id="valP99">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">TTFT P95</div>
          <div class="stat-value" id="valTtft">--</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="latencyChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>SLO Threshold: P95 &le; 3000 ms</span>
        <span id="latencyThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>

    <!-- Panel 2: Traffic -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">2. Request Traffic</div>
          <div class="card-meta">events: [request_received] | unit: req/min</div>
        </div>
        <div class="badge" id="trafficBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">Total Requests</div>
          <div class="stat-value" id="valTotalRequests">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Rate / Min</div>
          <div class="stat-value" id="valRateMin">--</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="trafficChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>Threshold: rate_per_minute &ge; 1</span>
        <span id="trafficThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>

    <!-- Panel 3: Errors -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">3. Error Rate & Tool Success</div>
          <div class="card-meta">events: [request_received, request_failed] | unit: %</div>
        </div>
        <div class="badge" id="errorsBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">Error Rate</div>
          <div class="stat-value" id="valErrorRate">--%</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Retrieval Success</div>
          <div class="stat-value" id="valRetrievalSuccess">--%</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="errorsChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>Threshold: error_rate_pct &le; 2.0%</span>
        <span id="errorsThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>

    <!-- Panel 4: Cost -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">4. Cost Over Time</div>
          <div class="card-meta">events: [response_sent] | unit: USD</div>
        </div>
        <div class="badge" id="costBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">Total 60m Cost</div>
          <div class="stat-value" id="valTotalCost">$0.00</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Budget Limit</div>
          <div class="stat-value">$2.50</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="costChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>Threshold: total &le; $2.50</span>
        <span id="costThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>

    <!-- Panel 5: Tokens -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">5. Input & Output Tokens</div>
          <div class="card-meta">events: [response_sent] | unit: tokens</div>
        </div>
        <div class="badge" id="tokensBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">Total Tokens</div>
          <div class="stat-value" id="valTotalTokens">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Tokens In</div>
          <div class="stat-value" id="valTokensIn">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Tokens Out</div>
          <div class="stat-value" id="valTokensOut">--</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="tokensChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>Threshold: sum_by_field &le; 50,000</span>
        <span id="tokensThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>

    <!-- Panel 6: Quality -->
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">6. Quality Proxy</div>
          <div class="card-meta">events: [response_sent] | unit: score (0–1)</div>
        </div>
        <div class="badge" id="qualityBadge">PASS</div>
      </div>
      <div class="stat-row">
        <div class="stat-box">
          <div class="stat-label">Mean Quality Score</div>
          <div class="stat-value" id="valMeanQuality">--</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Threshold Min</div>
          <div class="stat-value">0.75</div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="qualityChart"></canvas>
      </div>
      <div class="threshold-indicator">
        <span>Threshold: mean &ge; 0.75</span>
        <span id="qualityThresholdStatus" style="color: var(--success);">In Spec</span>
      </div>
    </div>
  </div>

  <!-- Recent Logs Table -->
  <div class="table-container">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="font-size:16px; font-weight:600;">Recent Structured Activity Logs (data/logs.jsonl)</h3>
      <span style="font-size:12px; color:var(--text-muted); font-family:'JetBrains Mono';">Auto-linked by correlation_id</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Timestamp (UTC)</th>
          <th>Event</th>
          <th>Correlation ID</th>
          <th>User Hash</th>
          <th>Feature</th>
          <th>Latency</th>
          <th>Retrieval</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="logsTableBody">
        <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">Loading logs...</td></tr>
      </tbody>
    </table>
  </div>

  <script>
    let charts = {};

    function initCharts() {
      const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } } } },
        scales: {
          x: { ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
        }
      };

      // 1. Latency Chart
      charts.latency = new Chart(document.getElementById('latencyChart'), {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Latency (ms)', data: [], borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.1)', tension: 0.3, fill: true },
            { label: 'TTFT (ms)', data: [], borderColor: '#818cf8', borderDash: [4, 4], tension: 0.3 },
            { label: 'Threshold (3000ms)', data: [], borderColor: '#ef4444', borderDash: [6, 6], pointRadius: 0, borderWidth: 1.5 }
          ]
        },
        options: commonOptions
      });

      // 2. Traffic Chart
      charts.traffic = new Chart(document.getElementById('trafficChart'), {
        type: 'bar',
        data: {
          labels: [],
          datasets: [
            { label: 'Requests / min', data: [], backgroundColor: 'rgba(56, 189, 248, 0.4)', borderColor: '#38bdf8', borderWidth: 1 }
          ]
        },
        options: commonOptions
      });

      // 3. Errors Breakdown Chart
      charts.errors = new Chart(document.getElementById('errorsChart'), {
        type: 'bar',
        data: {
          labels: ['Error Rate %', 'Tool Success %'],
          datasets: [
            { label: 'Metric %', data: [0, 100], backgroundColor: ['rgba(239, 68, 68, 0.6)', 'rgba(16, 185, 129, 0.6)'] }
          ]
        },
        options: {
          ...commonOptions,
          scales: { y: { min: 0, max: 100, ticks: { color: '#64748b' } } }
        }
      });

      // 4. Cost Chart
      charts.cost = new Chart(document.getElementById('costChart'), {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Cost ($)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', tension: 0.3, fill: true },
            { label: 'Limit ($2.50)', data: [], borderColor: '#ef4444', borderDash: [6, 6], pointRadius: 0 }
          ]
        },
        options: commonOptions
      });

      // 5. Tokens Chart
      charts.tokens = new Chart(document.getElementById('tokensChart'), {
        type: 'bar',
        data: {
          labels: [],
          datasets: [
            { label: 'Tokens In', data: [], backgroundColor: 'rgba(99, 102, 241, 0.6)' },
            { label: 'Tokens Out', data: [], backgroundColor: 'rgba(168, 85, 247, 0.6)' }
          ]
        },
        options: {
          ...commonOptions,
          scales: { x: { stacked: true }, y: { stacked: true } }
        }
      });

      // 6. Quality Chart
      charts.quality = new Chart(document.getElementById('qualityChart'), {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            { label: 'Quality Score', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', tension: 0.3, fill: true },
            { label: 'Target &ge; 0.75', data: [], borderColor: '#f59e0b', borderDash: [6, 6], pointRadius: 0 }
          ]
        },
        options: {
          ...commonOptions,
          scales: { y: { min: 0, max: 1.0, ticks: { color: '#64748b' } } }
        }
      });
    }

    async function fetchMetrics() {
      try {
        const res = await fetch('/api/dashboard/metrics');
        const data = await res.json();
        updateUI(data);
      } catch (err) {
        console.error('Failed to load metrics:', err);
      }
    }

    function updateBadge(id, isPass) {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = isPass ? 'PASS' : 'BREACH';
      el.className = isPass ? 'badge' : 'badge breach';
    }

    function updateUI(data) {
      const p = data.panels;

      // 1. Latency
      document.getElementById('valP50').textContent = p.latency.p50 + ' ms';
      document.getElementById('valP95').textContent = p.latency.p95 + ' ms';
      document.getElementById('valP99').textContent = p.latency.p99 + ' ms';
      document.getElementById('valTtft').textContent = p.latency.ttft_p95 + ' ms';
      updateBadge('latencyBadge', p.latency.status === 'PASS');
      const latSeries = p.latency.series || [];
      charts.latency.data.labels = latSeries.map(s => s.time);
      charts.latency.data.datasets[0].data = latSeries.map(s => s.latency);
      charts.latency.data.datasets[1].data = latSeries.map(s => s.ttft);
      charts.latency.data.datasets[2].data = latSeries.map(() => 3000);
      charts.latency.update();

      // 2. Traffic
      document.getElementById('valTotalRequests').textContent = p.traffic.total_requests;
      document.getElementById('valRateMin').textContent = p.traffic.rate_per_minute;
      updateBadge('trafficBadge', p.traffic.status === 'PASS');
      const trafSeries = p.traffic.series || [];
      charts.traffic.data.labels = trafSeries.map(s => s.time);
      charts.traffic.data.datasets[0].data = trafSeries.map(s => s.count);
      charts.traffic.update();

      // 3. Errors
      document.getElementById('valErrorRate').textContent = p.errors.error_rate_pct + '%';
      document.getElementById('valRetrievalSuccess').textContent = p.errors.tool_success_rate_pct + '%';
      updateBadge('errorsBadge', p.errors.status === 'PASS');
      charts.errors.data.datasets[0].data = [p.errors.error_rate_pct, p.errors.tool_success_rate_pct];
      charts.errors.update();

      // 4. Cost
      document.getElementById('valTotalCost').textContent = '$' + p.cost.total.toFixed(4);
      updateBadge('costBadge', p.cost.status === 'PASS');
      const costSeries = p.cost.series || [];
      charts.cost.data.labels = costSeries.map(s => s.time);
      charts.cost.data.datasets[0].data = costSeries.map(s => s.cost);
      charts.cost.data.datasets[1].data = costSeries.map(() => 2.5);
      charts.cost.update();

      // 5. Tokens
      document.getElementById('valTotalTokens').textContent = p.tokens.total.toLocaleString();
      document.getElementById('valTokensIn').textContent = p.tokens.tokens_in.toLocaleString();
      document.getElementById('valTokensOut').textContent = p.tokens.tokens_out.toLocaleString();
      updateBadge('tokensBadge', p.tokens.status === 'PASS');
      const tokSeries = p.tokens.series || [];
      charts.tokens.data.labels = tokSeries.map(s => s.time);
      charts.tokens.data.datasets[0].data = tokSeries.map(s => s.in);
      charts.tokens.data.datasets[1].data = tokSeries.map(s => s.out);
      charts.tokens.update();

      // 6. Quality
      document.getElementById('valMeanQuality').textContent = p.quality.mean.toFixed(2);
      updateBadge('qualityBadge', p.quality.status === 'PASS');
      const qualSeries = p.quality.series || [];
      charts.quality.data.labels = qualSeries.map(s => s.time);
      charts.quality.data.datasets[0].data = qualSeries.map(s => s.score);
      charts.quality.data.datasets[1].data = qualSeries.map(() => 0.75);
      charts.quality.update();

      // Recent logs table
      const tbody = document.getElementById('logsTableBody');
      tbody.innerHTML = '';
      (data.recent_logs || []).forEach(log => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td>${log.ts ? log.ts.substring(11, 19) : '-'}</td>
          <td><b>${log.event}</b></td>
          <td><span style="color:var(--accent);">${log.correlation_id}</span></td>
          <td>${log.user_id_hash}</td>
          <td>${log.feature}</td>
          <td>${log.latency_ms !== '-' ? log.latency_ms + 'ms' : '-'}</td>
          <td>${log.tool_success === true ? '<span class="status-ok">SUCCESS</span>' : (log.tool_success === false ? '<span class="status-fail">FAILED</span>' : '-')}</td>
          <td><span class="${log.status === 'OK' ? 'status-ok' : 'status-fail'}">${log.status}</span></td>
        `;
        tbody.appendChild(row);
      });
    }

    window.addEventListener('DOMContentLoaded', () => {
      initCharts();
      fetchMetrics();
      setInterval(fetchMetrics, 15000);
    });
  </script>
</body>
</html>
"""

dashboard_app = FastAPI(title="Day 13 LLMOps Dashboard")


@dashboard_app.get("/", response_class=HTMLResponse)
async def get_dashboard_html() -> str:
    return HTML_TEMPLATE


@dashboard_app.get("/api/dashboard/metrics")
async def get_dashboard_metrics() -> dict[str, Any]:
    return compute_dashboard_metrics()


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "8501"))
    print(f"Starting standalone dashboard on http://127.0.0.1:{port}")
    uvicorn.run("dashboard.app:dashboard_app", host="127.0.0.1", port=port, reload=False)
