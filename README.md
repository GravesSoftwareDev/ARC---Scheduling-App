# Scheduling-App
Creating a scheduling app for Ozark's Tech Academic Resource Center

## Railway deployment

To deploy on Railway:

1. Create a Railway project and link this repository.
2. Add the following environment variables in Railway settings:
   - `DJANGO_SECRET_KEY`
   - `DJANGO_DEBUG` (set to `False` in production)
   - `DJANGO_ALLOWED_HOSTS` (for example: `your-app.railway.app`)
   - `DATABASE_URL` (Railway Postgres will provide this automatically)
   - `EMAIL_HOST_USER`
   - `EMAIL_HOST_PASSWORD`
   - `EMAIL_HOST` and `EMAIL_PORT` are optional if using Gmail defaults.
3. Use the root `requirements.txt` and `Procfile` already added to the repo.
4. After the app deploys, run migrations:
   ```bash
   railway run python scheduling_app/manage.py migrate
   ```

### Deployment files added

- `Procfile` - starts Gunicorn on `$PORT`
- `requirements.txt` - Railway installs required Python packages
- `.gitignore` - ignores `venv`, `db.sqlite3`, and generated files

### Notes

- If `DATABASE_URL` is not set, the project falls back to local SQLite for development.
- Static files are collected into `staticfiles`.
