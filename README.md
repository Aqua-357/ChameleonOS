# ChameleonOS

> **DOGFOOD 2026 Submission**  
> Autonomous, self-hostable hackathon submission and judging platform with an adaptive event theme system.

---

## 🌟 Overview

ChameleonOS implements **T1 and T2, plus the Normalization Proof bonus and an adaptive visual/theming system.**

The platform is designed for zero-trust hackathon administration, team project submissions, secure multi-judge evaluations with deterministic score normalization, and dynamic styling powered by an offline token engine.

### Platform Capabilities & Claimed Tiers
- **Tier 1 (Core Platform):** Complete role-based authentication, configurable events, tracks, prizes, teams, invite tokens, project drafting, public gallery with unauthenticated search/filter, and strict deadline enforcement.
- **Tier 2 (Judging & Security):** Weighted rubrics, judge assignment queue, score submissions, strict judge isolation (no peer score leakage), organizer aggregate results, and RFC 4180 CSV export.
- **Tier 3 (Public / Community Voting):** *Not implemented / Not claimed.*
- **Tier 4 (Advanced Features):** *Not implemented / Not claimed.*
- **Normalization Proof (+5 Bonus):** Deterministic cross-judge Z-score normalization with benchmark rescaling, handling harsh/lenient graders, zero-variance evaluations, missing criteria, and unequal judge distributions (fully documented in [`JUDGING.md`](JUDGING.md)).
- **Product Innovation:** Adaptive Visual System featuring 6 design archetypes (`verdant`, `cosmos`, `arcade`, `monolith`, `bio`, `atelier`) and deterministic offline **Magic Morph**.

### Core Tenets
- **100% Offline & Zero-CDN:** Complete isolation from external networks. No external APIs, no external CDNs, no cloud telemetry, and zero third-party font/script downloads.
- **Local Persistence:** Powered by SQLite and SQLAlchemy with timezone-aware UTC timestamps stored in `./data/chameleon.db`.
- **Zero-Trust Security:** Strict backend-enforced authorization boundaries—judges cannot read peer scores, participants cannot access judging APIs, and submissions are strictly locked at deadlines.
- **Containerized:** Instant one-command startup via Docker Compose.

---

## 🚀 Quick Start (Clean Laptop / Offline Mode)

### Instant Startup via Docker Compose

```bash
docker compose up
```

Upon launching, ChameleonOS automatically executes:
1. Database schema initialization (`init_db`)
2. Idempotent user seeding (`organizer`, `judge_a`, `judge_b`, `participant`, `admin`)
3. Fixture data loading from `fixtures.json` (events, tracks, teams, projects, rubrics, assignments, scores)
4. Usable bearer authentication headers printed directly to the standard output console

### Access Endpoints
- **Web Application:** [http://localhost:8000](http://localhost:8000)
- **Public Project Gallery:** [http://localhost:8000/gallery](http://localhost:8000/gallery)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **Organizer Normalization Lab:** [http://localhost:8000/events/dogfood-2026/normalization-lab](http://localhost:8000/events/dogfood-2026/normalization-lab)

---

## 🔑 Seed User Credentials

The database is pre-seeded with authorized accounts for every platform role:

| Role | Username | Password | Email | Capabilities & Permissions |
| :--- | :--- | :--- | :--- | :--- |
| **Organizer** | `organizer` | `organizer_pass_2026` | `organizer@chameleon.local` | Event creation, rubric configuration, aggregate results, CSV export, Normalization Lab |
| **Judge A** | `judge_a` | `judge_a_pass_2026` | `judge_a@chameleon.local` | Assigned project scorecard evaluation, personal score viewing |
| **Judge B** | `judge_b` | `judge_b_pass_2026` | `judge_b@chameleon.local` | Peer judge; strictly isolated from Judge A's evaluations |
| **Participant** | `participant` | `participant_pass_2026` | `participant@chameleon.local` | Team formation, draft editing, project submission before deadline |
| **Admin** | `admin` | `admin_pass_2026` | `admin@chameleon.local` | Full administrative supervisor rights |

---

## 🛡️ DOGFOOD Compatibility Verification (`.dogfood.toml`)

ChameleonOS includes a local pre-flight compatibility harness configured through `.dogfood.toml` to verify adherence to the seven DOGFOOD behavioral targets.

> **Note on Verification:** `run.py` is a locally authored pre-flight test runner that validates compliance with the seven behavioral targets. Official acceptance certification remains subject to execution by the hackathon organizer's authoritative runner.

### Running the Local Compatibility Suite

Execute the local runner (zero external dependencies):
```bash
python3 run.py .dogfood.toml > acceptance-report.txt
```
*(On Windows systems where `python` is the executable, a local `python3.cmd` wrapper is provided).*

Or execute via pytest:
```bash
pytest -v tests/test_dogfood_acceptance.py
```

### The Seven Behavioral Compatibility Checks

| Check # | Name | Target Specification | Security & Operational Guarantee | Status |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **public gallery** | `GET /api/v1/projects` & `GET /gallery` | Public gallery is 100% accessible without authentication (HTTP 200). | Verified |
| **2** | **fixture visibility** | `GET /api/v1/projects` | Preloaded fixture projects (`fixtures.json`) are discoverable in public gallery. | Verified |
| **3** | **closed submission** | `POST /api/v1/projects/{id}/submit` | Submissions strictly rejected (HTTP 400) if event deadline has passed (`end_time < now`) or event phase is closed. | Verified |
| **4** | **judge own scores** | `GET /api/v1/judging/projects/{id}/scores` | Judge can retrieve and review their own submitted scores (HTTP 200). | Verified |
| **5** | **judge peer-score denial** | `GET /api/v1/judging/scores/{score_id}` | Judge is strictly forbidden (HTTP 403) from viewing peer scores, querying peer score IDs, or spoofing judge parameters. | Verified |
| **6** | **participant judge-score denial** | `GET /api/v1/judging/*` | Participant attempting to access judging endpoints or judge scores is denied (HTTP 403). | Verified |
| **7** | **organizer CSV export** | `GET /api/v1/judging/events/{id}/export.csv` | Organizers can download RFC 4180 compliant CSV scoring results; judges and participants are denied (HTTP 403). | Verified |

---

## 🧪 Comprehensive Test Suite

Run all unit, integration, visual token, and compatibility tests:

```bash
pytest -v
```

**Test Coverage Summary (49 Passed Tests):**
- `tests/test_database.py`: Table schema initialization, seed credential creation, and startup header printing.
- `tests/test_fixtures.py`: Idempotent fixture loading, ID preservation, ISO UTC timestamp normalization, tolerance of missing scores and duplicate submissions.
- `tests/test_t1.py`: Role-based permissions, event date configurations, teams and invites, draft editing, closed submission deadlines, unauthenticated gallery, search/filter.
- `tests/test_t2_judging.py`: Judge invitations, project queues, score submissions, weighted rubric calculations, CSV export, and hard authorization boundaries.
- `tests/test_normalization.py`: Zero-variance judge handling, harsh vs. lenient grader inversion, missing score proportional weighting, unequal judge counts, deterministic tie-breaking.
- `tests/test_visual_system.py`: 6 visual archetypes (`verdant`, `cosmos`, `arcade`, `monolith`, `bio`, `atelier`), 7 token dimensions, offline deterministic Magic Morph.
- `tests/test_dogfood_acceptance.py`: Acceptance harness validating all 7 behavioral criteria.

---

## 🎨 Product Innovation: Visual System & Magic Morph

ChameleonOS features a dynamic CSS token design system with 6 visual archetypes:
- **Verdant:** Ecological, deep forest emeralds, botanical rounded geometry.
- **Cosmos:** Deep celestial void, starlight accents, glassmorphic atmospheric cards.
- **Arcade:** High-contrast retro gaming neon, pixel-inspired geometric borders, energetic motion.
- **Monolith:** Brutalist architectural slate, razor-sharp edges, high-contrast typography.
- **Bio:** Organic warm amber and terracotta, fluid curves, biomimetic layout.
- **Atelier:** High-fashion luxury, editorial serif typography, warm canvas, minimalist borders.

### Deterministic Offline Magic Morph
The `magic_morph` engine analyzes event title and purpose strings using semantic keyword scoring combined with deterministic hashing to configure archetype tokens entirely offline without external AI APIs:
```bash
POST /api/v1/themes/magic-morph
Content-Type: application/json

{"name": "BioTech Summit 2026", "purpose": "Genomics and synthetic biology innovations"}
```

---

## 📐 Normalization Proof (+5 Bonus)

Read [`JUDGING.md`](JUDGING.md) for full mathematical definitions, formulas, and proofs covering:
- Weighted Raw Score calculations
- Individual Judge empirical mean and variance
- Global population scaling benchmarks
- Standardized Z-scores with standard error penalization
- Deterministic lexicographic tie-breaking: `(normalized_score DESC, raw_score DESC, evaluations DESC, project_id ASC)`

---

## 🛠️ Local Development (Without Docker)

```bash
# 1. Create and activate Python virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch ChameleonOS application server
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## 📄 License

Licensed under the [MIT License](LICENSE).
