#!/bin/bash
# Deploy script for VPS deployment

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
pip install -r scheduling_app/requirements.txt

# Create .env file
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
sudo tee /etc/systemd/system/scheduling-app.service > /dev/null <<EOF
[Unit]
Description=Scheduling App
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/scheduling-app/scheduling_app
ExecStart=/var/www/scheduling-app/venv/bin/gunicorn scheduling_app.wsgi:application --workers 3 --bind unix:/run/gunicorn.sock
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable scheduling-app
sudo systemctl start scheduling-app

# Configure Nginx (create your own nginx config)
echo "Setup complete! Configure Nginx and update your domain DNS."
