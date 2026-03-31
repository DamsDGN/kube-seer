import json
import re
from typing import Any, Dict

import structlog

from src.models import AnalysisResult, LLMInsight, Severity

logger = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are an expert SRE assistant analysing a Kubernetes cluster. "
    "You receive a structured snapshot of detected anomalies, correlated incidents, "
    "and resource saturation predictions. "
    "Respond ONLY with a valid JSON object matching the required schema. "
    "Do not add any explanation outside the JSON. "
    "For severity_assessment, choose exactly ONE value from: ok, warning, critical. "
    "Never combine values with | or /."
)

_SEVERITY_NAMES = {
    Severity.INFO: "INFO",
    Severity.WARNING: "WARNING",
    Severity.CRITICAL: "CRITICAL",
}
_SEVERITY_EMOJIS = {
    "critical": ":red_circle:",
    "warning": ":warning:",
    "ok": ":white_check_mark:",
}


def build_prompt(result: AnalysisResult) -> str:
    lines = [f"Cluster analysis — {result.analysis_timestamp.isoformat()}"]

    all_anomalies = sorted(result.anomalies, key=lambda a: -int(a.severity))
    shown = all_anomalies[:10]
    total = len(all_anomalies)
    lines.append(f"\nAnomalies ({total} total, showing {len(shown)}):")
    for a in shown:
        sev = _SEVERITY_NAMES.get(a.severity, str(a.severity))
        ns = f" ({a.namespace})" if a.namespace else ""
        lines.append(
            f"  [{sev}] {a.source}/{a.resource_type} {a.resource_name}{ns}: {a.description}"
        )

    if result.incidents:
        lines.append(f"\nIncidents ({len(result.incidents)}):")
        for inc in result.incidents:
            sev = _SEVERITY_NAMES.get(inc.severity, str(inc.severity))
            resources = ", ".join(inc.resources[:3])
            lines.append(
                f"  {inc.incident_id} [{sev}]: {resources} — {inc.description}"
            )

    if result.predictions:
        lines.append(f"\nPredictions ({len(result.predictions)}):")
        for p in result.predictions[:5]:
            ns = f"{p.namespace}/" if p.namespace else ""
            lines.append(
                f"  {ns}{p.resource_name} {p.metric_name} → {p.threshold}% "
                f"in {p.hours_to_threshold}h "
                f"(current: {p.current_value:.1f}%, trend: +{p.trend_per_hour:.2f}%/h)"
            )

    schema = (
        '{"summary":"one sentence summary","root_causes":["…"],'
        '"recommendations":[{"priority":1,"action":"…","resource":"…"}],'
        '"severity_assessment":"critical","affected_namespaces":["…"]}'
        "\n"
        "severity_assessment must be exactly one of: ok, warning, critical"
    )
    lines.append(
        f"\nRespond with this JSON structure (example values shown):\n{schema}"
    )
    return "\n".join(lines)


def parse_llm_response(raw: str) -> Dict[str, Any]:
    """Extract and parse JSON from LLM response. Returns empty dict on failure."""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def format_slack_message(insight: LLMInsight) -> str:
    """Format a LLMInsight as a Slack message string."""
    ts = insight.cycle_timestamp.strftime("%H:%M UTC")

    if not insight.summary:
        return (
            f"🤖 *kube-seer AI Analysis — {ts}*\n"
            f"⚠️ Could not parse structured response. Raw output:\n"
            f"{insight.raw_response[:500]}"
        )

    emoji = _SEVERITY_EMOJIS.get(insight.severity_assessment, ":white_check_mark:")
    lines = [
        f"🤖 *kube-seer AI Analysis — {ts}*",
        f"*Overall severity:* {emoji} {insight.severity_assessment}",
        f"\n*Summary:* {insight.summary}",
    ]

    if insight.root_causes:
        lines.append("\n*Probable root causes:*")
        for cause in insight.root_causes:
            lines.append(f"• {cause}")

    if insight.recommendations:
        lines.append("\n*Recommended actions:*")
        for i, rec in enumerate(insight.recommendations[:5], 1):
            action = rec.get("action", "")
            resource = rec.get("resource", "")
            lines.append(f"{i}. {action}" + (f" — `{resource}`" if resource else ""))

    return "\n".join(lines)
