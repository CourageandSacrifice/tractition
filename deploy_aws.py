import boto3
import json
import os
import zipfile
import time

print("Starting deployment to real AWS...")

REGION = "us-east-1"
ACCOUNT_ID = "214277677017"

def get_client(service):
    return boto3.client(service, region_name=REGION)

def zip_lambda(filename):
    zip_path = f"lambdas_frontend/lambdas/{filename.replace('.py', '.zip')}"
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.write(f"lambdas_frontend/lambdas/{filename}", filename)
    with open(zip_path, 'rb') as f:
        return f.read()

# ── IAM ROLE ──
print("\n1. Creating IAM role for Lambda...")
iam = get_client('iam')
trust_policy = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})
try:
    role = iam.create_role(
        RoleName='lap-tracker-lambda-role',
        AssumeRolePolicyDocument=trust_policy
    )
    role_arn = role['Role']['Arn']
    iam.attach_role_policy(
        RoleName='lap-tracker-lambda-role',
        PolicyArn='arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess'
    )
    iam.attach_role_policy(
        RoleName='lap-tracker-lambda-role',
        PolicyArn='arn:aws:iam::aws:policy/AmazonSNSFullAccess'
    )
    iam.attach_role_policy(
        RoleName='lap-tracker-lambda-role',
        PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
    )
    print(f"   Role created: {role_arn}")
    print("   Waiting 10 seconds for role to propagate...")
    time.sleep(10)
except iam.exceptions.EntityAlreadyExistsException:
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/lap-tracker-lambda-role"
    print(f"   Role already exists, using: {role_arn}")

# ── DYNAMODB ──
print("\n2. Creating DynamoDB table...")
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
            },
            {
                'IndexName': 'DriverTrackIndex',
                'KeySchema': [
                    {'AttributeName': 'driver_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'track_id', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'},
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    print("   DynamoDB table created")
except dynamo.exceptions.ResourceInUseException:
    print("   Table already exists, skipping")

# ── SNS ──
print("\n3. Creating SNS topic...")
sns = get_client('sns')
topic = sns.create_topic(Name='lap-records')
topic_arn = topic['TopicArn']
print(f"   SNS topic: {topic_arn}")

# ── LAMBDA ──
print("\n4. Deploying Lambda functions...")
lam = get_client('lambda')
env_vars = {
    'Variables': {
        'SNS_TOPIC_ARN': topic_arn,
    }
}

function_arns = {}
for fn_file, fn_name in [
    ('submit_lap.py', 'submit-lap'),
    ('get_leaderboard.py', 'get-leaderboard'),
    ('get_personal_best.py', 'get-personal-best')
]:
    try:
        resp = lam.create_function(
            FunctionName=fn_name,
            Runtime='python3.13',
            Role=role_arn,
            Handler=fn_file.replace('.py', '.lambda_handler'),
            Code={'ZipFile': zip_lambda(fn_file)},
            Environment=env_vars,
            Timeout=30
        )
        function_arns[fn_name] = resp['FunctionArn']
        print(f"   Created {fn_name}")
    except lam.exceptions.ResourceConflictException:
        resp = lam.get_function(FunctionName=fn_name)
        function_arns[fn_name] = resp['Configuration']['FunctionArn']
        print(f"   {fn_name} already exists, skipping")

# ── COGNITO ──
print("\n5. Creating Cognito User Pool...")
cognito = get_client('cognito-idp')
try:
    pool = cognito.create_user_pool(
        PoolName='lap-tracker-users',
        Policies={
            'PasswordPolicy': {
                'MinimumLength': 8,
                'RequireUppercase': False,
                'RequireLowercase': False,
                'RequireNumbers': False,
                'RequireSymbols': False
            }
        },
        AutoVerifiedAttributes=['email'],
        UsernameAttributes=['email']
    )
    pool_id = pool['UserPool']['Id']
    client = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName='lap-tracker-client',
        ExplicitAuthFlows=['ALLOW_USER_PASSWORD_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH'],
        GenerateSecret=False
    )
    client_id = client['UserPoolClient']['ClientId']
    print(f"   User Pool ID: {pool_id}")
    print(f"   Client ID: {client_id}")
except Exception as e:
    print(f"   Cognito error: {e}")
    pool_id = ""
    client_id = ""

# ── API GATEWAY ──
print("\n6. Creating API Gateway...")
apigw = get_client('apigateway')
api = apigw.create_rest_api(
    name='lap-tracker-api',
    description='Race Lap Tracker API'
)
api_id = api['id']
root_id = apigw.get_resources(restApiId=api_id)['items'][0]['id']

def add_endpoint(path, method, fn_name, parent_id=None):
    resource = apigw.create_resource(
        restApiId=api_id,
        parentId=parent_id or root_id,
        pathPart=path
    )
    rid = resource['id']
    apigw.put_method(
        restApiId=api_id, resourceId=rid,
        httpMethod=method, authorizationType='NONE'
    )
    fn_arn = function_arns[fn_name]
    apigw.put_integration(
        restApiId=api_id, resourceId=rid,
        httpMethod=method, type='AWS_PROXY',
        integrationHttpMethod='POST',
        uri=f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/{fn_arn}/invocations"
    )
    apigw.put_method(
        restApiId=api_id, resourceId=rid,
        httpMethod='OPTIONS', authorizationType='NONE'
    )
    apigw.put_integration(
        restApiId=api_id, resourceId=rid,
        httpMethod='OPTIONS', type='MOCK',
        requestTemplates={'application/json': '{"statusCode": 200}'}
    )
    apigw.put_method_response(
        restApiId=api_id, resourceId=rid,
        httpMethod='OPTIONS', statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': False,
            'method.response.header.Access-Control-Allow-Methods': False,
            'method.response.header.Access-Control-Allow-Origin': False
        }
    )
    apigw.put_integration_response(
        restApiId=api_id, resourceId=rid,
        httpMethod='OPTIONS', statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': "'Content-Type,Authorization'",
            'method.response.header.Access-Control-Allow-Methods': "'GET,POST,OPTIONS'",
            'method.response.header.Access-Control-Allow-Origin': "'*'"
        }
    )
    lam.add_permission(
        FunctionName=fn_name,
        StatementId=f"apigw-{rid}",
        Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com',
        SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*"
    )
    return rid

laps_id = add_endpoint('laps', 'POST', 'submit-lap')
lb_id = add_endpoint('leaderboard', 'GET', 'get-leaderboard')
track_id = add_endpoint('{track_id}', 'GET', 'get-leaderboard', lb_id)
pb_id = add_endpoint('personal-best', 'GET', 'get-personal-best')

apigw.create_deployment(restApiId=api_id, stageName='prod')

api_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/prod"
print(f"   API URL: {api_url}")

# ── SAVE CONFIG ──
config = {
    'api_url': api_url,
    'cognito_pool_id': pool_id,
    'cognito_client_id': client_id,
    'sns_topic_arn': topic_arn,
    'region': REGION
}
with open('aws_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("\n✅ Deployment complete!")
print(f"   API URL: {api_url}")
print(f"   Config saved to aws_config.json")
print(f"\n   Update app.js with this API URL:")
print(f"   const API = \"{api_url}\";")