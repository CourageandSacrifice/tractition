import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

LAPS_TABLE = 'lap_times'
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

def lambda_handler(event, context):
    body = json.loads(event.get('body', '{}'))
    driver_id = body.get('driver_id')
    driver_name = body.get('driver_name')
    car_name = body.get('car_name', '')
    track_id = body.get('track_id')
    track_name = body.get('track_name')
    lap_time_ms = int(body.get('lap_time_ms'))

    if not all([driver_id, track_id, lap_time_ms]):
        return response(400, {'error': 'Missing required fields'})

    table = dynamodb.Table(LAPS_TABLE)

    result = table.query(
        IndexName='TrackTimeIndex',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('track_id').eq(track_id),
        ScanIndexForward=True,
        Limit=1
    )

    is_record = False
    if not result['Items'] or lap_time_ms < int(result['Items'][0]['lap_time_ms']):
        is_record = True

    timestamp = datetime.utcnow().isoformat()
    table.put_item(Item={
        'lap_id': f"{driver_id}#{timestamp}",
        'driver_id': driver_id,
        'driver_name': driver_name,
        'car_name': car_name,
        'track_id': track_id,
        'track_name': track_name,
        'lap_time_ms': lap_time_ms,
        'timestamp': timestamp
    })

    if is_record and SNS_TOPIC_ARN:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=f"New track record on {track_name}! {driver_name} set a time of {lap_time_ms}ms",
            Subject=f"New Record on {track_name}!"
        )

    return response(200, {'message': 'Lap submitted', 'is_record': is_record})

def response(status, body):
    return {
        'statusCode': status,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body)
    }