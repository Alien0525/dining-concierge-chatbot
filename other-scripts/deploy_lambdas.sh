#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "Error: .env file not found"
    exit 1
fi

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Role ARNs
LF0_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/LF0-ExecutionRole"
LF1_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/LF1-ExecutionRole"
LF2_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/LF2-ExecutionRole"

echo "Deploying Lambda functions..."

# Deploy LF0
echo "Deploying LF0..."
cd lambda_functions/LF0
zip -r lf0.zip lambda_function.py
aws lambda create-function \
  --function-name LF0 \
  --runtime python3.11 \
  --role $LF0_ROLE \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lf0.zip \
  --timeout 30 \
  --region $REGION \
  2>/dev/null || aws lambda update-function-code \
  --function-name LF0 \
  --zip-file fileb://lf0.zip \
  --region $REGION

# Deploy LF1
echo "Deploying LF1..."
cd ../LF1
zip -r lf1.zip lambda_function.py
aws lambda create-function \
  --function-name LF1 \
  --runtime python3.11 \
  --role $LF1_ROLE \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lf1.zip \
  --timeout 30 \
  --region $REGION \
  2>/dev/null || aws lambda update-function-code \
  --function-name LF1 \
  --zip-file fileb://lf1.zip \
  --region $REGION

# Deploy LF2 with environment variables from .env
echo "Deploying LF2..."
cd ../LF2
zip -r lf2.zip lambda_function.py
aws lambda create-function \
  --function-name LF2 \
  --runtime python3.11 \
  --role $LF2_ROLE \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lf2.zip \
  --timeout 60 \
  --environment "Variables={SQS_QUEUE_URL=${SQS_QUEUE_URL},FROM_EMAIL=${FROM_EMAIL},DYNAMODB_TABLE=${DYNAMODB_TABLE_NAME}}" \
  --region $REGION \
  2>/dev/null || aws lambda update-function-code \
  --function-name LF2 \
  --zip-file fileb://lf2.zip \
  --region $REGION

echo "All Lambda functions deployed!"
cd ../..