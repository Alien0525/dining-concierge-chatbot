# Dining Concierge Chatbot

A serverless, microservice-driven dining recommendation system built on AWS. The application conducts a natural language conversation with the user to collect dining preferences, then asynchronously delivers personalized restaurant suggestions via email.

Live demo: https://amanns-dining-concierge-nyc.s3.us-east-1.amazonaws.com/index.html

---

## Architecture

```
User (Browser)
    │
    ▼
S3 Static Frontend
    │  API call
    ▼
API Gateway  ──►  Lambda LF0  ──►  Amazon Lex V2
                                        │
                                    Lambda LF1 (Code Hook)
                                        │  on fulfillment
                                        ▼
                               SQS Queue (Q1)        DynamoDB
                                        │             user-preferences
                             CloudWatch (1 min)
                                        │
                                    Lambda LF2
                                   ╱           ╲
                            OpenSearch        DynamoDB
                          (restaurant IDs)  (full details)
                                   ╲           ╱
                                    SES Email
```

The frontend sends messages to API Gateway, which invokes **LF0** to relay them to **Amazon Lex**. Lex routes the conversation through **LF1**, a code hook that validates slot values and saves user preferences. On fulfillment, LF1 pushes a structured request to an **SQS queue**. A **CloudWatch** rule triggers **LF2** every minute — it polls the queue, queries **OpenSearch** for random matching restaurant IDs, fetches full details from **DynamoDB**, and delivers a formatted HTML email via **SES**.

---

## Services Used

| Service | Role |
|---|---|
| S3 | Static frontend hosting |
| API Gateway | REST API, Swagger-defined |
| Lambda (LF0) | API handler, Lex proxy |
| Amazon Lex V2 | NLU, intent routing, slot collection |
| Lambda (LF1) | Lex code hook, slot validation, SQS dispatch |
| SQS | Decoupled request queue |
| Lambda (LF2) | Queue worker, recommendation engine |
| OpenSearch | Fast cuisine + area search |
| DynamoDB | Restaurant data store, user preference store |
| SES | HTML email delivery |
| CloudWatch Events | 1-minute LF2 trigger |

---

## Features

**Core chatbot flow**
- Collects location, cuisine, dining date, time, number of people, and email through guided conversation
- Validates all slot values (supported locations, cuisines, party size range, dates, times) before fulfillment
- Pushes validated preferences to SQS and confirms receipt to the user

**Intents implemented**
- `GreetingIntent` — welcomes the user; surfaces prior search history if available
- `ThankYouIntent` — closes the conversation gracefully
- `DiningSuggestionsIntent` — full slot-collection and fulfillment flow
- `RepeatLastSearchIntent` — re-sends recommendations from the user's last session

**Recommendation engine (LF2)**
- Queries OpenSearch with `function_score` + `random_score` for varied suggestions on each request
- Falls back to a DynamoDB scan filtered by cuisine and area if OpenSearch is unavailable
- Fetches full restaurant details via DynamoDB `batch_get_item`
- Sends a styled HTML email with name, star rating, review count, address (Google Maps linked), and phone number

**Additional feature: Conversation memory**
- Stores each user's last search (location, cuisine, email, party size) in a `user-preferences` DynamoDB table, keyed by a hashed session ID
- On return visits, `GreetingIntent` detects the prior search and offers to repeat it or start fresh
- `LF3` handles automatic re-dispatch: on greeting, it pushes the last preferences directly to SQS without requiring the user to re-enter anything

---

## Screenshots

### Frontend — Normal Flow

**Landing page**
![Landing page](screenshots/frontend/normal-flow/landing-page.png)

**Location selection**
![Location selection](screenshots/frontend/normal-flow/area.png)

**Cuisine selection**
![Cuisine selection](screenshots/frontend/normal-flow/cuisine.png)

**Date selection**
![Date selection](screenshots/frontend/normal-flow/date.png)

**Time selection**
![Time selection](screenshots/frontend/normal-flow/time.png)

**Headcount**
![Headcount](screenshots/frontend/normal-flow/headcount.png)

**Email entry**
![Email entry](screenshots/frontend/normal-flow/email.png)

**Confirmation**
![Recommendations received 1](screenshots/frontend/normal-flow/recommendations-1.png)
![Recommendations received 2](screenshots/frontend/normal-flow/recommendations-2.png)

---

### Frontend — Invalid Input Handling

**Invalid area**
![Invalid area](screenshots/frontend/invalid-prompts/invalid-area.png)

**Invalid cuisine**
![Invalid cuisine](screenshots/frontend/invalid-prompts/invalid-cuisine.png)

**Invalid date**
![Invalid date 1](screenshots/frontend/invalid-prompts/invalid-date-1.png)
![Invalid date 2](screenshots/frontend/invalid-prompts/invalid-date-2.png)

**Invalid time**
![Invalid time](screenshots/frontend/invalid-prompts/invalid-time-1.png)

**Invalid party size**
![Invalid party size 1](screenshots/frontend/invalid-prompts/invalid-party-1.png)
![Invalid party size 2](screenshots/frontend/invalid-prompts/invalid-party-2.png)
![Invalid party size 3](screenshots/frontend/invalid-prompts/invalid-party-3.png)

**Invalid email**
![Invalid email](screenshots/frontend/invalid-prompts/invalid-email.png)

**Invalid preference on return visit**
![Invalid preference return user](screenshots/frontend/invalid-prompts/invalid-preference-return-user.png)

---

### Frontend — Conversation Memory (Extra Credit)

**Return user — greeting with last search recalled**
![Return user greeting](screenshots/frontend/conversation-memory/return-user.png)

**Choosing same as last time**
![Same preference](screenshots/frontend/conversation-memory/same-preference.png)

**Choosing something different**
![Different preference](screenshots/frontend/conversation-memory/different-preference.png)

---

### AWS — Lambda Functions

![Lambda functions](screenshots/lambda-functions/lambda-functions.png)

---

### AWS — Amazon Lex

**All intents**
![Lex intents](screenshots/lex-intents/lex-intents.png)

**DiningSuggestionsIntent — utterances**
![Dining suggestions utterances](screenshots/lex-intents/dining-suggestions-intent-utterances.png)

**DiningSuggestionsIntent — slots**
![Dining suggestions slots](screenshots/lex-intents/dining-suggestions-intent-slots.png)

---

### AWS — API Gateway

**Endpoints**
![API Gateway endpoints](screenshots/api-gateway/api-gateway-endpoints.png)

**POST /chatbot**
![Chatbot POST endpoint](screenshots/api-gateway/chatbot-POST-endpoint.png)

---

### AWS — Opensearch

**domain**
![Opensearch Domain](screenshots/openseach/opensearch-domain.png)

---

### AWS — DynamoDB

**Tables**
![DynamoDB tables](screenshots/dynamodb/dynamodb-tables.png)

**yelp-restaurants table**
![yelp-restaurants](screenshots/dynamodb/yelp-restaurants-table.png)

**user-preferences table**
![user-preferences](screenshots/dynamodb/user-preferences-table.png)

---

### AWS — SQS

**Queue**
![SQS queue](screenshots/sqs/sqs-restaurant-requests.png)

**Monitoring**
![SQS monitoring](screenshots/sqs/sqs-monitoring.png)

---

### AWS — SES

**Verified identity**
![SES verified identity](screenshots/ses/ses-verified-identity.png)

---

### AWS — S3

**Bucket**
![S3 bucket](screenshots/s3/s3-bucket.png)

**Bucket objects**
![S3 bucket objects](screenshots/s3/s3-bucket-objects.png)

**Assets folder**
![S3 bucket assets](screenshots/s3/s3-bucket-objects-assets.png)

---

### AWS — CloudWatch Logs

**Log management**
![CloudWatch log management](screenshots/cloudwatch/cloudwatch-log-management.png)

**LF0 logs**
![LF0 logs](screenshots/cloudwatch/logs-lf0.png)

**LF1 logs — flow 1**
![LF1 logs flow 1](screenshots/cloudwatch/logs-lf1-flow-1.png)

**LF1 logs — flow 2**
![LF1 logs flow 2](screenshots/cloudwatch/logs-lf1-flow-2.png)

**LF2 logs**
![LF1 logs flow](screenshots/cloudwatch/logs-lf2-flow.png)

---

## Data

Restaurants were scraped from the Yelp Fusion API across **8 NYC-area locations** and **12 cuisine types**, yielding approximately **4,500 unique restaurant records**.

Locations: Manhattan, Brooklyn, Queens, Bronx, Staten Island, Jersey City, Hoboken, Long Island City

Cuisines: Japanese, Italian, Chinese, Mexican, Indian, Thai, Korean, French, Mediterranean, American, Vietnamese, Spanish

Each DynamoDB record includes:

```
BusinessID, Name, Address, Latitude, Longitude, ReviewCount,
Rating, ZipCode, Cuisine, City, State, Area, Phone,
PriceRange, Categories, insertedAtTimestamp
```

OpenSearch stores only `RestaurantId`, `Cuisine`, and `Area` per document, keeping the index lightweight. Full details are always resolved through DynamoDB.

---

## Repository Structure

```
.
├── frontend/
│   ├── index.html               # Chat UI
│   ├── assets/
│   │   ├── css/app.css
│   │   └── js/
│   │       ├── chat.js          # Frontend logic
│   │       └── sdk/             # API Gateway generated SDK
│   └── swagger/swagger.yaml     # API specification
│
├── lambda_functions/
│   ├── LF0/lambda_function.py   # API Gateway handler → Lex
│   ├── LF1/lambda_function.py   # Lex code hook, SQS dispatch
│   ├── LF2/lambda_function.py   # Queue worker, email sender
│   └── LF3/lambda_function.py   # Preference recall on greeting
│
└── other-scripts/
    ├── config.py                # Shared configuration
    ├── scrape.py                # Basic Yelp scraper
    ├── scrape_expanded.py       # Multi-location scraper (4,500 restaurants)
    ├── load_dynamodb.py         # Bulk load restaurants into DynamoDB
    ├── load_opensearch.py       # Index restaurants into OpenSearch
    ├── verify_db.py             # Sanity-check DynamoDB contents
    ├── debug_opensearch.py      # OpenSearch query debugging
    ├── create_iam_roles.sh      # IAM role setup
    ├── deploy_lambdas.sh        # Lambda deployment script
    └── setup_cloudwatch_trigger.sh  # CloudWatch 1-minute rule
```

---

## Environment Variables

Each Lambda function reads its configuration from environment variables set in the Lambda console.

**LF0**

| Variable | Description |
|---|---|
| `LEX_BOT_ID` | Lex V2 bot ID |
| `LEX_BOT_ALIAS_ID` | Lex alias ID (use `TSTALIASID` for dev) |
| `LEX_LOCALE_ID` | Locale, e.g. `en_US` |
| `AWS_REGION_NAME` | e.g. `us-east-1` |

**LF1**

| Variable | Description |
|---|---|
| `SQS_QUEUE_URL` | URL of the SQS queue |

**LF2**

| Variable | Description |
|---|---|
| `DYNAMODB_TABLE` | `yelp-restaurants` |
| `SQS_QUEUE_URL` | URL of the SQS queue |
| `FROM_EMAIL` | SES-verified sender address |
| `OPENSEARCH_ENDPOINT` | OpenSearch domain endpoint |
| `OPENSEARCH_USER` | OpenSearch master username |
| `OPENSEARCH_PASS` | OpenSearch master password |

**LF3**

| Variable | Description |
|---|---|
| `SQS_QUEUE_URL` | URL of the SQS queue |

---

## Setup Overview

1. **Scrape data** — run `other-scripts/scrape_expanded.py` with a valid `YELP_API_KEY` in `.env`
2. **Load DynamoDB** — run `other-scripts/load_dynamodb.py`
3. **Create OpenSearch domain** — use Dev/Test environment, t3.small.search, 1 AZ, no standby; note the endpoint
4. **Load OpenSearch** — run `other-scripts/load_opensearch.py` (set `OPENSEARCH_ENDPOINT`, `MASTER_USER`, `MASTER_PASS` in `.env`)
5. **Deploy Lambdas** — run `other-scripts/deploy_lambdas.sh`, set all environment variables
6. **Configure Lex** — create the bot, intents, and slots; point the code hook to LF1
7. **Set up API Gateway** — import `swagger.yaml`, enable CORS, link to LF0, generate and download the JS SDK
8. **Deploy frontend** — replace the SDK in `frontend/assets/js/sdk/`, upload to S3, enable static website hosting
9. **Create CloudWatch rule** — run `other-scripts/setup_cloudwatch_trigger.sh` to trigger LF2 every minute
10. **Verify SES** — verify both the sender address and any recipient addresses in SES sandbox mode

> **Cost note:** OpenSearch is not serverless and will accrue charges while running. Tear down the domain when not actively using.

---

## Recreating OpenSearch After Teardown

If you have torn down the OpenSearch domain and need to recreate it:

**Step 1 — Create domain in AWS Console**

Go to OpenSearch Service → Create domain with these settings:

| Setting | Value |
|---|---|
| Creation method | Standard create |
| Templates | Dev/Test |
| Deployment option | Domain without standby |
| Availability zones | 1-AZ |
| Instance type | `t3.small.search` |
| Number of nodes | 1 |
| Fine-grained access control | Enabled — create a master user |
| Access policy | Only use fine-grained access control |

Wait 10–15 minutes for the domain to reach Active status.

**Step 2 — Update credentials**

Add to your `.env`:
```
OPENSEARCH_ENDPOINT=https://your-domain.us-east-1.es.amazonaws.com
MASTER_USER=your-master-username
MASTER_PASS=your-master-password
```

Update LF2's environment variables `OPENSEARCH_ENDPOINT`, `OPENSEARCH_USER`, `OPENSEARCH_PASS` in the Lambda console.

**Step 3 — Re-index**
```bash
python other-scripts/load_opensearch.py
```

The script bulk-loads all ~4,500 restaurants and prints a final count to confirm.

---

## Example Interaction

```
User:  Hello
Bot:   Welcome back! Last time you searched for Japanese food in Manhattan.
       Would you like the same, or something different today?

User:  Something different
Bot:   Sure! Which area would you like to dine in?

User:  Brooklyn
Bot:   What cuisine would you like to try?

User:  Italian
Bot:   How many people are in your party?

User:  4
Bot:   What date?

User:  Tomorrow
Bot:   What time?

User:  8pm
Bot:   Lastly, what is your email address?

User:  user@example.com
Bot:   You're all set. Expect my suggestions shortly! Have a good day.
```

The user receives an HTML email listing restaurant name, star rating, review count, address with a Google Maps link, and phone number for each recommendation.

---

## Course

Cloud Computing and Big Data — Spring 2026, NYU