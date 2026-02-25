#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "Sending test message to SQS..."

aws sqs send-message \
  --queue-url ${SQS_QUEUE_URL} \
  --message-body '{"cuisine":"Indian","num_people":"2","dining_time":"tonight at 7pm","email":"'"${FROM_EMAIL}"'","location":"Manhattan"}' \
  --region us-east-1

echo "Test message sent! Check your email in 1-2 minutes."
echo "Or invoke LF2 manually:"
echo "aws lambda invoke --function-name LF2 --region us-east-1 response.json"