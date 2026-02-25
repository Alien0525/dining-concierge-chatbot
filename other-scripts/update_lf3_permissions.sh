#!/bin/bash

REGION="us-east-1"

echo "Creating LF3 IAM policy..."

# Create the policy
cat > lf3-policy-updated.json << POLICY
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
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/user-preferences"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:us-east-1:*:restaurant-requests"
    }
  ]
}
POLICY

# Apply the policy
aws iam put-role-policy \
  --role-name LF3-ExecutionRole \
  --policy-name LF3-Policy \
  --policy-document file://lf3-policy-updated.json \
  --region $REGION

echo "✅ LF3 permissions created!"
echo "Waiting 10 seconds for IAM changes to propagate..."
sleep 10
echo "✅ Ready!"

# Cleanup
rm lf3-policy-updated.json
