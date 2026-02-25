# test_aws.py
import boto3

# Create DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Try to list tables
client = boto3.client('dynamodb', region_name='us-east-1')
tables = client.list_tables()

print("AWS Connection Successful!")
print(f"Existing DynamoDB tables: {tables['TableNames']}")