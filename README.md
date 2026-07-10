# ARC Scheduling App

A Django web app for scheduling student-employee shifts at the Academic Resource Center (ARC) at Ozarks Technical Community College (OTC). It replaces manual/spreadsheet scheduling with a weekly availability system, a drag-to-paint schedule builder, per-department rosters, and exports to Microsoft Teams Shifts and .ics calendar files.

This document is written for whoever is picking up ownership of this project (IT staff, a new developer, etc.) with no prior context. It covers what the app does, how the pieces fit together, exactly which settings/environment variables control it, how to run it locally, how it's deployed, and the non-obvious behaviors that will trip you up if you don't know about them.

---

## Table of contents

1. [What this app does](#1-what-this-app-does)
2. [Tech stack](#2-tech-stack)
3. [Repository layout](#3-repository-layout)
4. [Data model / core concepts](#4-data-model--core-concepts)
5. [User roles & permissions](#5-user-roles--permissions)
6. [Local development setup](#6-local-development-setup)
7. [Bootstrapping the first admin user (read this first)](#7-bootstrapping-the-first-admin-user-read-this-first)
8. [Environment variables](#8-environment-variables)
9. [Database](#9-database)
10. [Static files](#10-static-files)
11. [Deployment (Railway)](#11-deployment-railway)
12. [Common admin tasks](#12-common-admin-tasks)
13. [Where things live (feature → file map)](#13-where-things-live-feature--file-map)
14. [Known quirks & gotchas](#14-known-quirks--gotchas)
15. [Testing](#15-testing)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. What this app does

Student employees ("Employees" in the code) log in and:
- Mark their **weekly availability** (recurring, by day of week) and optionally flag blocks as "preferred."
- Set **desired weekly hours** and whether they want a scheduled lunch break.

Schedulers/admins additionally:
- Use the **Schedule Builder** to paint shifts onto a weekly grid for each employee, per "Schedule" (department/team), respecting each employee's marked availability and existing shifts on other schedules (conflict detection).
- Maintain a **default weekly template** per schedule that can be loaded into any week as a starting point, or saved back from the current week.
- Manage **operating hours** (weekly defaults, plus one-off date overrides for holidays/closures).
- Control a global **availability editing window** (when employees are allowed to change their availability), with per-employee exceptions.
- Export a schedule's shifts to an **.xlsx file formatted for Microsoft Teams Shifts import**.
- Manage the **roster**: which schedules exist, and which employees belong to / can schedule for each one.
- Register new employees and reset passwords to a configurable default.

The org name shown in the UI is "ARC" and the dashboard branding assumes an academic support center context, but nothing about the app is OTC-specific beyond copy/branding.

---

## 2. Tech stack

| Layer | Technology |
|---|---|
| Language / framework | Python 3.12, Django 6.0 |
| Database | SQLite (local dev, zero-config) or PostgreSQL (production, via `DATABASE_URL`) |
| WSGI server | Gunicorn |
| Static files | WhiteNoise (`CompressedManifestStaticFilesStorage`) — no separate CDN/S3 needed |
| Frontend | Server-rendered Django templates + vanilla JavaScript (no build step, no npm/node — there is no frontend toolchain to install) |
| Spreadsheet export | `openpyxl` (Teams Shifts `.xlsx` template) |
| Hosting | Railway (see [Deployment](#11-deployment-railway)) |

There is no JavaScript package manager, bundler, or frontend build step anywhere in this project — all JS lives inline in `<script>` tags inside the templates and is served as-is.

---

## 3. Repository layout

```
Scheduling-App/                    ← repo root
├── README.md                      ← this file
├── DEPLOYMENT.md                  ← platform-specific deploy walkthroughs (Heroku/Railway/VPS)
├── Procfile                       ← production start command (Railway/Heroku)
├── requirements.txt                ← the one and only Python dependency list — installed by Railway/Heroku
├── runtime.txt                    ← Python version pin for some platforms (python-3.12.3)
├── deploy.sh                      ← reference VPS setup script (systemd + nginx), not used by Railway
├── .env.example                   ← example env var names (not auto-loaded, see §8)
├── mise.toml                      ← pins tool versions for the `mise` version manager (optional)
└── scheduling_app/                ← the actual Django project root — most work happens here
    ├── manage.py
    ├── db.sqlite3                 ← local dev database (git-ignored in principle; currently tracked — see §14)
    ├── fixtures/demo.json         ← loadable demo dataset (4 employees, 4 schedules, availability, shifts)
    ├── staticfiles/               ← output of `collectstatic` (gitignored, regenerated on every deploy) — don't hand-edit, don't commit
    ├── scheduling_app/            ← Django "project" package (settings, urls, wsgi/asgi)
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py / asgi.py
    ├── account/                   ← employees, auth, registration, roster admin
    │   ├── models.py              ← Employee (custom user model), SecuritySettings
    │   ├── views.py / forms.py / admin.py / urls.py
    │   └── templates/account/
    ├── scheduling/                ← the scheduling domain: availability, hours, schedule builder, exports
    │   ├── models.py              ← Schedule, WeeklyAvailability, AvailabilityWindow, OperatingHours,
    │   │                             WeeklySchedule, ScheduleEntry, ShiftLabel, DateOperatingHours
    │   ├── views.py / forms.py / admin.py / urls.py / exports.py / signals.py
    │   ├── data/TeamsShiftsTemplate.xlsx   ← template workbook used by the Teams export
    │   └── templates/scheduling/
    └── dashboard/                 ← the logged-in landing page / personal weekly view / .ics export
        ├── views.py / urls.py
        └── templates/dashboard/
```

Three Django apps, all under `AUTH_USER_MODEL = 'account.Employee'`:

| App | Responsibility |
|---|---|
| `account` | The custom `Employee` user model, login/logout/password change, employee registration, employee list & roster management (admin-only screens). |
| `scheduling` | Everything schedule-related: weekly availability, operating hours (weekly + date overrides), the availability edit window toggle, the schedule builder UI, default weekly templates, shift position labels, and both export formats. |
| `dashboard` | The post-login landing page: the logged-in employee's own weekly schedule, the admin/scheduler quick-links menu, and the `.ics` calendar export. |

---

## 4. Data model / core concepts

All models live in `account/models.py` and `scheduling/models.py`. `dashboard/models.py` is empty — that app is views/templates only.

### Employee (`account.Employee`)
Custom user model (`AUTH_USER_MODEL`), extends Django's `AbstractUser` (so it has `username`, `password`, `email`, `is_active`, `is_staff`, `is_superuser`, etc. built in) plus:

| Field | Purpose |
|---|---|
| `role` | One of `ASSISTANT_I`, `ASSISTANT_II`, `TUTOR`, `LIBRARY` (`Employee.Role` choices). Drives automatic schedule membership — see §14. |
| `is_admin` | **Custom, app-level admin flag.** Not the same as `is_superuser`/`is_staff`. Gates all admin-only screens in this app. See §7 — this is not set by `createsuperuser`. |
| `part_time` | Whether the employee is subject to the 19.5 hr/week part-time cap enforced by the schedule builder. |
| `desired_weekly_hours`, `wants_lunch_break` | Preferences the employee sets themselves; shown to schedulers while building the schedule. |
| `birthdate` | Stored, currently informational only (no age-based logic uses it). |
| `availability_override_until` | If set to a future date, this employee can edit their availability even while the global window is closed (see `AvailabilityWindow` below). |

### SecuritySettings (`account.SecuritySettings`)
A **singleton** (always `pk=1`) holding `default_password` — the password newly-registered employees get, and what "Reset Password" resets an employee back to. Editable from the Employee List admin screen. Defaults to `Test123!` if never changed.

### Schedule (`scheduling.Schedule`)
A department/team (e.g. "Math", "CIS", "Assistant I"). Has:
- `members` (M2M to Employee) — who can be assigned shifts on this schedule, and who appears in the Schedule Builder sidebar for it.
- `schedulers` (M2M to Employee) — who (besides admins) can open the Schedule Builder / register employees / export for this specific schedule.
- `color` — used throughout the UI (conflict highlighting, key legends).

### WeeklyAvailability (`scheduling.WeeklyAvailability`)
An employee's recurring weekly availability: one row per contiguous block (day of week + start/end time + `AVAILABLE` or `PREFERRED`). No two blocks for the same employee/day may overlap (enforced in `clean()`). This is what the Schedule Builder checks shifts against.

### AvailabilityWindow (`scheduling.AvailabilityWindow`)
A **singleton** (`pk=1`, admin-editable at **Availability Window**) controlling whether employees are currently allowed to edit their own availability at all. Three fields: `is_open` (manual toggle), `opens_at`, `closes_at` (optional date range).

**Current logic (`is_currently_open()`): the toggle and the date range are independent — editing is open if *either* the toggle is on, *or* today falls within the date range.** You don't need both. Individual employees can still be exempted from a closed window via their `availability_override_until` field.

### OperatingHours / DateOperatingHours (`scheduling.OperatingHours` / `DateOperatingHours`)
`OperatingHours` is the weekly default (one row per weekday, e.g. Mon 8am–5pm). `DateOperatingHours` is a one-off override for a specific date (holiday closures, special hours) and always wins over the weekly default when both exist for a date. Both are editable at **Edit Operating Hours**.

### WeeklySchedule (`scheduling.WeeklySchedule`)
The **default weekly template** for a `Schedule` — a recurring, dateless shift pattern (day of week + times) used as a starting point when building a real week. Edited at **Default Weekly Schedule**, and can be pushed into the currently-viewed week ("Load Default Week") or captured back from it ("Save Week as Default") from inside the Schedule Builder.

### ScheduleEntry (`scheduling.ScheduleEntry`)
An **actual dated shift**: one employee, one schedule, one specific date, start/end time. This is what the Schedule Builder writes when you paint a cell and Save, what the employee dashboard reads to show "your shifts this week," and what both exports (.ics and Teams `.xlsx`) read from. No two entries for the same employee on the same date may overlap.

### ShiftLabel (`scheduling.ShiftLabel`)
A named position/role tag (e.g. "Front Desk", "WC") scoped to one `Schedule`, with a color, applied to individual painted cells in the builder. Shared across everyone using that schedule — created/deleted inline from the builder sidebar.

### LEAD_IN / part-time cap constants (not DB fields, worth knowing)
- `scheduling/views.py`: `MIN_AVAILABILITY_HOURS = 10` — employees marking fewer than 10 hrs/week of availability are flagged red in the builder sidebar as "not schedulable."
- `dashboard/views.py` and the builder JS: `LEAD_IN_MINUTES = 15` — the first schedulable slot of each day is a 15-minute "lead-in" block (for an opening supervisor), and `PARTTIME_MAX = 19.5` hrs/week is the hard cap the builder enforces for anyone with `part_time=True`.

---

## 5. User roles & permissions

There is no Django Groups/Permissions usage — access is entirely three custom checks, all defined near the top of `scheduling/views.py` and `account/views.py`:

| Tier | Check | Can do |
|---|---|---|
| **Any logged-in employee** | `login_required` only | Manage their own availability, change their own password, view their own dashboard schedule, export their own `.ics`. |
| **Scheduler** | `user.is_admin OR user.scheduler_of.exists()` | Everything above, plus: Schedule Builder, Default Weekly Schedule, Register Employee, Export Teams Shifts — **but only for schedules they're listed as a `scheduler` on** (admins see/manage every schedule; schedulers see only their own). |
| **Admin** | `user.is_admin` | Everything above for **all** schedules, plus: Employee List (register/edit/remove employees, reset passwords, set default password), Schedule Roster (create/rename/delete schedules, manage members & schedulers), Edit Operating Hours, Availability Window. |

`is_admin` is a plain boolean field on `Employee` — grant/revoke it from **Employee List → Edit** (admin-only) or the Django admin shell (see §7). It is intentionally decoupled from Django's own `is_staff`/`is_superuser`, which only control access to `/admin/` (the built-in Django admin site), not this app's own admin screens.

---

## 6. Local development setup

Prerequisites: Python 3.12 (matches `runtime.txt`; the repo has been run successfully on 3.12.3–3.12.5). No Node/npm needed.

```bash
# 1. Clone and enter the repo
git clone https://github.com/GravesSoftwareDev/ARC---Scheduling-App.git Scheduling-App
cd Scheduling-App

# 2. Create and activate a virtualenv (the existing repo already has one at ./venv —
#    reuse it or delete and recreate)
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Move into the actual Django project
cd scheduling_app

# 5. Run migrations (creates/updates db.sqlite3 — no DATABASE_URL means SQLite by default)
python manage.py migrate

# 6. Create your own login and grant yourself app-admin rights — see §7, this is not optional
python manage.py createsuperuser
python manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"

# 7. (Optional) load the bundled demo dataset — 4 employees, 4 schedules, sample availability & shifts
python manage.py loaddata fixtures/demo.json

# 8. Run the dev server
python manage.py runserver
# → http://127.0.0.1:8000/login/
```

No `.env` loading happens automatically (see §8) — for local dev this is fine, since every setting has a safe default when no environment variables are set at all.

> **Local dev callout:** with zero environment variables set, `DJANGO_DEBUG` defaults to `False`. If you want Django's debug error pages and other DEBUG-only conveniences while developing, run with `DJANGO_DEBUG=True` explicitly:
> ```bash
> DJANGO_DEBUG=True python manage.py runserver
> ```

---

## 7. Bootstrapping the first admin user (read this first)

This is the single most important non-obvious step in this whole project, so it gets its own section.

`python manage.py createsuperuser` creates a Django **superuser** (`is_superuser=True`, `is_staff=True`) — this lets that user log into the built-in Django admin at `/admin/`. **It does NOT set `is_admin=True`.** `is_admin` is this app's own custom field, and it is deliberately **not editable from `/admin/` at all** — `account/admin.py`'s `EmployeeAdmin.fieldsets` never lists `is_admin`, so the field doesn't even appear on the Django admin edit form.

The only ways to set `is_admin=True` on a user are:
1. **The app's own "Employee List → Edit Employee" screen** — but that screen is itself gated by `is_admin`, so this only works once someone already has it.
2. **Directly via `manage.py shell`** (or a one-off script), e.g.:
   ```bash
   python manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='desired_username').update(is_admin=True)"
   ```

**On a brand-new environment (new database), step 2 above is mandatory** — there is no other path to getting your first admin. Do this immediately after your first `migrate` + `createsuperuser`, before trying to use any admin screen in the app itself.

---

## 8. Environment variables

Read directly from `os.environ` in `scheduling_app/scheduling_app/settings.py`. **Nothing in this codebase loads a `.env` file automatically** (no `python-dotenv`, no `django-environ`) — `.env.example` at the repo root is documentation only. On your own machine you must `export` these yourself (or use a tool like `direnv`/`mise` configured to do so); on Railway/Heroku you set them in the platform's dashboard and the platform injects them as real process environment variables.

| Variable | Read in settings.py as | Default if unset | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | `SECRET_KEY` | `SECRET_KEY` env var, then a hardcoded insecure fallback string | **Must** be set to a long random value in any environment reachable by real users. Generate one with `python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`. |
| `SECRET_KEY` | (fallback for the above) | — | Legacy/alternate name, checked only if `DJANGO_SECRET_KEY` is unset. |
| `DJANGO_DEBUG` | `DEBUG` | `False` | Set to the exact string `True` to enable debug mode. **Never `True` in production** — it exposes stack traces and settings to visitors. |
| `DEBUG` | (fallback for the above) | — | Legacy/alternate name, checked only if `DJANGO_DEBUG` is unset. |
| `DJANGO_ALLOWED_HOSTS` | `ALLOWED_HOSTS` | `localhost 127.0.0.1` | Space- or comma-separated list of hostnames the app will answer requests for. **`.railway.app` is always appended automatically**, regardless of this variable, so any Railway-issued subdomain works out of the box. Django will return HTTP 400 for any `Host` header not in this list. |
| `ALLOWED_HOSTS` | (fallback for the above) | — | Legacy/alternate name, checked only if `DJANGO_ALLOWED_HOSTS` is unset. |
| `DATABASE_URL` | `DATABASE_URL` | unset → falls back to local SQLite (`db.sqlite3`) | Standard `postgres://user:pass@host:port/dbname` URL. Railway's Postgres plugin sets this automatically when attached. Parsed with `dj_database_url`. |

Every one of the above has a working default for local development — you can `python manage.py runserver` with **zero** environment variables set and it will just work against SQLite.

`CSRF_TRUSTED_ORIGINS` is derived automatically from `ALLOWED_HOSTS` (every host except `localhost`/`127.0.0.1`/wildcard entries gets an `https://` origin added) — there's no separate variable to set for it.

**There is no outbound email functionality in this app at all** — no password-reset emails, no notifications, nothing reads an `EMAIL_HOST_*`-style variable anywhere in the code. If you ever see one referenced in an old doc, deploy note, or dashboard config, it's a leftover from an earlier plan and does nothing today. Don't spend time chasing an "email not sending" issue, because nothing tries to send email; password resets are handled manually by an admin (§12).

When `DEBUG=False`, `settings.py` also turns on `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and trusts `X-Forwarded-Proto` for SSL detection (`SECURE_PROXY_SSL_HEADER`) — required for cookies/CSRF to work correctly behind Railway's HTTPS-terminating proxy. Don't disable `DEBUG` without HTTPS in front of the app, or logins will silently fail (secure cookies won't be set over plain HTTP).

---

## 9. Database

- **Local/default:** SQLite at `scheduling_app/db.sqlite3`. Zero setup. Note this file is currently **tracked in git** despite being listed in `.gitignore` (it was committed before the ignore rule existed) — see §14.
- **Production:** PostgreSQL, selected automatically the moment `DATABASE_URL` is set (see §8). Railway's Postgres plugin provisions this and injects the variable for you — no manual connection-string assembly needed.
- Migrations are the standard Django mechanism: `python manage.py migrate`. The production `Procfile` runs this on every deploy automatically (see §11) — you generally never need to run it by hand against production, only after writing new migrations locally (`python manage.py makemigrations`).
- No app-level backup tooling exists. If you need production backups, use your Postgres provider's built-in backup/snapshot feature (Railway offers this in its Postgres plugin settings).

---

## 10. Static files

Serving is handled by **WhiteNoise** directly inside the Django process (`whitenoise.middleware.WhiteNoiseMiddleware`) — there is no separate nginx/CDN static file server, no S3. `STORAGES['staticfiles']` uses `CompressedManifestStaticFilesStorage`, which:
- Gzip-compresses assets.
- Renames each file with a content hash (e.g. `styles.b8ab6fbc8b94.css`) so browsers can cache them forever without going stale on deploy.

Source static files live per-app (e.g. `scheduling_app/account/static/account/css/styles.css`). Running `python manage.py collectstatic --noinput` copies + hashes + gzips them into `scheduling_app/staticfiles/` (`STATIC_ROOT`), which is what actually gets served in production.

- **In local dev with `DEBUG=True`**, Django's `runserver` serves static files straight from each app's source `static/` directory automatically — you do **not** need to run `collectstatic` while developing; edits to CSS/JS show up on refresh with no build step.
- **In production**, `collectstatic` must have been run at least once (the `Procfile` does this on every deploy automatically — see §11). If you ever see unstyled pages or 404s for `/static/...` in production, that's the first thing to check.

---

## 11. Deployment (Railway)

**Production currently deploys straight from the `shifts_dev` branch** (not `main` — `main` is the nominal default branch on GitHub but is not what Railway is watching as of this writing). Confirm which branch your Railway service is tracking under its Settings → Source before assuming a push to `main` will go live — if you push a fix and it doesn't appear, this is the first thing to check. Whatever branch Railway is watching auto-deploys on every push to it.

### One-time setup (already done for the existing Railway project, included here in case this ever needs to be rebuilt from scratch)
1. Create a Railway project, link this GitHub repo, and pick the branch to deploy from.
2. Attach a Railway **PostgreSQL** plugin — this sets `DATABASE_URL` automatically.
3. Add the environment variables from §8 in Railway's dashboard (at minimum `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`).
4. Railway auto-detects the root `Procfile` and `requirements.txt` — no extra build configuration needed.
5. After the first deploy, bootstrap your first admin exactly as in §7, but via `railway run`:
   ```bash
   railway run python scheduling_app/manage.py migrate
   railway run python scheduling_app/manage.py createsuperuser
   railway run python scheduling_app/manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"
   ```

### What happens on every deploy
The `Procfile` defines the single production process:
```
web: cd scheduling_app && python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py shell -c "from account.models import Employee; Employee.objects.filter(is_active=False).delete()" && gunicorn scheduling_app.wsgi --bind 0.0.0.0:$PORT --workers 3
```
In order, every time the app boots (including every deploy):
1. `collectstatic` — regenerates `staticfiles/` from source.
2. `migrate` — applies any new database migrations.
3. **Hard-deletes any `Employee` row with `is_active=False`.** This is a real, irreversible data deletion that runs automatically on every deploy — see §14, this is important.
4. Starts Gunicorn with 3 workers, bound to Railway's `$PORT`.

For deploying to platforms other than Railway (Heroku, a bare VPS), see `DEPLOYMENT.md` at the repo root, which has full walkthroughs for both plus a VPS `deploy.sh` reference script.

---

## 12. Common admin tasks

All of these require an `is_admin=True` account (see §5/§7), and are reachable from the dashboard's quick-links menu after login.

| Task | Where |
|---|---|
| Create a new schedule (department/team) | **Schedule Roster** → "New Schedule" |
| Add/remove employees from a schedule, or grant/revoke scheduler rights for a schedule | **Schedule Roster** → click a schedule |
| Register a new employee | **Register Employee** (also available to schedulers, scoped to their own schedules) |
| Change an employee's role, admin flag, part-time status, or grant a temporary availability-edit exception | **Employee List** → Edit |
| Reset an employee's password back to the org default | **Employee List** → Reset Password |
| Change what the "default password" for new/reset accounts actually is | **Employee List** → set Default Password (must pass Django's normal password validators) |
| Remove an employee entirely | **Employee List** → Remove (this is an immediate hard delete, not a soft-deactivate — see §14) |
| Set weekly operating hours | **Edit Operating Hours** |
| Close for a holiday / set special one-off hours for a specific date | **Edit Operating Hours** → date override section |
| Open or close the window during which employees may edit their own availability | **Availability Window** |
| Grant one specific employee an exception to edit availability while the window is closed | **Employee List** → Edit → "Availability override until" |
| Build/edit a specific week's shifts | **Build Schedule** |
| Edit the recurring default template a schedule starts from | **Default Weekly Schedule** |
| Copy the on-screen week into the default template, or load the default template into the on-screen week | Inside **Build Schedule**: "Save Week as Default" / "Load Default Week" |
| Export a schedule's shifts for Microsoft Teams Shifts import | **Export Teams Shifts** |
| Employee's personal calendar subscription file | Employee dashboard → "Export to .ics" (any logged-in employee, not admin-only) |

---

## 13. Where things live (feature → file map)

| Screen / URL name | View function | Template |
|---|---|---|
| Login | `django.contrib.auth.views.LoginView` | `account/templates/account/registration/login.html` |
| Dashboard (`dashboard:dashboard`) | `dashboard/views.py::dashboard` | `dashboard/templates/dashboard/dashboard.html` |
| `.ics` export (`dashboard:export_ics`) | `dashboard/views.py::export_schedule_ics` | (no template — returns a `.ics` file) |
| Manage Availability (`scheduling:manage_availability`) | `scheduling/views.py::manage_availability` | `scheduling/templates/scheduling/availability.html` |
| Availability Window (`scheduling:availability_window`) | `scheduling/views.py::availability_window` | `scheduling/templates/scheduling/availability_window.html` |
| Edit Operating Hours (`scheduling:operating_hours`) | `scheduling/views.py::operating_hours` | `scheduling/templates/scheduling/operating_hours.html` |
| Schedule Builder (`scheduling:schedule_builder`) | `scheduling/views.py::schedule_builder` | `scheduling/templates/scheduling/schedule_builder.html` |
| Default Weekly Schedule (`scheduling:default_schedule_builder`) | `scheduling/views.py::default_schedule_builder` | `scheduling/templates/scheduling/default_schedule_builder.html` |
| Export Teams Shifts (`scheduling:export_teams_shifts`) | `scheduling/views.py::export_teams_shifts` + `scheduling/exports.py` | `scheduling/templates/scheduling/export_teams_shifts.html` |
| Employee List (`account:employee_list`) | `account/views.py::employee_list` | `account/templates/account/employee_list.html` |
| Edit Employee (`account:edit_employee`) | `account/views.py::edit_employee` | `account/templates/account/edit_employee.html` |
| Register Employee (`account:registration`) | `account/views.py::registration` | `account/templates/account/register.html` |
| Schedule Roster (`account:roster`) | `account/views.py::roster` | `account/templates/account/roster.html` |

Full URL prefixes are unnamespaced at the root (see `scheduling_app/urls.py` — `account.urls`, `scheduling.urls`, and `dashboard.urls` are all mounted at `''`). Run `python manage.py show_urls` (if `django-extensions` were installed — it isn't) or just read the three `urls.py` files directly for the exact paths; there's no single combined URL list.

---

## 14. Known quirks & gotchas

Things that look like bugs but are actually just how this app currently works, plus a couple of real rough edges to be aware of:

- **`is_admin` bootstrapping.** Covered fully in §7 — the built-in Django admin (`/admin/`) cannot grant it; you need a shell command for the very first admin.
- **The Procfile permanently deletes deactivated employees on every deploy.** `Employee.objects.filter(is_active=False).delete()` runs on every boot. Nothing in the app's own UI currently sets `is_active=False` (the "Remove" button in Employee List does an immediate hard `delete()`, not a soft-deactivate) — the only way to end up with `is_active=False` today is editing it directly via `/admin/`. If that ever happens, know that the *next deploy* will permanently erase that employee and all their foreign-keyed history (availability, shifts, etc., which cascade-delete). There is no "undo."
- **Removing an employee from Employee List is already a hard delete**, not a soft one — `emp.delete()` cascades to their `WeeklyAvailability`, `WeeklySchedule`, and `ScheduleEntry` rows immediately (via `on_delete=CASCADE`). Historical shift data for a removed employee is not recoverable from the app once this happens.
- **Automatic schedule membership syncing** (`scheduling/signals.py`, wired up in `scheduling/apps.py::SchedulingConfig.ready`): any `Schedule` whose **name** contains "assistant i" or "assistant ii" (case-insensitive) automatically has every `Employee` with the matching `role` added as a `member` — both when an employee's role changes/is created, and when a schedule is created/renamed. This means renaming a schedule to include "Assistant I" in its name will silently bulk-add every Assistant I employee as a member. This is intentional (keeps the "Assistant I"/"Assistant II" schedules in sync with actual role assignments) but is easy to forget about if you're troubleshooting "why did this person get added to a schedule I didn't touch."
- **`db.sqlite3` is committed to git** even though `.gitignore` lists it — it was tracked before the ignore rule was added, and `.gitignore` only prevents *new* tracking, not existing tracked files. Be careful committing over it during local development/testing (it currently contains a mix of real-looking and demo employee records); if you need to experiment locally without risking that data, copy it aside first or work on an untracked copy.
- **`.gitignore`'s `staticfiles/` rule used to be written as `/staticfiles/`**, which anchors to the repo root — but the actual directory is `scheduling_app/staticfiles/`, one level down, so the rule silently never matched and ~540 generated, content-hashed CSS/JS build artifacts (regenerated fresh on every deploy anyway) had been accumulating in git history. This has been fixed (`staticfiles/` with no leading slash) and the tracked copies removed — if you ever see `git status` wanting to add a huge pile of files under `staticfiles/` again, the ignore rule has regressed.
- **`TIME_ZONE = 'UTC'`** in `settings.py`, with `USE_TZ = True`. All stored datetimes are UTC; the app largely works in plain `date`/`time` fields (not timezone-aware datetimes) for schedule logic, so this mostly doesn't bite — but if timezone-aware datetime logic is ever added, remember the project-wide zone is UTC, not US/Central, despite this being a Missouri-based school.
- **Multi-location scheduling exists in the data model but isn't currently exposed.** `ScheduleEntry.location` and the schedule builder's location-column rendering are wired up in the template/JS, but `scheduling/views.py::schedule_builder` currently hardcodes `dept_locs = ['']` / `has_locs = False`, so no schedule actually shows multiple location columns today. This looks like a dormant/future feature, not a bug.
- **No automated test suite.** `account/tests.py`, `scheduling/tests.py`, `dashboard/tests.py` are all untouched Django boilerplate (`# Create your tests here.`) — there is nothing to run and nothing enforcing regressions. See §15.

---

## 15. Testing

There are no meaningful automated tests in this repository today — the three `tests.py` files are empty Django scaffolding. `python manage.py test` will run and pass instantly (0 tests), which is not a signal of correctness. Manual verification (log in as different role tiers, exercise the flow you changed) is currently the only form of QA in this project. If you add real tests, they'll be auto-discovered by `python manage.py test` with no extra configuration needed.

---

## 16. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `DisallowedHost` error / HTTP 400 on a request | The request's `Host` header isn't in `DJANGO_ALLOWED_HOSTS`. Add it (§8). Railway subdomains are covered automatically. |
| Logged in, but none of the admin screens/links appear | Your account has `is_admin=False`. Grant it per §7 (not the same as Django superuser). |
| Just deployed, page is unstyled / static 404s | `collectstatic` didn't run or failed. The `Procfile` runs it automatically — check deploy logs. Locally, this only matters if you're running with `DEBUG=False`; with `DEBUG=True` static files are served straight from source, no `collectstatic` needed. |
| Pushed a fix, production doesn't reflect it | Confirm which branch Railway is actually deploying from (§11) — it is currently `shifts_dev`, not `main`. A push to the wrong branch simply won't deploy. |
| Login works but immediately loses session / CSRF errors in production | `DEBUG=False` forces secure cookies; if the app is somehow being reached over plain HTTP (not through Railway's HTTPS-terminating proxy), secure cookies won't be set and auth will silently break. Should not happen on Railway's default domain; would matter if you ever point a custom domain at this without HTTPS. |
| An employee vanished along with their shift/availability history | Someone used "Remove" on Employee List (immediate hard delete + cascade), or the employee had `is_active=False` and a deploy's cleanup step purged them (§14). There is no recovery path from within the app — restore from a database backup if one exists. |
| "Why did this person get added to that schedule automatically?" | Automatic role↔schedule-name syncing — see §14. |
| Trying to email someone from the app / expecting a password-reset email | Not implemented — there is no email sending in this codebase (§8). Password resets are manual (admin resets to the shared default password). |
