import sys
from pathlib import Path
import os
import gradio as gr

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.audit.logger import append_audit_event
from src.ingestion.loader import load_text_from_upload
from src.nlp.preprocess import preprocess_contract
from src.llm.ollama_client import analyze_clause_with_llm
from src.risk.scoring import normalize_risk
from src.risk.aggregator import ClauseAnalysis, aggregate_contract
from src.export.pdf_report import generate_pdf_report
from src.negotiation.rewrite import rewrite_clause
from src.risk.selector import smart_select_clauses


def process_upload(file_path):
    """
    Returns:
      status,
      original_preview,
      normalized_preview,
      detected_language,
      dropdown_update,
      first_clause_text,
      clause_map,
      clauses_list
    """
    if file_path is None:
        return (
            "No file uploaded.",
            "",
            "",
            "",
            gr.update(choices=[], value=None),
            "",
            {},
            [],
        )

    file_path_str = str(file_path)
    filename = os.path.basename(file_path_str)

    try:
        with open(file_path_str, "rb") as f:
            content = f.read()

        loaded = load_text_from_upload(filename, content)
        prep = preprocess_contract(loaded.text)

        append_audit_event(
            {
                "event": "upload_and_extract",
                "filename": loaded.filename,
                "doc_type": loaded.doc_type,
                "language_detected": prep.language,
                "language_normalized": prep.normalized_language,
                "did_normalize": prep.did_normalize,
                "chars_extracted": len(loaded.text),
                "chars_normalized": len(prep.normalized_text),
                "clauses_extracted": len(prep.clauses),
            }
        )

        clause_labels = []
        for c in prep.clauses:
            preview_text = c.text[:80].replace("\n", " ")
            clause_labels.append(f"{c.clause_id} — {preview_text}...")

        clause_map = {label: c.text for label, c in zip(clause_labels, prep.clauses)}

        status = (
            f"✅ Loaded: {loaded.doc_type.upper()} | "
            f"Language: {prep.language.upper()} → {prep.normalized_language.upper()} | "
            f"Normalized: {prep.did_normalize} | "
            f"Chars: {len(loaded.text)} | Clauses: {len(prep.clauses)}"
        )

        original_preview = loaded.text[:8000]
        normalized_preview = prep.normalized_text[:8000]

        dropdown_update = gr.update(
            choices=clause_labels,
            value=clause_labels[0] if clause_labels else None,
        )

        first_clause_text = clause_map[clause_labels[0]] if clause_labels else ""
        clauses_list = [{"clause_id": c.clause_id, "text": c.text} for c in prep.clauses]

        return (
            status,
            original_preview,
            normalized_preview,
            prep.language,
            dropdown_update,
            first_clause_text,
            clause_map,
            clauses_list,
        )

    except Exception as e:
        return (
            f"❌ Error: {e}",
            "",
            "",
            "",
            gr.update(choices=[], value=None),
            "",
            {},
            [],
        )


def show_selected_clause(selected_label, clause_map):
    if not selected_label or not clause_map:
        return ""
    return clause_map.get(selected_label, "")


def analyze_selected_clause(selected_label, clause_map):
    """
    Runs LLM analysis on the selected clause (normalized English).
    """
    if not selected_label or not clause_map:
        return "", "", "", ""

    clause_text = clause_map[selected_label]
    llm_raw = analyze_clause_with_llm(clause_text)
    result = normalize_risk(llm_raw)

    append_audit_event(
        {
            "event": "llm_clause_analysis",
            "clause_type": result["clause_type"],
            "risk_level": result["risk_level"],
            "chars_clause": len(clause_text),
        }
    )

    return (
        result["clause_type"],
        result["explanation"],
        f"{result['risk_level']} — {result['risk_reason']}",
        result["mitigation"],
    )


def analyze_full_contract(clauses_list):
    """
    Smart selection:
      - scans ALL clauses quickly
      - selects high-signal clauses for LLM
      - aggregates risk + red flags
    Returns:
      overall_risk, avg_score, counts_line, high_risk_text, red_flags_text, summary_dict
    """
    if not clauses_list:
        return (
            "Unclear",
            "0.0",
            "High: 0 | Medium: 0 | Low: 0 | Unclear: 0",
            "No clauses found.",
            "[]",
            {},
        )

    # Smart selection instead of first N clauses
    selected, sel_stats = smart_select_clauses(
        clauses_list,
        max_llm_clauses=12,   # keep same speed budget
        ensure_baseline=2,    # always include first 2 clauses
    )

    clause_results = []
    selection_debug = []

    for c in selected:
        llm_raw = analyze_clause_with_llm(c.text)
        result = normalize_risk(llm_raw)

        clause_results.append(
            ClauseAnalysis(
                clause_id=c.clause_id,
                clause_text=c.text,
                clause_type=result["clause_type"],
                risk_level=result["risk_level"],
                risk_reason=result["risk_reason"],
            )
        )

        selection_debug.append(
            {
                "clause_id": c.clause_id,
                "selection_score": c.score,
                "selection_reasons": c.reasons,
            }
        )

    summary = aggregate_contract(clause_results)

    append_audit_event(
        {
            "event": "llm_contract_analysis_smart_select",
            "selection_stats": sel_stats,
            "selected_clause_debug": selection_debug[:20],  # cap log size
            "overall_risk": summary["overall_risk"],
            "avg_score": summary["avg_score"],
            "counts": summary["counts"],
            "red_flags_count": len(summary["red_flags"]),
        }
    )

    counts = summary["counts"]
    counts_line = (
        f"High: {counts.get('High', 0)} | "
        f"Medium: {counts.get('Medium', 0)} | "
        f"Low: {counts.get('Low', 0)} | "
        f"Unclear: {counts.get('Unclear', 0)}"
    )

    high_risk_text = "\n\n".join(
        [
            f"- {x['clause_id']} ({x['clause_type']}): {x['risk_reason']}\n  {x['text_preview']}"
            for x in summary["top_high_risk"]
        ]
    ) or "No High-risk clauses detected in analyzed subset."

    red_flags_text = "\n".join(
        [f"- [{x['severity']}] {x['flag_type']}: {x['reason']}" for x in summary["red_flags"]]
    ) or "No rule-based red flags detected."

    return summary["overall_risk"], str(summary["avg_score"]), counts_line, high_risk_text, red_flags_text, summary



def export_pdf(contract_summary, high_risk_text, red_flags_text):
    """
    Generates a PDF and returns the file path for Gradio File output.
    """
    if not contract_summary:
        return None

    disclaimer = (
        "This report is generated automatically for informational purposes only and does not constitute legal advice. "
        "For decisions that may have legal or financial impact, consult a qualified legal professional."
    )

    out_path = generate_pdf_report(
        filename_base="contract",
        contract_summary=contract_summary,
        high_risk_text=high_risk_text,
        red_flags_text=red_flags_text,
        disclaimer=disclaimer,
    )

    append_audit_event(
        {
            "event": "export_pdf_report",
            "output_path": out_path,
            "overall_risk": contract_summary.get("overall_risk", "Unclear"),
        }
    )

    return out_path


def suggest_rewrite(selected_label, clause_map):
    """
    LLM-based unfavorable clause assessment + rewrite + negotiation points.
    """
    if not selected_label or not clause_map:
        return "", "", ""

    clause_text = clause_map[selected_label]
    out = rewrite_clause(clause_text, party_perspective="SME")

    append_audit_event(
        {
            "event": "rewrite_suggestion",
            "is_unfavorable": out.get("is_unfavorable", False),
            "chars_clause": len(clause_text),
        }
    )

    points = "\n".join([f"- {p}" for p in out.get("negotiation_points", [])]) or ""
    combined = out.get("suggested_rewrite", "")

    if points:
        combined = combined + "\n\nNegotiation Points:\n" + points

    return str(out.get("is_unfavorable", False)), out.get("why_unfavorable", ""), combined


with gr.Blocks(title="Contract Risk Bot — Phase 7") as demo:
    gr.Markdown("# Contract Risk Bot — Phase 7 [smart clause selection]")
    gr.Markdown(
        "Flow:\n"
        "1) Upload → Process\n"
        "2) Analyze Selected Clause (optional)\n"
        "3) Analyze Full Contract (recommended)\n"
        "4) Export PDF (optional)\n"
        "5) Suggest SME-Friendly Rewrite for selected clause\n"
        "6) rewrite and negotiation suggestions\n"
        "7) smart clause selection"
    )

    clause_map_state = gr.State({})
    clauses_state = gr.State([])
    contract_summary_state = gr.State({})

    with gr.Row():
        file_in = gr.File(label="Upload Contract", file_types=[".pdf", ".docx", ".txt"])
        process_btn = gr.Button("Process")

    status = gr.Textbox(label="Status", interactive=False)
    lang = gr.Textbox(label="Detected Language (Original)", interactive=False)

    original_preview = gr.Textbox(label="Original Text Preview (first 8000 chars)", lines=8)
    normalized_preview = gr.Textbox(label="Normalized English Text Preview (first 8000 chars)", lines=8)

    clause_dropdown = gr.Dropdown(label="Clauses (normalized)", choices=[], value=None)
    clause_text = gr.Textbox(label="Selected Clause Text (normalized)", lines=8)

    analyze_btn = gr.Button("Analyze Selected Clause")
    clause_type = gr.Textbox(label="Clause Type", interactive=False)
    explanation = gr.Textbox(label="Plain-English Explanation", lines=4)
    risk = gr.Textbox(label="Risk Assessment", interactive=False)
    mitigation = gr.Textbox(label="Suggested Mitigation", lines=3)

    full_analyze_btn = gr.Button("Analyze Full Contract (Sample-based)")
    overall_risk = gr.Textbox(label="Overall Contract Risk", interactive=False)
    avg_score = gr.Textbox(label="Average Risk Score", interactive=False)
    risk_counts = gr.Textbox(label="Clause Risk Distribution", interactive=False)
    top_high_risk = gr.Textbox(label="Top High-Risk Clauses (subset)", lines=8)
    red_flags = gr.Textbox(label="Detected Red Flags (rule-based)", lines=8)

    export_btn = gr.Button("Export PDF Report")
    pdf_file = gr.File(label="Download Report (PDF)", interactive=False)

    # Phase 6 UI
    rewrite_btn = gr.Button("Suggest SME-Friendly Rewrite")
    is_unfavorable = gr.Textbox(label="Is Unfavorable?", interactive=False)
    why_unfavorable = gr.Textbox(label="Why Unfavorable", lines=4)
    rewrite_text = gr.Textbox(label="Suggested Rewrite + Negotiation Points", lines=10)

    process_btn.click(
        process_upload,
        inputs=[file_in],
        outputs=[
            status,
            original_preview,
            normalized_preview,
            lang,
            clause_dropdown,
            clause_text,
            clause_map_state,
            clauses_state,
        ],
    )

    clause_dropdown.change(
        show_selected_clause,
        inputs=[clause_dropdown, clause_map_state],
        outputs=[clause_text],
    )

    analyze_btn.click(
        analyze_selected_clause,
        inputs=[clause_dropdown, clause_map_state],
        outputs=[clause_type, explanation, risk, mitigation],
    )

    full_analyze_btn.click(
        analyze_full_contract,
        inputs=[clauses_state],
        outputs=[overall_risk, avg_score, risk_counts, top_high_risk, red_flags, contract_summary_state],
    )

    export_btn.click(
        export_pdf,
        inputs=[contract_summary_state, top_high_risk, red_flags],
        outputs=[pdf_file],
    )

    rewrite_btn.click(
        suggest_rewrite,
        inputs=[clause_dropdown, clause_map_state],
        outputs=[is_unfavorable, why_unfavorable, rewrite_text],
    )

demo.launch(server_name="127.0.0.1", server_port=7860)

