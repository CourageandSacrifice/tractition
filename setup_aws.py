import boto3
import json
import os
import zipfile

print("Script started")

ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"

def get_client(service):
    return boto3.client(service, endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id="test", aws_secret_access_key="test")

def zip_lambda(filename):
    zip_path = f"lambdas_frontend/lambdas/{filename.replace('.py', '.zip')}"
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.write(f"lambdas_frontend/lambdas/{filename}", filename)
    with open(zip_path, 'rb') as f:
        return f.read()

print("Creating DynamoDB table...")
dynamo = get_client('dynamodb')
try:
    dynamo.create_table(
        TableName='lap_times',
        AttributeDefinitions=[
            {'AttributeName': 'lap_id', 'AttributeType': 'S'},
            {'AttributeName': 'track_id', 'AttributeType': 'S'},
            {'AttributeName': 'driver_id', 'AttributeType': 'S'},
            {'AttributeName': 'lap_time_ms', 'AttributeType': 'N'},
        ],
        KeySchema=[{'AttributeName': 'lap_id', 'KeyType': 'HASH'}],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'TrackTimeIndex',
                'KeySchema': [
                    {'AttributeName': 'track_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'lap_time_ms', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'},
                'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            },
            {
                'IndexName': 'DriverTrackIndex',
                'KeySchema': [
                    {'AttributeName': 'driver_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'track_id', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'},
                'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            }
        ],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )
    print("  DynamoDB table created")
except dynamo.exceptions.ResourceInUseException:
    print("  Table already exists, skipping")

print("Creating SNS topic...")
sns = get_client('sns')
topic = sns.create_topic(Name='lap-records')
topic_arn = topic['TopicArn']
sns.subscribe(TopicArn=topic_arn, Protocol='email', Endpoint='your@email.com')
print(f"  SNS topic created: {topic_arn}")

print("Creating Lambda functions...")
lam = get_client('lambda')
env_vars = {
    'Variables': {
        'DYNAMODB_ENDPOINT': ENDPOINT,
        'SNS_ENDPOINT': ENDPOINT,
        'SNS_TOPIC_ARN': topic_arn,
        'REDIS_HOST': 'localhost'
    }
}

for fn_file, fn_name in [
    ('submit_lap.py', 'submit-lap'),
    ('get_leaderboard.py', 'get-leaderboard'),
    ('get_personal_best.py', 'get-personal-best')
]:
    try:
        lam.create_function(
            FunctionName=fn_name,
            Runtime='python3.13',
            Role='arn:aws:iam::000000000000:role/lambda-role',
            Handler=fn_file.replace('.py', '.lambda_handler'),
            Code={'ZipFile': zip_lambda(fn_file)},
            Environment=env_vars
        )
        print(f"  Created {fn_name}")
    except lam.exceptions.ResourceConflictException:
        print(f"  {fn_name} already exists, skipping")

print("Creating API Gateway...")
apigw = get_client('apigateway')
api = apigw.create_rest_api(name='lap-tracker-api')
api_id = api['id']

root = apigw.get_resources(restApiId=api_id)['items'][0]['id']

def add_endpoint(path, method, function_name, parent_id=None):
    resource = apigw.create_resource(
        restApiId=api_id,
        parentId=parent_id or root,
        pathPart=path
    )
    resource_id = resource['id']
    apigw.put_method(
        restApiId=api_id, resourceId=resource_id,
        httpMethod=method, authorizationType='NONE'
    )
    apigw.put_integration(
        restApiId=api_id, resourceId=resource_id,
        httpMethod=method, type='AWS_PROXY',
        integrationHttpMethod='POST',
        uri=f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/arn:aws:lambda:{REGION}:000000000000:function:{function_name}/invocations"
    )
    return resource_id

laps_id = add_endpoint('laps', 'POST', 'submit-lap')
leaderboard_id = add_endpoint('leaderboard', 'GET', 'get-leaderboard')
track_resource_id = add_endpoint('{track_id}', 'GET', 'get-leaderboard', leaderboard_id)
pb_id = add_endpoint('personal-best', 'GET', 'get-personal-best')

apigw.create_deployment(restApiId=api_id, stageName='dev')

api_url = f"{ENDPOINT}/restapis/{api_id}/dev/_user_request_"
print(f"  API Gateway URL: {api_url}")

print("\n✅ All done! Save this URL for your frontend:")
print(f"   {api_url}")

with open('api_url.txt', 'w') as f:
    f.write(api_url)