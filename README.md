# Setup

1. Install dependencies:
```bash
pip3 install requests python-dotenv boto3
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Edit `.env` and add your Yelp API key

4. Run scraper:
```bash
python3 scrape.py
```