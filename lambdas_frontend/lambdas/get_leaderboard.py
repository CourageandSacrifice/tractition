import json
import boto3

dynamodb = boto3.resource('dynamodb')
LAPS_TABLE = 'lap_times'

def lambda_handler(event, context):
    track_id = event.get('pathParameters', {}).get('track_id')
    if not track_id:
        return response(400, {'error': 'Missing track_id'})

    table = dynamodb.Table(LAPS_TABLE)
    result = table.query(
        IndexName='TrackTimeIndex',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('track_id').eq(track_id),
        ScanIndexForward=True,
        Limit=10
    )

    leaderboard = []
    seen_drivers = set()
    for item in result['Items']:
        if item['driver_id'] not in seen_drivers:
            seen_drivers.add(item['driver_id'])
            leaderboard.append({
                'driver_name': item['driver_name'],
                'lap_time_ms': int(item['lap_time_ms']),
                'timestamp': item['timestamp']
            })

    return response(200, {'leaderboard': leaderboard, 'cached': False})

def response(status, body):
    return {
        'statusCode': status,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body)
    }
