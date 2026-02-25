import boto3

ses = boto3.client('ses', region_name='us-east-1')

response = ses.send_email(
    Source='aas10498@nyu.edu',
    Destination={'ToAddresses': ['aas10498@nyu.edu']},
    Message={
        'Subject': {'Data': 'SES Working'},
        'Body': {
            'Text': {'Data': 'If you got this, SES works.'}
        }
    }
)

print("Sent:", response['MessageId'])
