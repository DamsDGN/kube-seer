from datetime import datetime, timezone
from src.models import Anomaly, AnalysisResult, Severity


def _make_result(anomalies=None, incidents=None, predictions=None):
    return AnalysisResult(
        anomalies=anomalies or [],
        incidents=incidents or [],
        predictions=predictions or [],
        analysis_timestamp=datetime(2026, 3, 31, 14, 32, tzinfo=timezone.utc),
        metrics_analyzed=10,
        events_analyzed=5,
    )


def _make_anomaly(
    aid,
    source="events",
    sev=Severity.WARNING,
    rtype="pod",
    rname="my-pod",
    ns="default",
    desc="something bad",
):
    return Anomaly(
        anomaly_id=aid,
        source=source,
        severity=sev,
        resource_type=rtype,
        resource_name=rname,
        namespace=ns,
        description=desc,
        score=0.8,
        details={},
        timestamp=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )


class TestBuildPrompt:
    def test_contains_timestamp(self):
        from src.intelligence.prompt import build_prompt

        result = _make_result(anomalies=[_make_anomaly("a1")])
        prompt = build_prompt(result)
        assert "2026-03-31" in prompt

    def test_contains_anomaly_description(self):
        from src.intelligence.prompt import build_prompt

        result = _make_result(
            anomalies=[_make_anomaly("a1", desc="CrashLoop detected")]
        )
        prompt = build_prompt(result)
        assert "CrashLoop detected" in prompt

    def test_truncates_to_10_anomalies(self):
        from src.intelligence.prompt import build_prompt

        anomalies = [_make_anomaly(f"a{i}", desc=f"error-{i}") for i in range(15)]
        result = _make_result(anomalies=anomalies)
        prompt = build_prompt(result)
        assert "15 total" in prompt
        assert "error-14" not in prompt

    def test_contains_json_schema_hint(self):
        from src.intelligence.prompt import build_prompt

        result = _make_result(anomalies=[_make_anomaly("a1")])
        prompt = build_prompt(result)
        assert "severity_assessment" in prompt
        assert "recommendations" in prompt

    def test_empty_incidents_not_shown(self):
        from src.intelligence.prompt import build_prompt

        result = _make_result(anomalies=[_make_anomaly("a1")])
        prompt = build_prompt(result)
        assert "Incidents" not in prompt


class TestParseLLMResponse:
    def test_valid_json(self):
        from src.intelligence.prompt import parse_llm_response

        raw = (
            '{"summary": "ok", "root_causes": [], "recommendations": [], '
            '"severity_assessment": "ok", "affected_namespaces": []}'
        )
        result = parse_llm_response(raw)
        assert result["summary"] == "ok"

    def test_json_embedded_in_text(self):
        from src.intelligence.prompt import parse_llm_response

        raw = (
            "Here is my analysis:\n"
            '{"summary": "critical", "root_causes": ["oom"], "recommendations": [], '
            '"severity_assessment": "critical", "affected_namespaces": ["prod"]}\nEnd.'
        )
        result = parse_llm_response(raw)
        assert result["summary"] == "critical"

    def test_invalid_json_returns_empty(self):
        from src.intelligence.prompt import parse_llm_response

        result = parse_llm_response("not json at all")
        assert result == {}

    def test_empty_string_returns_empty(self):
        from src.intelligence.prompt import parse_llm_response

        assert parse_llm_response("") == {}


class TestFormatSlackMessage:
    def _make_insight(self, **kwargs):
        from src.models import LLMInsight

        defaults = dict(
            insight_id="ins-1",
            cycle_timestamp=datetime(2026, 3, 31, 14, 32, tzinfo=timezone.utc),
            anomaly_count=2,
            summary="2 anomalies detected",
            root_causes=["OOM on payment-api"],
            recommendations=[
                {
                    "priority": 1,
                    "action": "Increase limit",
                    "resource": "deployment/payment-api",
                }
            ],
            severity_assessment="critical",
            affected_namespaces=["production"],
            raw_response="{}",
            provider="ollama/llama3.2",
        )
        defaults.update(kwargs)
        return LLMInsight(**defaults)

    def test_contains_summary(self):
        from src.intelligence.prompt import format_slack_message

        msg = format_slack_message(self._make_insight())
        assert "2 anomalies detected" in msg

    def test_contains_root_cause(self):
        from src.intelligence.prompt import format_slack_message

        msg = format_slack_message(self._make_insight())
        assert "OOM on payment-api" in msg

    def test_contains_recommendation(self):
        from src.intelligence.prompt import format_slack_message

        msg = format_slack_message(self._make_insight())
        assert "Increase limit" in msg

    def test_fallback_when_no_summary(self):
        from src.intelligence.prompt import format_slack_message

        insight = self._make_insight(summary="", raw_response="raw text from llm")
        msg = format_slack_message(insight)
        assert "raw text from llm" in msg

    def test_critical_severity_emoji(self):
        from src.intelligence.prompt import format_slack_message

        msg = format_slack_message(self._make_insight(severity_assessment="critical"))
        assert ":red_circle:" in msg

    def test_ok_severity_emoji(self):
        from src.intelligence.prompt import format_slack_message

        msg = format_slack_message(
            self._make_insight(severity_assessment="ok", summary="all good")
        )
        assert ":white_check_mark:" in msg
