from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import get_settings


logger = logging.getLogger(__name__)


def dispatch_observation_notification(record: dict[str, Any]) -> None:
    if not should_notify(record):
        return
    settings = get_settings()
    if settings.notification_webhook_url:
        try:
            send_webhook_notification(settings.notification_webhook_url, record)
        except Exception:
            logger.exception("observation_webhook_notification_failed run_id=%s", record.get("run_id"))
    if settings.smtp_host and settings.notification_email_recipients and settings.smtp_sender:
        try:
            send_email_notification(record)
        except Exception:
            logger.exception("observation_email_notification_failed run_id=%s", record.get("run_id"))


def should_notify(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    if str(record.get("status") or "").lower() != "completed":
        return False
    if str(record.get("observation_status") or "open").lower() != "open":
        return False
    return True


def send_webhook_notification(url: str, record: dict[str, Any]) -> None:
    payload = {
        "event": "observation.generated",
        "run_id": record.get("run_id"),
        "source_name": record.get("source_name"),
        "observation_type": record.get("observation_type"),
        "structural_state": record.get("structural_state"),
        "regime_label": record.get("regime_label"),
        "variables": record.get("variables") or [],
        "drift_metrics": record.get("drift_metrics") or {},
        "deformation_started_at": record.get("deformation_started_at"),
        "evidence_summary": record.get("evidence_summary") or [],
        "data_conditions": record.get("data_conditions") or [],
        "created_at": record.get("created_at"),
        "completed_at": record.get("completed_at"),
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()


def send_email_notification(record: dict[str, Any]) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = build_subject(record)
    message["From"] = settings.smtp_sender
    message["To"] = ", ".join(settings.notification_email_recipients)
    message.set_content(build_email_body(record))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def build_subject(record: dict[str, Any]) -> str:
    source = str(record.get("source_name") or record.get("source_type") or "telemetry")
    observation_type = str(record.get("observation_type") or "observation").replace("_", " ")
    return f"Neraium observation: {observation_type} on {source}"


def build_email_body(record: dict[str, Any]) -> str:
    evidence = "\n".join(f"- {item}" for item in (record.get("evidence_summary") or [])[:5]) or "- None recorded"
    variables = ", ".join(str(item) for item in (record.get("variables") or [])[:8]) or "None recorded"
    drift_metrics = record.get("drift_metrics") or {}
    metric_lines = "\n".join(f"- {key}: {value}" for key, value in drift_metrics.items() if value not in {None, ""}) or "- None recorded"
    return (
        "A new structural observation was generated.\n\n"
        f"Run ID: {record.get('run_id')}\n"
        f"Source: {record.get('source_name') or record.get('source_type')}\n"
        f"Observation Type: {record.get('observation_type')}\n"
        f"Structural State: {record.get('structural_state')}\n"
        f"Regime: {record.get('regime_label')}\n"
        f"Variables: {variables}\n"
        f"Deformation Started At: {record.get('deformation_started_at')}\n\n"
        "Evidence Summary:\n"
        f"{evidence}\n\n"
        "Drift Metrics:\n"
        f"{metric_lines}\n"
    )
