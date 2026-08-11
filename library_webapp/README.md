# Library Web App — CMPT 354 Step 6

Flask web application for the Community Library DBMS.  
Runs locally or deploys to **Google Cloud Run**.

---

## Prerequisites

- Python 3.10+
- `library.db` built by `library_schema.ipynb` + `library_populate.ipynb`
- Place `library.db` in the same folder as `app.py`

---

## Run locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the dev server
python app.py

# 3. Open in browser
# http://localhost:5000
```

Set `FLASK_DEBUG=1` for auto-reload during development:
```bash
FLASK_DEBUG=1 python app.py
```

---

## Deploy to Google Cloud Run

### One-time setup
```bash
# Install the gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

### Build and deploy
```bash
# From inside the library_webapp/ folder:

# Build the container image in Cloud Build and push to Artifact Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/library-app

# Deploy to Cloud Run (unauthenticated = public URL)
gcloud run deploy library-app \
  --image gcr.io/YOUR_PROJECT_ID/library-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=your-secret-key-here

# Cloud Run prints a service URL like:
# https://library-app-xxxx-uc.a.run.app
```

### Notes on SQLite + Cloud Run
Cloud Run containers are **stateless** — the SQLite file is bundled into the
image at build time. This is fine for a course demo but means writes don't
persist across deployments. For production, the natural upgrade is
**Cloud SQL (PostgreSQL)**, which your Python code can reach by swapping
`sqlite3.connect(DB_PATH)` for a `psycopg2` connection string.

---

## Project structure

```
library_webapp/
├── app.py              # Flask routes (all 8 operations)
├── requirements.txt    # Flask + gunicorn
├── Dockerfile          # Container definition for Cloud Run
├── .dockerignore
├── library.db          # SQLite database (copy from Jupyter workspace)
└── templates/
    ├── base.html       # Shared layout, nav, styles
    ├── index.html      # Home / dashboard
    ├── items.html      # 1. Find an item
    ├── borrow.html     # 2. Borrow
    ├── return.html     # 3. Return
    ├── donate.html     # 4. Donate
    ├── events.html     # 5. Find an event
    ├── register.html   # 6. Register for event
    ├── volunteer.html  # 7. Volunteer
    └── help.html       # 8. Ask for help
```
