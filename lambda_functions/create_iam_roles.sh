#!/bin/bash

REGION="us-east-1"

# Trust policy (same for all - allows Lambda to assume the role)
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# LF0 Policy
cat > lf0-policy.json << EOF
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
        "lex:PostText",
        "lex:PostContent",
        "lex:RecognizeText"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# LF1 Policy - Updated with DynamoDB permissions
cat > lf1-policy.json << EOF
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
      "Resource": "arn:aws:sqs:${REGION}:*:restaurant-requests"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:${REGION}:*:table/user-preferences"
    }
  ]
}
EOF

# LF2 Policy
cat > lf2-policy.json << EOF
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
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:${REGION}:*:restaurant-requests"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:Scan",
        "dynamodb:Query",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:${REGION}:*:table/yelp-restaurants"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# LF3 Policy - For preference recall
cat > lf3-policy.json << EOF
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
      "Resource": "arn:aws:dynamodb:${REGION}:*:table/user-preferences"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:${REGION}:*:restaurant-requests"
    }
  ]
}
EOF

echo "Creating/updating IAM roles..."

# Create or update LF0
echo "LF0 role..."
aws iam create-role --role-name LF0-ExecutionRole --assume-role-policy-document file://trust-policy.json 2>/dev/null || echo "LF0 role already exists"
aws iam put-role-policy --role-name LF0-ExecutionRole --policy-name LF0-Policy --policy-document file://lf0-policy.json

# Create or update LF1
echo "LF1 role..."
aws iam create-role --role-name LF1-ExecutionRole --assume-role-policy-document file://trust-policy.json 2>/dev/null || echo "LF1 role already exists"
aws iam put-role-policy --role-name LF1-ExecutionRole --policy-name LF1-Policy --policy-document file://lf1-policy.json

# Create or update LF2
echo "LF2 role..."
aws iam create-role --role-name LF2-ExecutionRole --assume-role-policy-document file://trust-policy.json 2>/dev/null || echo "LF2 role already exists"
aws iam put-role-policy --role-name LF2-ExecutionRole --policy-name LF2-Policy --policy-document file://lf2-policy.json

# Create or update LF3
echo "LF3 role..."
aws iam create-role --role-name LF3-ExecutionRole --assume-role-policy-document file://trust-policy.json 2>/dev/null || echo "LF3 role already exists"
aws iam put-role-policy --role-name LF3-ExecutionRole --policy-name LF3-Policy --policy-document file://lf3-policy.json

echo ""
echo "Done! Role ARNs:"
aws iam get-role --role-name LF0-ExecutionRole --query 'Role.Arn' --output text
aws iam get-role --role-name LF1-ExecutionRole --query 'Role.Arn' --output text
aws iam get-role --role-name LF2-ExecutionRole --query 'Role.Arn' --output text
aws iam get-role --role-name LF3-ExecutionRole --query 'Role.Arn' --output text

# Cleanup
rm trust-policy.json lf0-policy.json lf1-policy.json lf2-policy.json lf3-policy.json