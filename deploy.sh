#!/bin/bash
# Deploy script for VPS deployment
set -e

# Update and install system dependencies
sudo apt-get update
sudo apt-get install -y python3.12 python3-pip python3-venv postgresql postgresql-contrib nginx

# Create app directory
sudo mkdir -p /var/www/scheduling-app
cd /var/www/scheduling-app

# Clone your repo (replace with your repo)
# sudo git clone https://github.com/yourusername/Scheduling-App.git .

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
# NOTE: edit DJANGO_ALLOWED_HOSTS and DATABASE_URL below before running this
# script for real — these placeholders won't work as-is.
cat > .env << EOF
DJANGO_SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com www.yourdomain.com
DATABASE_URL=postgres://user:password@localhost:5432/scheduling_db
EOF

# Prepare static files
cd scheduling_app
python manage.py migrate
python manage.py collectstatic --noinput
cd ..

# Create systemd service
# EnvironmentFile is required — nothing in this codebase loads .env on its own
# (no python-dotenv), so without this line DJANGO_SECRET_KEY/DATABASE_URL/etc.
# above would silently never reach the app and it would fall back to the
# insecure default secret key and local SQLite.
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

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable scheduling-app
sudo systemctl start scheduling-app

# Configure Nginx as a reverse proxy in front of gunicorn's unix socket.
# Static files are NOT proxied separately — WhiteNoise serves them straight
# out of the same Django/gunicorn process, so nginx just needs to forward
# everything. X-Forwarded-Proto is required: settings.py trusts it to detect
# HTTPS (SECURE_PROXY_SSL_HEADER), and without it secure cookies/CSRF will
# silently break once DJANGO_DEBUG=False.
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
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "Setup complete! Remaining manual steps:"
echo "  1. Edit server_name in /etc/nginx/sites-available/scheduling-app to your real domain,"
echo "     then 'sudo systemctl reload nginx'."
echo "  2. Point your domain's DNS at this server."
echo "  3. Get HTTPS (required — DJANGO_DEBUG=False forces secure cookies that need it):"
echo "       sudo apt-get install -y certbot python3-certbot-nginx"
echo "       sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com"
echo "  4. Bootstrap your first admin account (createsuperuser needs an interactive"
echo "     terminal, so it isn't run automatically by this script):"
echo "       cd /var/www/scheduling-app/scheduling_app"
echo "       source ../venv/bin/activate"
echo "       python manage.py createsuperuser"
echo "       python manage.py shell -c \"from account.models import Employee; Employee.objects.filter(username='YOUR_USERNAME').update(is_admin=True)\""
echo "     (createsuperuser alone is NOT enough to use this app's admin screens — see README.md §7.)"
