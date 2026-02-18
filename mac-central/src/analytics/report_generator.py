"""Auto event report generator.

Generates structured security reports from detection events,
optionally using VLM for narrative summaries.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReportSection:
    """A section within a generated report."""
    title: str
    content: str
    event_count: int = 0
    severity: str = "info"


@dataclass
class EventReport:
    """A generated event report."""
    report_id: str
    device_id: str
    time_range_hours: float
    generated_at: float = field(default_factory=time.time)
    sections: list[ReportSection] = field(default_factory=list)
    total_events: int = 0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "device_id": self.device_id,
            "time_range_hours": self.time_range_hours,
            "generated_at": self.generated_at,
            "total_events": self.total_events,
            "summary": self.summary,
            "sections": [
                {"title": s.title, "content": s.content,
                 "event_count": s.event_count, "severity": s.severity}
                for s in self.sections
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class ReportGenerator:
    """Generates structured event reports from detection history."""

    def __init__(self, detection_store=None, cloud_storage=None) -> None:
        self._store = detection_store
        self._cloud = cloud_storage

    def generate(
        self,
        device_id: str = "",
        time_range_hours: float = 24.0,
        include_vlm: bool = True,
    ) -> EventReport:
        """Generate a report for a device over a time range.

        Args:
            device_id: Filter by device (empty = all devices).
            time_range_hours: How far back to look.
            include_vlm: Include VLM analysis results in report.

        Returns:
            EventReport with sections for each event category.
        """
        report_id = f"rpt-{device_id or 'all'}-{int(time.time())}"
        report = EventReport(
            report_id=report_id,
            device_id=device_id,
            time_range_hours=time_range_hours,
        )

        if not self._store:
            report.summary = "No detection store available."
            return report

        since = time.time() - time_range_hours * 3600
        events = self._store.query(since=since, limit=1000, device_id=device_id)
        report.total_events = len(events)

        if not events:
            report.summary = f"No events in the last {time_range_hours:.0f}h."
            return report

        # Categorize events
        detections = [e for e in events if e.get("event_type") == "detection"]
        vlm_analyses = [e for e in events if e.get("event_type") == "vlm_analysis"]
        behavior_alerts = [e for e in events if e.get("event_type") == "behavior_alert"]
        anomalies = [e for e in events if e.get("event_type") == "anomaly_alert"]

        # Detection summary section
        if detections:
            class_counts: dict[str, int] = {}
            for evt in detections:
                for d in evt.get("detections", []):
                    cn = d.get("class_name", "unknown")
                    class_counts[cn] = class_counts.get(cn, 0) + 1
            top_classes = sorted(class_counts.items(), key=lambda x: -x[1])[:10]
            content = "Detection class distribution:\n"
            for cn, count in top_classes:
                content += f"  {cn}: {count}\n"
            report.sections.append(ReportSection(
                title="Detection Summary",
                content=content,
                event_count=len(detections),
            ))

        # VLM analysis section
        if include_vlm and vlm_analyses:
            vlm_lines = []
            for evt in vlm_analyses[:20]:
                vlm_result = evt.get("vlm_result", "")
                rule = evt.get("rule_matched", "")
                vlm_lines.append(f"  [{rule}] {vlm_result[:120]}")
            report.sections.append(ReportSection(
                title="VLM Analysis Highlights",
                content="\n".join(vlm_lines),
                event_count=len(vlm_analyses),
            ))

        # Behavior alerts section
        if behavior_alerts:
            report.sections.append(ReportSection(
                title="Behavior Alerts",
                content=f"{len(behavior_alerts)} behavior alerts detected.",
                event_count=len(behavior_alerts),
                severity="warning",
            ))

        # Anomaly section
        if anomalies:
            report.sections.append(ReportSection(
                title="Anomalies",
                content=f"{len(anomalies)} anomalous events detected.",
                event_count=len(anomalies),
                severity="critical",
            ))

        report.summary = (
            f"Report for {device_id or 'all devices'}: "
            f"{len(detections)} detections, {len(vlm_analyses)} VLM analyses, "
            f"{len(behavior_alerts)} behavior alerts, {len(anomalies)} anomalies "
            f"over {time_range_hours:.0f}h."
        )

        return report

    async def generate_and_upload(
        self,
        device_id: str = "",
        time_range_hours: float = 24.0,
    ) -> Optional[str]:
        """Generate report and upload to cloud storage. Returns upload key."""
        report = self.generate(device_id, time_range_hours)
        if self._cloud and hasattr(self._cloud, "upload_report"):
            try:
                key = await self._cloud.upload_report(
                    report_id=report.report_id,
                    content=report.to_json(),
                )
                logger.info(f"Report uploaded: {key}")
                return key
            except Exception as e:
                logger.warning(f"Report upload failed: {e}")
        return None
