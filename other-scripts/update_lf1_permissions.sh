#!/bin/bash

REGION="us-east-1"

echo "Updating LF1 IAM permissions to include DynamoDB access..."

# Create the updated policy
cat > lf1-policy-updated.json << POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:GetQueueUrl"
      ],
      "Resource": "arn:aws:sqs:us-east-1:*:restaurant-requests"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/user-preferences"
    }
  ]
}
POLICY

# Apply the updated policy
aws iam put-role-policy \
  --role-name LF1-ExecutionRole \
  --policy-name LF1-Policy \
  --policy-document file://lf1-policy-updated.json \
  --region $REGION

echo "✅ LF1 permissions updated!"
echo "Waiting 10 seconds for IAM changes to propagate..."
sleep 10
echo "✅ Ready to test!"

# Cleanup
rm lf1-policy-updated.json
