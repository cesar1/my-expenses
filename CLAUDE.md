# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Run in production
gunicorn app:app
```

Enable debug mode via environment variable (do not hardcode):
```bash
FLASK_DEBUG=true python app.py
```

There are no tests or a linter configured for this project.

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and a SQLite database.

- **`app.py`** — all routes, DB init, and form validation. `get_db()` opens a new SQLite connection per request using `sqlite3.Row` for dict-like row access. `init_db()` is called once at startup. All form input goes through `validate_expense_form()` before any DB write.
- **`expenses.db`** — auto-generated on first run, not committed to git.
- **`templates/`** — `base.html` holds the full layout, CSS (CSS variables), and Bootstrap 5 CDN links. All other templates extend it via `{% block content %}`.

## Key conventions

- `CATEGORIES` in `app.py` is the single source of truth for allowed categories. Templates and validation both reference it — keep them in sync.
- All form validation (required fields, positive amount, valid category, date format `YYYY-MM-DD`) is handled in `validate_expense_form()`. Add new validation there, not inline in route handlers.
- Category badge styling is driven by CSS classes named `cat-<CategoryName>` in `base.html`. Adding a new category requires a matching CSS rule.
- Delete uses `POST`, not `GET`, to prevent accidental deletion via link prefetch.
