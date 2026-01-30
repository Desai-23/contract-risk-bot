from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

from src.config import EXPORT_DIR


def _wrap_text(c: canvas.Canvas, text: str, x: float, y: float, max_chars: int = 110, line_height: int = 13):
    """
    Simple word wrap by max character count (fast + hackathon-safe).
    """
    words = (text or "").split()
    line = ""
    for w in words:
        test = f"{line} {w}".strip()
        if len(test) <= max_chars:
            line = test
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = w
    if line:
        c.drawString(x, y, line)
        y -= line_height
    return y


def generate_pdf_report(
    filename_base: str,
    contract_summary: Dict[str, Any],
    high_risk_text: str,
    red_flags_text: str,
    disclaimer: str,
) -> str:
    """
    Writes a PDF to exports/ and returns the absolute file path.
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(EXPORT_DIR, f"{filename_base}_risk_report_{ts}.pdf")

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    x = 2 * cm
    y = height - 2 * cm

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "Contract Risk Assessment Report")
    y -= 22


    # Executive summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Executive Summary")
    y -= 18

    c.setFont("Helvetica", 11)
    overall = contract_summary.get("overall_risk", "Unclear")
    avg = contract_summary.get("avg_score", "0.0")
    counts = contract_summary.get("counts", {})

    y = _wrap_text(c, f"Overall Contract Risk: {overall}", x, y)
    y = _wrap_text(c, f"Average Risk Score: {avg}", x, y)
    y = _wrap_text(
        c,
        f"Clause Risk Distribution: High={counts.get('High',0)}, Medium={counts.get('Medium',0)}, "
        f"Low={counts.get('Low',0)}, Unclear={counts.get('Unclear',0)}",
        x,
        y,
    )

    y -= 8

    # Red flags
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Detected Red Flags (Rule-based)")
    y -= 18

    c.setFont("Helvetica", 10)
    for line in (red_flags_text or "").splitlines():
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 10)
        y = _wrap_text(c, line, x, y, max_chars=120, line_height=12)

    y -= 8

    # High-risk clauses
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Top High-Risk Clauses (LLM subset)")
    y -= 18

    c.setFont("Helvetica", 10)
    for block in (high_risk_text or "").split("\n\n"):
        if not block.strip():
            continue
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 10)
        y = _wrap_text(c, block, x, y, max_chars=120, line_height=12)
        y -= 6

    # Disclaimer 
    if y < 4 * cm:
        c.showPage()
        y = height - 2 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Disclaimer")
    y -= 18

    c.setFont("Helvetica", 9)
    y = _wrap_text(c, disclaimer, x, y, max_chars=130, line_height=11)

    c.save()
    return os.path.abspath(out_path)

