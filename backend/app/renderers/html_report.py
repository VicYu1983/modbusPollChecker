from __future__ import annotations

from html import escape

from ..services.report_service import ReportContext


class HtmlReportRenderer:
    content_type = "text/html; charset=utf-8"
    file_extension = "html"

    def render(self, context: ReportContext) -> bytes:
        rows = []
        for comparison in context.comparison.comparisons:
            record = comparison.current or comparison.baseline
            if record is None:
                continue
            result = comparison.current.result if comparison.current else None
            baseline = comparison.baseline.result if comparison.baseline else None
            values = (
                ", ".join(str(value) for value in result.values) or "-"
                if result
                else "未檢查"
            )
            baseline_values = (
                ", ".join(str(value) for value in baseline.values) or "-"
                if baseline
                else "-"
            )
            rows.append(
                "<tr>"
                f"<td>{escape(comparison.device_name)}</td>"
                f"<td>{escape(str(record.device_snapshot.ip))}:{record.device_snapshot.port}</td>"
                f"<td>{escape(result.status if result else 'NOT_CHECKED')}</td>"
                f"<td>{escape(values)}</td>"
                f"<td>{f'{result.elapsed_ms} ms' if result else '-'}</td>"
                f"<td>{f'{comparison.response_time_delta_ms:+} ms' if comparison.response_time_delta_ms is not None else '-'}</td>"
                f"<td>{escape(comparison.status)}</td>"
                f"<td>{escape(baseline_values)}</td>"
                f"<td>{escape(result.error_message or '') if result else ''}</td>"
                "</tr>"
            )
        completed_at = context.batch.completed_at or context.batch.started_at
        title = escape(context.batch.site_name)
        batch_id = escape(context.batch.id)
        comparison_summary = (
            f"基準批次：{escape(context.comparison.baseline_batch_id)}"
            if context.comparison.baseline_batch_id
            else "尚未設定比較基準"
        )
        document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} Modbus 回歸檢查報告</title>
  <style>
    :root {{ color-scheme: light; font-family: "Segoe UI", sans-serif; color: #182322; background: #f3f6f4; }}
    body {{ margin: 0; padding: 32px; }}
    main {{ max-width: 1200px; margin: 0 auto; }}
    header {{ border-bottom: 3px solid #16836f; padding-bottom: 20px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 6px 0; color: #52605d; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px 28px; margin: 18px 0; }}
    .summary strong {{ color: #182322; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #dfe7e3; white-space: nowrap; }}
    th {{ background: #e6efeb; }}
    td:last-child {{ white-space: normal; min-width: 180px; }}
    footer {{ margin-top: 20px; color: #687571; font-size: 13px; }}
    @media (max-width: 600px) {{ body {{ padding: 16px; }} h1 {{ font-size: 22px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{title} · Modbus 回歸檢查報告</h1>
      <p>批次編號：{batch_id}</p>
      <p>開始時間：{escape(context.batch.started_at.isoformat())}</p>
      <p>完成時間：{escape(completed_at.isoformat())}</p>
      <p>{comparison_summary}</p>
    </header>
    <section class="summary">
      <span>設備總數 <strong>{len(context.batch.device_names)}</strong></span>
      <span>通過 <strong>{context.batch.pass_count}</strong></span>
      <span>失敗 <strong>{context.batch.fail_count}</strong></span>
      <span>逾時 <strong>{context.batch.timeout_count}</strong></span>
      <span>設定錯誤 <strong>{context.batch.config_error_count}</strong></span>
    </section>
    <div class="table-wrap">
      <table>
        <thead><tr><th>設備</th><th>IP / Port</th><th>狀態</th><th>本次讀值</th><th>耗時</th><th>耗時差</th><th>差異</th><th>基準讀值</th><th>錯誤訊息</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <footer>報告產生時間：{escape(context.generated_at.isoformat())}</footer>
  </main>
</body>
</html>"""
        return document.encode("utf-8")