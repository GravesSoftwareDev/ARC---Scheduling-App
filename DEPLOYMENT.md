# Deployment Guide

Platform-specific deployment instructions for the ARC Scheduling App. For local development setup, environment variable reference, and the data model, see `README.md` — this document only covers getting the app running on Heroku, Railway, or a self-managed VPS.

Before deploying anywhere, read `README.md` §7 ("Bootstrapping the first admin user"). It is referenced repeatedly below because it is the step most likely to be skipped, and skipping it leaves the first administrator locked out of every admin screen in the app.

## Local verification

To confirm the app runs correctly before deploying, follow the local setup steps in `README.md` §6, then visit `http://localhost:8000`.

---

## Deploy to Heroku

### 1. Prerequisites
```bash
# Install the Heroku CLI
brew tap heroku/brew && brew install heroku

# Log in
heroku login
```

### 2. Create and deploy
Run the following from the repository root:
```bash
# Create the Heroku app
heroku create your-app-name

# Set environment variables
heroku config:set DJANGO_SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
heroku config:set DJANGO_DEBUG=False
heroku config:set DJANGO_ALLOWED_HOSTS=your-app-name.herokuapp.com

# Add a PostgreSQL database
heroku addons:create heroku-postgresql:essential-0

# Deploy
git push heroku main

# Run migrations
heroku run python scheduling_app/manage.py migrate

# Create your login
heroku run python scheduling_app/manage.py createsuperuser

# createsuperuser alone does NOT grant access to this app's own admin
# screens (Employee List, Schedule Roster, etc.) — that is gated by a
# separate `is_admin` field with no UI path to set it on a brand-new
# database. Grant it to yourself directly:
heroku run python scheduling_app/manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"
```

### 3. View logs
```bash
heroku logs --tail
```

---

## Deploy to Railway

1. Go to [railway.app](https://railway.app) and connect the GitHub repository.
2. Railway auto-detects `Procfile` and `runtime.txt`; no additional build configuration is required.
3. Set the following environment variables in the Railway dashboard:
   - `DJANGO_SECRET_KEY` — generate with `python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
   - `DJANGO_DEBUG` — `False`
   - `DJANGO_ALLOWED_HOSTS` — your Railway domain, e.g. `your-domain.railway.app`
4. Railway deploys automatically on every push to the branch it is watching. Confirm which branch that is under the service's Settings before assuming a push to any particular branch will go live.
5. After the first deploy, bootstrap your first admin (`createsuperuser` alone is not enough — see `README.md` §7):
   ```bash
   railway run python scheduling_app/manage.py createsuperuser
   railway run python scheduling_app/manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"
   ```

---

## Deploy to a VPS (AWS, DigitalOcean, Linode, etc.)

### Using the deploy script
```bash
# On the VPS, from a clone of this repository
bash deploy.sh
```
`deploy.sh` installs system dependencies, creates a virtual environment, writes a `.env` file with a generated secret key, runs migrations and `collectstatic`, and configures both a systemd service and an Nginx reverse proxy. Review it before running — the placeholder domain and database credentials it writes must be edited for your environment, and it prints the remaining manual steps (DNS, HTTPS, admin bootstrap) when it finishes.

### Manual setup
```bash
# As root or with sudo
sudo apt-get update
sudo apt-get install -y python3.12 python3-pip python3-venv postgresql postgresql-contrib nginx

# Create an app user and directory
sudo useradd -m appuser
sudo mkdir -p /var/www/scheduling-app
sudo chown appuser:appuser /var/www/scheduling-app
cd /var/www/scheduling-app

# Clone the repository (as appuser)
git clone https://github.com/yourusername/scheduling-app.git .

# Create a virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create the .env file
cat > .env << EOF
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com www.yourdomain.com
DATABASE_URL=postgres://user:password@localhost:5432/scheduling_db
EOF

# Run migrations and collect static files
cd scheduling_app
python manage.py migrate
python manage.py collectstatic --noinput

# Bootstrap the first admin — createsuperuser alone does NOT grant access
# to this app's own admin screens, which are gated by a separate
# `is_admin` field with no other way to set it on a brand-new database.
# See README.md §7 for the full explanation.
python manage.py createsuperuser
python manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"
cd ..
```

Create the systemd service (as root):
```bash
sudo tee /etc/systemd/system/scheduling-app.service > /dev/null <<EOF
[Unit]
Description=Scheduling App
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/scheduling-app/scheduling_app
EnvironmentFile=/var/www/scheduling-app/.env
ExecStart=/var/www/scheduling-app/venv/bin/gunicorn scheduling_app.wsgi:application --workers 3 --bind unix:/run/gunicorn.sock
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable scheduling-app
sudo systemctl start scheduling-app
```
`EnvironmentFile` is required. Nothing in this codebase loads `.env` files on its own (no `python-dotenv`), so without this line the variables set above would never reach the application, and it would silently fall back to the insecure default secret key and local SQLite.

Configure Nginx as a reverse proxy in front of gunicorn's unix socket. Static files do not need their own location block — WhiteNoise already serves them from inside the same gunicorn process. `X-Forwarded-Proto` is required for secure cookies and CSRF to work once `DJANGO_DEBUG=False` (see `settings.py`'s `SECURE_PROXY_SSL_HEADER`):
```bash
sudo tee /etc/nginx/sites-available/scheduling-app > /dev/null <<'EOF'
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://unix:/run/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/scheduling-app /etc/nginx/sites-enabled/scheduling-app
sudo nginx -t && sudo systemctl reload nginx
```

Finally, enable HTTPS. This is required, not optional — `DJANGO_DEBUG=False` forces secure cookies, which silently break login over plain HTTP:
```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## Environment variables reference

```env
# Required
DJANGO_SECRET_KEY=long-random-string-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com www.yourdomain.com

# Database (provisioned automatically on Heroku/Railway; must be set manually on a VPS)
DATABASE_URL=postgres://user:password@host:5432/dbname
```

See `README.md` §8 for the full variable reference, including which legacy-looking variable names are not actually read by the code.

---

## Security checklist

- `DEBUG=False` in production.
- A strong, generated `DJANGO_SECRET_KEY` — never the hardcoded development fallback.
- HTTPS enabled. Required, not optional: `settings.py` sets `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` whenever `DEBUG=False`, so login and CSRF protection will silently break over plain HTTP. Heroku and Railway terminate HTTPS automatically; on a VPS this must be set up manually (see the `certbot` step above).
- The app is sitting behind a proxy that sets `X-Forwarded-Proto` correctly. `settings.py` trusts that header (`SECURE_PROXY_SSL_HEADER`) to determine whether a request was made over HTTPS. Heroku and Railway already do this; the VPS Nginx configuration above sets it explicitly.
- A PostgreSQL database, not SQLite.
- `DJANGO_ALLOWED_HOSTS` set to the actual production domain(s).
- A strong database password.

---

## Troubleshooting

**A superuser was created, but no admin screens appear in the app.**
`createsuperuser` only grants access to Django's built-in `/admin/`. It does not set this app's own `is_admin` field, which gates every admin screen inside the app itself (Employee List, Schedule Roster, etc.), and that field cannot be set through `/admin/` either. Run this once against the platform's shell (see the bootstrap step under each platform above):
```bash
python manage.py shell -c "from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)"
```
See `README.md` §7 for the full explanation.

**`DisallowedHost` / allowed-hosts error.**
Update `DJANGO_ALLOWED_HOSTS` to include the request's domain:
```bash
# Heroku example
heroku config:set DJANGO_ALLOWED_HOSTS=your-app-name.herokuapp.com
```

**Static files not loading.**
Run `collectstatic`:
```bash
python manage.py collectstatic --noinput
```

**Database connection error.**
Confirm `DATABASE_URL` is set correctly:
```bash
# Heroku
heroku config

# Railway — check the dashboard's Variables tab
```

**`ModuleNotFoundError` after installing dependencies.**
Reinstall from the repository root's `requirements.txt`:
```bash
pip install -r requirements.txt
```

---

## Additional resources

- Django deployment checklist: https://docs.djangoproject.com/en/6.0/howto/deployment/
- Heroku Django guide: https://devcenter.heroku.com/articles/deploying-python-and-django-apps-on-heroku
- Railway documentation: https://docs.railway.app/
- Gunicorn documentation: https://gunicorn.org/
