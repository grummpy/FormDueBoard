"""Printable HTML checklist, one section per kid."""

from __future__ import annotations

import html


def render_checklist(board: dict) -> str:
    sections = []
    for kid in board["kids"]:
        rows = []
        for item in kid["items"]:
            if item["cancelled"]:
                mark = "Cancelled"
            elif item["status"] == "returned":
                mark = "Returned"
            elif item["status"] == "signed":
                mark = "Signed"
            else:
                mark = "To do"
            due = item["due_display"] or "No date"
            fee = f" · ${item['fee_amount']}" if item.get("fee_amount") else ""
            rows.append(
                "<li>"
                f"<span class='box'>{'☑' if item['status'] != 'todo' or item['cancelled'] else '☐'}</span>"
                f"<span><strong>{html.escape(item['title'])}</strong>"
                f"<em>{html.escape(item['form_label'])} · Due {html.escape(due)}{html.escape(fee)}</em>"
                f"<small>{html.escape(mark)}</small></span></li>"
            )
        body = "".join(rows) or "<li class='empty'>Nothing filed.</li>"
        grade = f" · Grade {html.escape(str(kid['grade']))}" if kid.get("grade") else ""
        sections.append(f"<section><h2>{html.escape(kid['name'])}{grade}</h2><ul>{body}</ul></section>")
    review_rows = []
    for item in board["review"]:
        review_rows.append(
            "<li><strong>"
            + html.escape(item["title"])
            + "</strong><em>"
            + html.escape(item.get("review_reason") or "Needs a look")
            + "</em></li>"
        )
    review = ""
    if review_rows:
        review = "<section><h2>Needs a look</h2><ul>" + "".join(review_rows) + "</ul></section>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FormDueBoard checklist</title>
<style>
  body {{ font-family: "Trebuchet MS", "Segoe UI", sans-serif; color: #1b2a4a; margin: 32px; }}
  h1 {{ font-size: 28px; margin-bottom: 0; }}
  h1 span.due {{ color: #e23b32; }}
  p.meta {{ color: #6e6256; }}
  section {{ break-inside: avoid; margin-top: 24px; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid #ecd9b0; }}
  em {{ display: block; font-style: normal; color: #6e6256; }}
  .box {{ font-size: 20px; }}
  @media print {{
    button {{ display: none; }}
    body {{ margin: 0.5in; }}
  }}
</style>
</head>
<body>
<h1>Form<span class="due">Due</span>Board</h1>
<p class="meta">Checklist for {html.escape(board["today"])}. Printed from this computer.</p>
<button onclick="window.print()">Print</button>
{"".join(sections)}
{review}
</body>
</html>
"""
