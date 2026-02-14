#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

echo "Setting up CloudWatch EventBridge trigger for LF2..."

# Create EventBridge rule
aws events put-rule \
  --name trigger-lf2-every-minute \
  --schedule-expression "rate(1 minute)" \
  --region $REGION

# Add Lambda permission
aws lambda add-permission \
  --function-name LF2 \
  --statement-id AllowEventBridge \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/trigger-lf2-every-minute \
  --region $REGION

# Connect rule to LF2
aws events put-targets \
  --rule trigger-lf2-every-minute \
  --targets "Id"="1","Arn"="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:LF2" \
  --region $REGION

echo "CloudWatch trigger set up successfully!"