import json
import math
from datetime import datetime, timedelta, timezone

def handler(event, context):
    if event.get('requestContext', {}).get('http', {}).get('method') != 'GET' or event.get('rawPath') != '/telemetry':
        return {'statusCode': 404, 'body': 'not found'}
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1)
    records = []
    for i in range(40):
        at = (end - timedelta(minutes=39-i)).isoformat().replace('+00:00', 'Z')
        flow = 42.0 + 7.0 * math.sin(i / 6.0) + 0.04 * i
        for tag, value in (('synthetic_flow_a', flow), ('synthetic_flow_b', 0.83 * flow + 2.0 + 0.3 * math.cos(i / 9.0))):
            records.append({'event_id': f'v2-closeout-{tag}-{i:03d}-{end:%Y%m%d%H%M}', 'observed_at': at, 'signal': tag, 'value': round(value, 5), 'unit': 'L/s'})
    return {'statusCode': 200, 'headers': {'content-type': 'application/json', 'cache-control': 'no-store'}, 'body': json.dumps({'source': 'neraium-controlled-synthetic-v2', 'records': records})}
