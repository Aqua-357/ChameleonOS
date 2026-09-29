# ChameleonOS

> **DOGFOOD 2026 Submission**  
> A self-hostable hackathon submission and judging platform with an adaptive event theme system.

---

## Overview

ChameleonOS is an autonomous, self-hostable platform designed for organizing hackathons, handling team project submissions, executing multi-dimensional weighted judging, and adapting event themes dynamically.

### Key Tenets
- **100% Self-Contained:** No external API, no CDN, no hosted database, and zero cloud dependencies.
- **Local Persistence:** Powered by SQLite and SQLAlchemy.
- **Fast & Modern:** Built with FastAPI and server-rendered Jinja templates.
- **Containerized:** Instant deployment via Docker and Docker Compose.

---

## Repository Structure

```text
.
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE
├── README.md
├── data/                  # SQLite database persistence directory
└── src/
    ├── main.py            # Application entry point & health check
    ├── config.py          # Environment & application settings
    ├── database.py        # SQLAlchemy engine & session factory
    ├── static/            # Self-hosted static assets (CSS, JS, images)
    ├── templates/         # Jinja templates (self-contained, no external CDN)
    ├── auth/              # Authentication & authorization module
    ├── events/            # Hackathon event & theme management module
    ├── submissions/       # Project submissions module
    ├── judging/           # Rubric scorecard & evaluation module
    ├── normalization/     # Score normalization & ranking module
    └── audit/             # Tamper-evident audit trail & logging module
```

---

## Getting Started

### Using Docker Compose (Recommended)

Start the entire application with a single command:

```bash
docker compose up
```

The service will be accessible at:
- **Application:** [http://localhost:8000](http://localhost:8000)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Local Development

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the development server:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## License

This project is licensed under the [MIT License](LICENSE).
