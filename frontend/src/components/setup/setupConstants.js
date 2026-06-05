export const JSON_UPLOAD_SCHEMA_EXAMPLE = `{
  "source_id": "pilot-json-001",
  "source_type": "uploaded_dataset",
  "deployment_id": "pilot-deployment-001",
  "segment_id": "segment-1",
  "scenario": "relationship_shift",
  "tick": 10,
  "timestamp": "2026-05-01T08:00:00Z",
  "readings": [
    {
      "timestamp": "2026-05-01T08:00:00Z",
      "sensor_id": "metric-001",
      "sensor_name": "variable_a",
      "value": 75.2,
      "unit": "arb",
      "quality": "good"
    }
  ]
}`;

export const TAG_MAP_ROWS = [
  ["control_runtime", "Control Runtime", "Segment Group A", "Controller 1", "minutes", "1 min", "Good"],
  ["variable_a", "Variable A", "Segment Group A", "Sensor A", "arb", "1 min", "Good"],
  ["variable_b", "Variable B", "Segment Group A", "Sensor B", "arb", "1 min", "Good"],
  ["response_metric", "Response Metric", "Segment Group A", "Sensor C", "arb", "1 min", "Good"],
];
