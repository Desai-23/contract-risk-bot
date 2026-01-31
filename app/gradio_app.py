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

from src.nlp.ambiguity import format_ambiguity_as_text

from src.llm.ollama_client import analyze_clause_with_llm
from src.risk.scoring import normalize_risk
from src.risk.aggregator import ClauseAnalysis, aggregate_contract
from src.risk.selector import smart_select_clauses

from src.compliance.checks import run_compliance_checks, format_compliance_flags
from src.negotiation.rewrite import rewrite_clause
from src.export.pdf_report import generate_pdf_report

# ✅ IMPORTANT: matcher & generator are in data/
from data.templates.matcher import match_clause_to_templates
from data.templates.generator import generate_contract


def process_upload(file_path):
    """
    Returns:
      status,
      contract_type_line,
      entities_dict,
      ambiguity_text,
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
            {},
            "",
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

        contract_type_line = (
            f"{prep.contract_type} | conf={prep.contract_type_confidence} | method={prep.contract_type_method} "
            f"| evidence={', '.join(prep.contract_type_evidence) if prep.contract_type_evidence else '[]'}"
        )

        ambiguity_text = format_ambiguity_as_text(getattr(prep, "ambiguity", {}))

        original_preview = loaded.text[:8000]
        normalized_preview = prep.normalized_text[:8000]

        dropdown_update = gr.update(
            choices=clause_labels,
            value=clause_labels[0] if clause_labels else None,
        )

        first_clause_text = clause_map[clause_labels[0]] if clause_labels else ""
        clauses_list = [{"clause_id": c.clause_id, "text": c.text} for c in prep.clauses]

        ent_counts = {
            "organizations": len(prep.entities.get("organizations", [])),
            "persons": len(prep.entities.get("persons", [])),
            "locations": len(prep.entities.get("locations", [])),
            "dates": len(prep.entities.get("dates", [])),
            "money_amounts": len(prep.entities.get("money_amounts", [])),
            "jurisdiction_mentions": len(prep.entities.get("jurisdiction_mentions", [])),
            "party_mentions": len(prep.entities.get("parties", {}).get("party_mentions", [])),
            "party_roles": len(prep.entities.get("parties", {}).get("roles", {})),
        }

        amb = getattr(prep, "ambiguity", {}) or {}
        amb_metrics = {
            "level": amb.get("level", "None"),
            "score": amb.get("score", 0),
            "hits": len(amb.get("hits", []) or []),
        }

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
                "contract_type": prep.contract_type,
                "contract_type_confidence": prep.contract_type_confidence,
                "contract_type_method": prep.contract_type_method,
                "contract_type_evidence": prep.contract_type_evidence,
                "entity_counts": ent_counts,
                "ambiguity": amb_metrics,
            }
        )

        return (
            status,
            contract_type_line,
            prep.entities,
            ambiguity_text,
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
            {},
            "",
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
    if not clauses_list:
        return (
            "Unclear",
            "0.0",
            "High: 0 | Medium: 0 | Low: 0 | Unclear: 0",
            "No clauses found.",
            "[]",
            "No compliance-related heuristic flags detected.",
            {},
        )

    full_text = "\n".join([c.get("text", "") for c in clauses_list])
    compliance_flags = run_compliance_checks(full_text)
    compliance_text = format_compliance_flags(compliance_flags)

    selected, sel_stats = smart_select_clauses(
        clauses_list,
        max_llm_clauses=12,
        ensure_baseline=2,
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
            {"clause_id": c.clause_id, "selection_score": c.score, "selection_reasons": c.reasons}
        )

    summary = aggregate_contract(clause_results)

    append_audit_event(
        {
            "event": "llm_contract_analysis_smart_select",
            "selection_stats": sel_stats,
            "selected_clause_debug": selection_debug[:20],
            "overall_risk": summary["overall_risk"],
            "avg_score": summary["avg_score"],
            "counts": summary["counts"],
            "red_flags_count": len(summary["red_flags"]),
            "compliance_flags_count": len(compliance_flags),
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
        [f"- {x['clause_id']} ({x['clause_type']}): {x['risk_reason']}\n  {x['text_preview']}"
         for x in summary["top_high_risk"]]
    ) or "No High-risk clauses detected in analyzed subset."

    red_flags_text = "\n".join(
        [f"- [{x['severity']}] {x['flag_type']}: {x['reason']}" for x in summary["red_flags"]]
    ) or "No rule-based red flags detected."

    return (
        summary["overall_risk"],
        str(summary["avg_score"]),
        counts_line,
        high_risk_text,
        red_flags_text,
        compliance_text,
        summary,
    )


def export_pdf(contract_summary, high_risk_text, red_flags_text, compliance_text):
    if not contract_summary:
        return None

    disclaimer = (
        "This report is generated automatically for informational purposes only and does not constitute legal advice. "
        "For decisions that may have legal or financial impact, consult a qualified legal professional."
    )

    combined_redflags = red_flags_text + "\n\nCompliance Heuristic Flags:\n" + (compliance_text or "")

    out_path = generate_pdf_report(
        filename_base="contract",
        contract_summary=contract_summary,
        high_risk_text=high_risk_text,
        red_flags_text=combined_redflags,
        disclaimer=disclaimer,
    )

    append_audit_event(
        {"event": "export_pdf_report", "output_path": out_path, "overall_risk": contract_summary.get("overall_risk", "Unclear")}
    )
    return out_path


def suggest_rewrite(selected_label, clause_map):
    if not selected_label or not clause_map:
        return "", "", ""

    clause_text = clause_map[selected_label]
    out = rewrite_clause(clause_text, party_perspective="SME")

    append_audit_event(
        {"event": "rewrite_suggestion", "is_unfavorable": out.get("is_unfavorable", False), "chars_clause": len(clause_text)}
    )

    points = "\n".join([f"- {p}" for p in out.get("negotiation_points", [])]) or ""
    combined = out.get("suggested_rewrite", "")
    if points:
        combined = combined + "\n\nNegotiation Points:\n" + points

    return str(out.get("is_unfavorable", False)), out.get("why_unfavorable", ""), combined


def match_selected_clause_to_templates(selected_label, clause_map, contract_type_line):
    if not selected_label or not clause_map:
        return []

    clause_text = clause_map.get(selected_label, "")
    contract_type = (contract_type_line.split("|")[0].strip() if contract_type_line else "unknown")

    matches = match_clause_to_templates(clause_text, contract_type=contract_type, top_k=3)

    append_audit_event(
        {"event": "template_similarity_match", "contract_type": contract_type, "matches_returned": len(matches)}
    )
    return matches


def generate_sme_contract(contract_type):
    if not contract_type:
        return "Please select a contract type."

    try:
        out = generate_contract(contract_type)

        append_audit_event(
            {"event": "generate_sme_contract", "contract_type": contract_type, "template_name": out.get("name")}
        )

        header = f"{out.get('name','SME Contract Template')}\n\n{out.get('description','')}\n\n"
        return header + out.get("text", "")

    except Exception as e:
        return f"❌ Error: {e}"


with gr.Blocks(title="Contract Risk Bot — Phase 14") as demo:
    gr.Markdown("# Contract Risk Bot — Phase 14 (SME-Friendly Standard Templates + Full Stack)")

    clause_map_state = gr.State({})
    clauses_state = gr.State([])
    contract_summary_state = gr.State({})

    with gr.Row():
        file_in = gr.File(label="Upload Contract", file_types=[".pdf", ".docx", ".txt"])
        process_btn = gr.Button("Process")

    status = gr.Textbox(label="Status", interactive=False)
    contract_type_box = gr.Textbox(label="Contract Type (predicted)", interactive=False)
    lang = gr.Textbox(label="Detected Language (Original)", interactive=False)

    entities_view = gr.JSON(label="Extracted Entities (NER + Regex)")
    ambiguity_view = gr.Textbox(label="Ambiguity Detection (rule-based)", lines=10)

    original_preview = gr.Textbox(label="Original Text Preview (first 8000 chars)", lines=4)
    normalized_preview = gr.Textbox(label="Normalized English Text Preview (first 8000 chars)", lines=4)

    clause_dropdown = gr.Dropdown(label="Clauses (normalized)", choices=[], value=None)
    clause_text = gr.Textbox(label="Selected Clause Text (normalized)", lines=6)

    with gr.Row():
        analyze_btn = gr.Button("Analyze Selected Clause")
        rewrite_btn = gr.Button("Suggest SME-Friendly Rewrite")
        template_btn = gr.Button("Match Clause to Standard Templates")

    clause_type = gr.Textbox(label="Clause Type", interactive=False)
    explanation = gr.Textbox(label="Plain-English Explanation", lines=4)
    risk = gr.Textbox(label="Risk Assessment", interactive=False)
    mitigation = gr.Textbox(label="Suggested Mitigation", lines=3)

    is_unfavorable = gr.Textbox(label="Is Unfavorable?", interactive=False)
    why_unfavorable = gr.Textbox(label="Why Unfavorable", lines=3)
    rewrite_text = gr.Textbox(label="Suggested Rewrite + Negotiation Points", lines=8)

    template_matches = gr.JSON(label="Top Template Matches")

    full_analyze_btn = gr.Button("Analyze Full Contract (Smart Selection)")
    overall_risk = gr.Textbox(label="Overall Contract Risk", interactive=False)
    avg_score = gr.Textbox(label="Average Risk Score", interactive=False)
    risk_counts = gr.Textbox(label="Clause Risk Distribution (LLM subset)", interactive=False)







    top_high_risk = gr.Textbox(label="Top High-Risk Clauses (subset)", lines=7)
    red_flags = gr.Textbox(label="Detected Red Flags (rule-based)", lines=7)
    compliance_box = gr.Textbox(label="Compliance Heuristic Flags (India-focused)", lines=10)

    export_btn = gr.Button("Export PDF Report")
    pdf_file = gr.File(label="Download Report (PDF)", interactive=False)

    gr.Markdown("## Generate SME-Friendly Standard Contract Template")

    template_contract_type = gr.Dropdown(
        label="Select Contract Type",
        choices=["service_contract", "vendor_contract", "employment_agreement", "lease_agreement", "partnership_deed"],
        value="service_contract",
    )
    generate_template_btn = gr.Button("Generate SME-Friendly Contract")
    generated_contract = gr.Textbox(label="Generated SME Contract (Editable)", lines=18)

    # --- Wiring ---
    process_btn.click(
        process_upload,
        inputs=[file_in],
        outputs=[
            status,
            contract_type_box,
            entities_view,
            ambiguity_view,
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

    rewrite_btn.click(
        suggest_rewrite,
        inputs=[clause_dropdown, clause_map_state],
        outputs=[is_unfavorable, why_unfavorable, rewrite_text],
    )

    template_btn.click(
        match_selected_clause_to_templates,
        inputs=[clause_dropdown, clause_map_state, contract_type_box],
        outputs=[template_matches],
    )

    full_analyze_btn.click(
        analyze_full_contract,
        inputs=[clauses_state],
        outputs=[overall_risk, avg_score, risk_counts, top_high_risk, red_flags, compliance_box, contract_summary_state],
    )

    export_btn.click(
        export_pdf,
        inputs=[contract_summary_state, top_high_risk, red_flags, compliance_box],
        outputs=[pdf_file],
    )

    generate_template_btn.click(
        generate_sme_contract,
        inputs=[template_contract_type],
        outputs=[generated_contract],
    )

demo.launch(server_name="127.0.0.1", server_port=7860)

