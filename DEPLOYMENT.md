# Scheduling App Deployment Guide

## Quick Start to Production

### Local Verification ✓
Your app is running locally! To test:
```bash
cd /Users/sgraves/Desktop/ARC/Scheduling-App/scheduling_app
source ../venv/bin/activate
python manage.py runserver
# Visit http://localhost:8000
```

## 🚀 Deploy to Heroku (Recommended for Beginners)

### 1. Prerequisites
```bash
# Install Heroku CLI
brew tap heroku/brew && brew install heroku

# Login
heroku login
```

### 2. Create & Deploy
```bash
cd /Users/sgraves/Desktop/ARC/Scheduling-App

# Create Heroku app
heroku create your-app-name

# Set environment variables
heroku config:set DJANGO_SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
heroku config:set DJANGO_DEBUG=False
heroku config:set DJANGO_ALLOWED_HOSTS=your-app-name.herokuapp.com

# Add PostgreSQL database
heroku addons:create heroku-postgresql:essential-0

# Deploy
git push heroku main

# Run migrations
heroku run python scheduling_app/manage.py migrate

# Create superuser (optional)
heroku run python scheduling_app/manage.py createsuperuser
```

### 3. View Logs
```bash
heroku logs --tail
```

---

## 🚂 Deploy to Railway.app (Easiest)

1. Go to [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Railway auto-detects `Procfile` and `runtime.txt`
4. Set environment variables in the Railway dashboard:
   - `DJANGO_SECRET_KEY`: Generate with `python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: `your-domain.railway.app`
5. Railway auto-deploys on every push!

---

## 🐧 Deploy to VPS (AWS, DigitalOcean, Linode)

### Using the Deploy Script
```bash
# On your VPS, download and run the deploy script
bash deploy.sh
```

### Manual Setup (if needed)
```bash
# On VPS as root/with sudo:
sudo apt-get update
sudo apt-get install -y python3.12 python3-pip postgresql nginx

# Create app user and directory
sudo useradd -m appuser
sudo mkdir -p /var/www/scheduling-app
sudo chown appuser:appuser /var/www/scheduling-app
cd /var/www/scheduling-app

# Clone repo (as appuser)
git clone https://github.com/yourusername/scheduling-app.git .

# Create virtual environment and install
python3 -m venv venv
source venv/bin/activate
pip install -r scheduling_app/requirements.txt

# Create .env file
cat > .env << EOF
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com www.yourdomain.com
DATABASE_URL=postgres://user:password@localhost:5432/scheduling_db
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EOF

# Prepare static files
cd scheduling_app
python manage.py migrate
python manage.py collectstatic --noinput

# Create systemd service (as root)
# ... (see deploy.sh for service file)

# Start service
sudo systemctl start scheduling-app
sudo systemctl enable scheduling-app
```

---

## 📝 Environment Variables Reference

```env
# Required
DJANGO_SECRET_KEY=long-random-string-here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com www.yourdomain.com

# Database (auto-generated on Heroku/Railway, required for VPS)
DATABASE_URL=postgres://user:password@host:5432/dbname

# Email (optional but recommended)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-specific-password
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

---

## 🔒 Security Checklist

- ✅ `DEBUG=False` in production
- ✅ Strong `DJANGO_SECRET_KEY` (generated, not hardcoded)
- ✅ HTTPS enabled (Heroku/Railway do this automatically)
- ✅ `SECURE_SSL_REDIRECT=True` (already in settings)
- ✅ PostgreSQL database (not SQLite)
- ✅ Custom `ALLOWED_HOSTS` set to your domain
- ✅ Strong database password

---

## 🐛 Troubleshooting

### "Allowed hosts issue"
Update `DJANGO_ALLOWED_HOSTS` to include your domain:
```bash
# Heroku example
heroku config:set DJANGO_ALLOWED_HOSTS=your-app-name.herokuapp.com
```

### "Static files not loading"
Already handled! Run:
```bash
python manage.py collectstatic --noinput
```

### "Database connection error"
Ensure `DATABASE_URL` is set correctly:
```bash
# Heroku
heroku config

# Railway - check dashboard
```

### "Module not found errors"
Ensure all dependencies are installed:
```bash
pip install -r scheduling_app/requirements.txt
```

---

## 📚 Additional Resources

- Django Deployment: https://docs.djangoproject.com/en/6.0/howto/deployment/
- Heroku Django Guide: https://devcenter.heroku.com/articles/deploying-python-and-django-apps-on-heroku
- Railway Docs: https://docs.railway.app/
- Gunicorn Docs: https://gunicorn.org/

---

## Next Steps

1. **Choose your platform**: Heroku (easiest), Railway (fast), or VPS (most control)
2. **Generate secret key**: `python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
3. **Set environment variables** according to your chosen platform
4. **Deploy and monitor logs**

Good luck! 🚀
