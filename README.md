# avry-blog

Blog CMS microservice for the Aivory platform — articles, reactions, comments, and WebSocket real-time updates.

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- PostgreSQL
- WebSocket (real-time updates)
- Docker

## Directory Structure

```
avry-blog/
├── app/            # Application source code
├── migrations/     # Database migrations
├── tests/          # Test suite
├── main.py         # Entry point
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env

# Start the server (port 8088)
uvicorn main:app --host 0.0.0.0 --port 8088 --reload
```

## Docker

```bash
docker compose up --build
```

## VPS Deployment

```bash
docker compose -f docker-compose.yml up -d --build
```

Ensure `.env` is configured on the server with production credentials.

## Part of Aivory

This service is part of the [Aivory platform](https://github.com/ClementHansel/aivory).
