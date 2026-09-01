New-Item -ItemType Directory -Force "D:\code\airmap\data\logs" | Out-Null
Set-Location "D:\code\airmap\backend"
python manage.py runserver 127.0.0.1:8000 --noreload *> "D:\code\airmap\data\logs\backend.log"
