import sys
from pathlib import Path
import os
import gradio as gr

# Add project root to Python path (so `src.*` imports work reliably)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.audit.logger import append_audit_event
from src.ingestion.loader import load_text_from_upload
from src.nlp.preprocess import preprocess_contract
from src.llm.ollama_client import analyze_clause_with_llm
from src.risk.scoring import normalize_risk

# Phase 3 imports
from src.risk.aggregator import ClauseAnalysis, aggregate_contract


def process_upload(file_path):
    """
    Gradio may pass a NamedString (path-like) instead of a file object.
    So we treat input as a file path and read bytes from disk.

    Returns:
      status, preview, language, dropdown_update, first_clause_text, clause_map, clauses_list
    """
    if file_path is None:
        return "No file uploaded.", "", "", gr.update(choices=[], value=None), "", {}, []

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
                "language": prep.language,
                "chars_extracted": len(loaded.text),
                "clauses_extracted": len(prep.clauses),
            }
        )

        # Build dropdown labels
        clause_labels = []
        for c in prep.clauses:
            preview_text = c.text[:80].replace("\n", " ")
            clause_labels.append(f"{c.clause_id} — {preview_text}...")

        clause_map = {label: c.text for label, c in zip(clause_labels, prep.clauses)}

        status = (
            f"✅ Loaded: {loaded.doc_type.upper()} | "
            f"Language: {prep.language.upper()} | "
            f"Chars: {len(loaded.text)} | Clauses: {len(prep.clauses)}"
        )
        preview = loaded.text[:8000]

        dropdown_update = gr.update(
            choices=clause_labels,
            value=clause_labels[0] if clause_labels else None,
        )

        first_clause_text = clause_map[clause_labels[0]] if clause_labels else ""

        # Phase 3: list of clauses with ids + text
        clauses_list = [{"clause_id": c.clause_id, "text": c.text} for c in prep.clauses]

        return status, preview, prep.language, dropdown_update, first_clause_text, clause_map, clauses_list

    except Exception as e:
        return f"❌ Error: {e}", "", "", gr.update(choices=[], value=None), "", {}, []


def show_selected_clause(selected_label, clause_map):
    if not selected_label or not clause_map:
        return ""
    return clause_map.get(selected_label, "")


def analyze_selected_clause(selected_label, clause_map):
    """
    Runs LLM analysis on the selected clause and returns fields for the UI.
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
    Runs clause analysis over a subset of clauses (speed guard) and aggregates into contract-level score.
    Also returns rule-based red flags.

    Returns:
      overall_risk, avg_score, counts_line, high_risk_text, red_flags_text
    """
    if not clauses_list:
        return (
            "Unclear",
            "0.0",
            "High: 0 | Medium: 0 | Low: 0 | Unclear: 0",
            "No clauses found.",
            "[]",
        )

    # Speed guard for hackathon; increase later if needed
    MAX_CLAUSES = 12
    subset = clauses_list[:MAX_CLAUSES]

    clause_results = []
    for c in subset:
        llm_raw = analyze_clause_with_llm(c["text"])
        result = normalize_risk(llm_raw)

        clause_results.append(
            ClauseAnalysis(
                clause_id=c["clause_id"],
                clause_text=c["text"],
                clause_type=result["clause_type"],
                risk_level=result["risk_level"],
                risk_reason=result["risk_reason"],
            )
        )

    summary = aggregate_contract(clause_results)

    append_audit_event(
        {
            "event": "llm_contract_analysis",
            "clauses_analyzed": len(subset),
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

    return summary["overall_risk"], str(summary["avg_score"]), counts_line, high_risk_text, red_flags_text


with gr.Blocks(title="Contract Risk Bot — Phase 3") as demo:
    gr.Markdown("# Contract Risk Bot — Phase 3 (Clause + Contract Risk Assessment)")
    gr.Markdown(
        "1) Upload a contract (PDF text-based / DOCX / TXT) and click **Process**.\n"
        "2) Select a clause and click **Analyze Selected Clause**.\n"
        "3) Click **Analyze Full Contract (Sample-based)** to compute an overall risk score + red flags "
        "(analyzes a subset for speed)."
    )

    # States
    clause_map_state = gr.State({})
    clauses_state = gr.State([])  # Phase 3: list[{"clause_id":..., "text":...}]

    with gr.Row():
        file_in = gr.File(label="Upload Contract", file_types=[".pdf", ".docx", ".txt"])
        process_btn = gr.Button("Process")

    status = gr.Textbox(label="Status", interactive=False)
    lang = gr.Textbox(label="Detected Language", interactive=False)

    preview = gr.Textbox(label="Extracted Text Preview (first 8000 chars)", lines=14)

    clause_dropdown = gr.Dropdown(label="Clauses", choices=[], value=None)
    clause_text = gr.Textbox(label="Selected Clause Text", lines=10)

    # Phase 2 UI
    analyze_btn = gr.Button("Analyze Selected Clause")
    clause_type = gr.Textbox(label="Clause Type", interactive=False)
    explanation = gr.Textbox(label="Plain-English Explanation", lines=5)
    risk = gr.Textbox(label="Risk Assessment", interactive=False)
    mitigation = gr.Textbox(label="Suggested Mitigation", lines=4)

    # Phase 3 UI
    full_analyze_btn = gr.Button("Analyze Full Contract (Sample-based)")

    overall_risk = gr.Textbox(label="Overall Contract Risk", interactive=False)
    avg_score = gr.Textbox(label="Average Risk Score", interactive=False)
    risk_counts = gr.Textbox(label="Clause Risk Distribution", interactive=False)

    top_high_risk = gr.Textbox(label="Top High-Risk Clauses (subset)", lines=10)
    red_flags = gr.Textbox(label="Detected Red Flags (rule-based)", lines=10)

    # --- Event wiring ---
    process_btn.click(
        process_upload,
        inputs=[file_in],
        outputs=[status, preview, lang, clause_dropdown, clause_text, clause_map_state, clauses_state],
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
        outputs=[overall_risk, avg_score, risk_counts, top_high_risk, red_flags],
    )

demo.launch(server_name="127.0.0.1", server_port=7860)
