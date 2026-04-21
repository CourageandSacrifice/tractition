import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
LAPS_TABLE = 'lap_times'

def lambda_handler(event, context):
    params = event.get('pathParameters', {})
    driver_id = params.get('driver_id')
    track_id = params.get('track_id')

    if not driver_id or not track_id:
        return response(400, {'error': 'Missing driver_id or track_id'})

    table = dynamodb.Table(LAPS_TABLE)
    result = table.query(
        IndexName='DriverTrackIndex',
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key('driver_id').eq(driver_id) &
            boto3.dynamodb.conditions.Key('track_id').eq(track_id)
        ),
        ScanIndexForward=True,
        Limit=1
    )

    if not result['Items']:
        return response(404, {'error': 'No laps found'})

    best = result['Items'][0]
    return response(200, {
        'driver_name': best['driver_name'],
        'track_id': track_id,
        'best_lap_ms': int(best['lap_time_ms']),
        'timestamp': best['timestamp']
    })

def response(status, body):
    return {
        'statusCode': status,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body)
    }