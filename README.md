# Expense Tracker

A lightweight personal finance web app built with Flask and SQLite. Track your daily spending by adding, editing, and deleting expenses — organized by category with a live running total.

## Features

- Multi-user accounts — register, log in, and see only your own expenses
- Public landing page with a read-only sample preview for logged-out visitors
- View all expenses in a clean, sortable table
- Add new expenses with description, amount, category, and date
- Edit or delete existing expenses
- Color-coded categories: Housing, Food, Transport, Entertainment, Utilities, Other
- Live total of all spending displayed on the main page
- Form validation with inline error messages
- Empty state prompt when no expenses exist yet
- `/healthz` endpoint that reads the database, for deployment health checks

## Tech Stack

- **Backend:** Python, Flask, Flask-Login
- **Database:** SQLite (via Python's built-in `sqlite3`)
- **Frontend:** Jinja2 templates, Bootstrap 5, Bootstrap Icons
- **Server:** gunicorn behind nginx
- **Containers:** Docker + Docker Compose
- **CI/CD:** Jenkins (declarative pipeline, `Jenkinsfile`)
- **Infrastructure:** AWS EC2, EBS, Terraform (`infra/`)
- **Tests:** pytest

## Getting Started

**1. Clone the repository**

```bash
git clone https://github.com/cesar1/my-expenses.git
cd my-expenses
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Run the app**

```bash
python app.py
```

**4. Open in your browser**

```
http://127.0.0.1:5000
```

The SQLite database (`expenses.db`) is created automatically on first run — no setup required.

Two environment variables are read if present: `FLASK_DEBUG=true` enables debug mode, and `DB_PATH` overrides where the database file lives. Both default sensibly for local work.

**Run the tests**

```bash
python -m pytest tests/ -v
```

## Project Structure

```
├── app.py                   # Flask app: routes, auth, DB init, and validation
├── requirements.txt         # Python dependencies
├── Dockerfile               # App image (gunicorn, non-root user)
├── docker-compose.yml       # app + nginx services
├── Jenkinsfile              # CI/CD pipeline definition
├── expenses.db              # SQLite database (auto-generated, not committed)
├── templates/
│   ├── base.html            # Shared layout and styles
│   ├── landing.html         # Public preview for logged-out visitors
│   ├── index.html           # Expense list with total
│   ├── add.html             # Add expense form
│   ├── edit.html            # Edit expense form
│   ├── login.html           # Login form
│   └── register.html        # Registration form
├── tests/                   # pytest suite (validation, routes, auth)
├── deploy/                  # nginx config, nginx image, as-built deployment notes
├── infra/                   # Terraform: EC2, EBS, security group, IAM, snapshots
└── scripts/                 # Maintenance scripts
```

## Expense Fields

| Field       | Type   | Description                              |
|-------------|--------|------------------------------------------|
| Description | Text   | What the expense was for                 |
| Amount      | Number | Cost in USD (e.g. 12.50)                 |
| Category    | Select | Housing, Food, Transport, Entertainment, Utilities, Other |
| Date        | Date   | When the expense occurred                |

## Deployment

The app runs in Docker on an AWS EC2 instance, as two containers defined in `docker-compose.yml`:

- **`app`** — gunicorn serving the Flask app on port 5000, not published to the host
- **`nginx`** — reverse proxy publishing port 80, config in `deploy/nginx.docker.conf`

```bash
docker compose up -d --build
```

Two details matter for durability:

- **The database lives outside the container.** `expenses.db` sits on a separate encrypted EBS volume, bind-mounted to `/data` in the container and selected via the `DB_PATH` environment variable. The volume is set to survive instance termination, so the instance itself is disposable.
- **The secret key comes from the environment**, loaded by Compose from a root-owned file on the host — never from the repository.

The full as-built record, operating commands, and known gaps are in [`deploy/DOCKER-RESTORE.md`](deploy/DOCKER-RESTORE.md).

## CI/CD

Jenkins runs the pipeline defined in [`Jenkinsfile`](Jenkinsfile) at the repository root. It is self-hosted in a container on the same EC2 box, bound to localhost and reached through an SSM port-forward rather than exposed to the internet. Builds are triggered by SCM polling, so a push to `main` is picked up within a couple of minutes.

| Stage | What it does |
|---|---|
| **Build** | Builds the app and nginx images, tagged `:b<build-number>` |
| **Test** | Runs the pytest suite **inside the freshly built image**, so the tests exercise the real artifact rather than the source tree beside it |
| **Deploy** | Brings the new images up via Docker Compose |
| **Health gate** | Polls `/healthz`, which reads SQLite — a page that renders without touching the database would report healthy even with the data volume unmounted |
| **Promote** | Retags the build as `:latest`, so only a health-gated image is ever the default |

Because promotion is gated, rolling back is just picking an earlier tag:

```bash
IMAGE_TAG=b12 docker compose -p my-expenses up -d
```

Jenkins is configured as code (JCasC) rather than through the UI, so the controller can be rebuilt from scratch. GitHub Actions was retired in favor of this setup in October 2026.

## Infrastructure

Terraform in [`infra/`](infra/) describes the AWS resources the app runs on — EC2 instance, Elastic IP, security group, IAM role for SSM access, and a Data Lifecycle Manager policy for daily EBS snapshots. It never touches application code or the database.

> **Note:** the Terraform state is currently out of date with respect to the running infrastructure, which was rebuilt by hand during the Docker migration. See `infra/README.md` and the outstanding items in `deploy/DOCKER-RESTORE.md` before running `terraform apply`.

## License

MIT
