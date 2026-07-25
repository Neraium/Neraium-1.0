from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

from app.core.config import Settings

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover - optional in isolated test environments
    boto3 = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationResult:
    adapter: str
    delivered: bool
    detail: str


class NotificationAdapter(Protocol):
    name: str

    def send(self, event: dict[str, Any], message: str) -> NotificationResult: ...


class ConsoleNotificationAdapter:
    name = "console"

    def send(self, event: dict[str, Any], message: str) -> NotificationResult:
        level = logging.CRITICAL if event.get("category") == "Infrastructure Critical" else logging.WARNING
        if event.get("event_type") == "recovery":
            level = logging.INFO
        logger.log(
            level,
            "infrastructure_notification",
            extra={
                "event": "infrastructure_notification",
                "incident_id": event.get("incident_id"),
                "notification_category": event.get("category"),
                "subsystem": event.get("subsystem"),
                "notification_event_type": event.get("event_type"),
                "notification_message": message,
            },
        )
        return NotificationResult(self.name, True, "logged")


class SnsNotificationAdapter:
    name = "sns"

    def __init__(self, topic_arn: str, client: Any | None = None):
        self.topic_arn = topic_arn
        self.client = client

    def send(self, event: dict[str, Any], message: str) -> NotificationResult:
        if self.client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required for SNS infrastructure notifications.")
            self.client = boto3.client("sns", region_name=os.getenv("AWS_REGION") or None)
        subject = str(event.get("category") or "Neraium infrastructure alert")[:100]
        self.client.publish(TopicArn=self.topic_arn, Subject=subject, Message=message)
        return NotificationResult(self.name, True, "published")


class JsonWebhookNotificationAdapter:
    def __init__(self, name: str, url: str, payload_kind: str = "webhook"):
        self.name = name
        self.url = url
        self.payload_kind = payload_kind

    def _payload(self, event: dict[str, Any], message: str) -> dict[str, Any]:
        if self.payload_kind == "slack":
            return {"text": message}
        if self.payload_kind == "teams":
            return {
                "type": "message",
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [{"type": "TextBlock", "wrap": True, "text": message}],
                    },
                }],
            }
        return {"source": "neraium-production-monitor", "event": event, "text": message}

    def send(self, event: dict[str, Any], message: str) -> NotificationResult:
        body = json.dumps(self._payload(event, message), separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Neraium-Infrastructure-Monitor/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            status = int(getattr(response, "status", 200))
        if status < 200 or status >= 300:
            raise RuntimeError(f"Webhook returned HTTP {status}.")
        return NotificationResult(self.name, True, f"http_{status}")


class EmailNotificationAdapter:
    name = "email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, event: dict[str, Any], message: str) -> NotificationResult:
        email = EmailMessage()
        email["Subject"] = str(event.get("category") or "Neraium infrastructure alert")
        email["From"] = self.settings.smtp_sender
        email["To"] = ", ".join(self.settings.notification_email_recipients)
        email.set_content(message)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(email)
        return NotificationResult(self.name, True, "sent")


def format_infrastructure_notification(event: dict[str, Any]) -> str:
    evidence = [str(item) for item in event.get("evidence") or [] if str(item).strip()]
    evidence_text = "\n".join(f"- {item}" for item in evidence) or "- No additional evidence recorded."
    changed = event.get("what_changed") or "Production infrastructure health changed."
    return (
        f"{event.get('category', 'Production infrastructure update')}\n\n"
        f"What changed: {changed}\n"
        f"When it started: {event.get('started_at') or 'unknown'}\n"
        f"Subsystem: {event.get('subsystem') or 'platform'}\n"
        f"Current impact: {event.get('impact') or 'Operator review is recommended.'}\n\n"
        f"Evidence:\n{evidence_text}\n\n"
        f"Recommended first check: {event.get('recommended_first_check') or 'Review the production health dashboard and recent service logs.'}\n"
        f"Incident: {event.get('incident_id') or 'unknown'}"
    )


class InfrastructureNotificationEngine:
    """Fan out one state-transition notification to every configured adapter."""

    def __init__(self, adapters: list[NotificationAdapter]):
        self.adapters = adapters
        self.last_results: list[dict[str, Any]] = []

    @classmethod
    def from_settings(cls, settings: Settings) -> "InfrastructureNotificationEngine":
        adapters: list[NotificationAdapter] = [ConsoleNotificationAdapter()]
        topic_arn = os.getenv("NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN", "").strip()
        if topic_arn:
            adapters.append(SnsNotificationAdapter(topic_arn))
        slack_url = os.getenv("NERAIUM_INFRA_ALERT_SLACK_WEBHOOK_URL", "").strip()
        if slack_url:
            adapters.append(JsonWebhookNotificationAdapter("slack", slack_url, "slack"))
        teams_url = os.getenv("NERAIUM_INFRA_ALERT_TEAMS_WEBHOOK_URL", "").strip()
        if teams_url:
            adapters.append(JsonWebhookNotificationAdapter("teams", teams_url, "teams"))
        webhook_url = os.getenv("NERAIUM_INFRA_ALERT_WEBHOOK_URL", "").strip()
        if webhook_url:
            adapters.append(JsonWebhookNotificationAdapter("webhook", webhook_url))
        if settings.smtp_host and settings.notification_email_recipients and settings.smtp_sender:
            adapters.append(EmailNotificationAdapter(settings))
        return cls(adapters)

    def dispatch(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        message = format_infrastructure_notification(event)
        results: list[dict[str, Any]] = []
        for adapter in self.adapters:
            try:
                result = adapter.send(event, message)
                results.append({"adapter": result.adapter, "delivered": result.delivered, "detail": result.detail})
            except Exception as error:
                logger.exception(
                    "infrastructure_notification_delivery_failed",
                    extra={
                        "event": "infrastructure_notification_delivery_failed",
                        "adapter": getattr(adapter, "name", type(adapter).__name__),
                        "incident_id": event.get("incident_id"),
                    },
                )
                results.append({
                    "adapter": getattr(adapter, "name", type(adapter).__name__),
                    "delivered": False,
                    "detail": type(error).__name__,
                })
        self.last_results = results
        return results

    def status(self) -> dict[str, Any]:
        return {
            "configured_adapters": [getattr(adapter, "name", type(adapter).__name__) for adapter in self.adapters],
            "last_delivery_results": list(self.last_results),
        }
