from __future__ import annotations

from html import escape

from ..domain.network_models import NetworkReportContext


class NetworkHtmlReportRenderer:
    content_type = "text/html; charset=utf-8"
    file_extension = "html"

    def render(self, context: NetworkReportContext) -> bytes:
        trends = {item.device_name: item for item in context.trend.devices}
        rows: list[str] = []
        for record in context.results:
            result = record.result
            trend = trends.get(result.device_name)
            suggestions = "<br>".join(escape(item) for item in result.diagnosis_suggestions) or "-"
            violations = "<br>".join(escape(item) for item in result.threshold_violations) or "-"
            rows.append(
                "<tr>"
                f"<td>{escape(result.device_name)}<small>{escape(str(result.target_ip))}</small></td>"
                f"<td>{escape(result.ping_state)}<small>{self._number(result.ping_avg_ms)} ms avg</small></td>"
                f"<td>{self._number(result.ping_loss_percent)}%</td>"
                f"<td>{escape(result.tcp_state)}<small>{result.tcp_port or '-'} · {self._number(result.tcp_connect_ms)} ms</small></td>"
                f"<td>{self._number(record.device_snapshot.max_latency_ms)} ms / {self._number(record.device_snapshot.max_loss_percent)}%</td>"
                f"<td>{escape(result.overall_status)}<small>{escape(result.failure_stage or '-')}</small></td>"
                f"<td>{escape(result.diagnosis_summary or result.error_message or '-')}<small>{escape(result.error_type or '')} {escape(result.error_message or '')}<br>{suggestions}</small></td>"
                f"<td>{violations}</td>"
                f"<td>{self._number(trend.latency_delta_ms) if trend and trend.latency_delta_ms is not None else '-'} ms"
                f"<small>{self._number(trend.loss_delta_percent) if trend and trend.loss_delta_percent is not None else '-'} percentage points</small></td>"
                f"<td>{escape(trend.summary) if trend else '尚無比較資料'}</td>"
                "</tr>"
            )
        batch = context.batch
        completed_at = batch.completed_at or batch.started_at
        document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(batch.site_name)} 網路健檢報告</title>
  <style>
    :root {{ color-scheme: light; font-family: "Segoe UI", sans-serif; color: #182522; background: #f2f5f1; }}
    body {{ margin: 0; padding: 32px; }}
    main {{ max-width: 1500px; margin: 0 auto; }}
    header {{ border-bottom: 3px solid #1b5b4c; padding-bottom: 20px; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 6px 0; color: #61706b; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px 28px; margin: 18px 0; }}
    .summary strong {{ color: #182522; }}
    .trend {{ padding: 14px 0; margin: 18px 0; border-top: 1px solid #d8e1da; border-bottom: 1px solid #d8e1da; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid #dfe7e3; }}
    th {{ background: #e5eee8; white-space: nowrap; }}
    td {{ min-width: 90px; }}
    td:nth-child(6), td:nth-child(7), td:last-child {{ min-width: 180px; }}
    small {{ display: block; color: #687671; margin-top: 4px; white-space: normal; }}
    footer {{ margin-top: 20px; color: #687571; font-size: 13px; }}
    @media (max-width: 700px) {{ body {{ padding: 16px; }} h1 {{ font-size: 22px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(batch.site_name)} · 網路健檢報告</h1>
      <p>批次編號：{escape(batch.id)}</p>
      <p>測試模式：{escape(batch.mode)}</p>
      <p>開始時間：{escape(batch.started_at.isoformat())}</p>
      <p>完成時間：{escape(completed_at.isoformat())}</p>
      <p>最大並行數：{batch.max_concurrency}</p>
    </header>
    <section class="summary">
      <span>設備總數 <strong>{len(batch.device_names)}</strong></span>
      <span>已完成 <strong>{batch.completed_device_count}</strong></span>
      <span>通過 <strong>{batch.pass_count}</strong></span>
      <span>失敗 <strong>{batch.fail_count}</strong></span>
      <span>逾時 <strong>{batch.timeout_count}</strong></span>
      <span>部分正常 <strong>{batch.partial_count}</strong></span>
      <span>設定錯誤 <strong>{batch.config_error_count}</strong></span>
    </section>
    <section class="trend">
      <strong>歷史趨勢摘要</strong>
      <p>{escape(context.trend.summary)}</p>
      <p>比較批次數：{context.trend.historical_batch_count}；延遲增加：{context.trend.latency_degraded_count} 台；封包遺失增加：{context.trend.loss_degraded_count} 台；間歇性未通過：{context.trend.intermittent_disconnect_count} 台。</p>
    </section>
    <div class="table-wrap">
      <table>
        <thead><tr><th>設備 / IP</th><th>Ping</th><th>封包遺失</th><th>TCP</th><th>門檻（延遲 / 遺失）</th><th>總狀態</th><th>診斷 / 建議</th><th>門檻違規</th><th>趨勢差異</th><th>歷史摘要</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <footer>報告產生時間：{escape(context.generated_at.isoformat())}</footer>
  </main>
</body>
</html>"""
        return document.encode("utf-8")

    @staticmethod
    def _number(value: float | int | None) -> str:
        return "-" if value is None else f"{value:.1f}"
