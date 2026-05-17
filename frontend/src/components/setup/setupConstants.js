export const JSON_UPLOAD_SCHEMA_EXAMPLE = `{
  "source_id": "pilot-json-001",
  "source_type": "uploaded_dataset",
  "facility_id": "pilot-facility-001",
  "room_id": "room-1",
  "scenario": "airflow_drift",
  "tick": 10,
  "timestamp": "2026-05-01T08:00:00Z",
  "readings": [
    {
      "timestamp": "2026-05-01T08:00:00Z",
      "sensor_id": "temp-001",
      "sensor_name": "temperature",
      "value": 75.2,
      "unit": "F",
      "quality": "good"
    }
  ]
}`;

export const TAG_MAP_ROWS = [
  ["hvac_runtime", "HVAC Runtime", "Cultivation Rooms", "HVAC Unit 1", "minutes", "1 min", "Good"],
  ["temp_air", "Air Temperature", "Cultivation Rooms", "Room Sensor", "Â°F", "1 min", "Good"],
  ["rh_percent", "Relative Humidity", "Cultivation Rooms", "Room Sensor", "%RH", "1 min", "Good"],
  ["dehu_runtime", "Dehumidifier Runtime", "Cultivation Rooms", "Dehu Unit 1", "minutes", "1 min", "Good"],
];
