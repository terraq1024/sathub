New-Item -ItemType Directory -Force "D:\code\airmap\data\logs" | Out-Null
Set-Location "D:\code\airmap\frontend"
npm.cmd run dev -- --host 127.0.0.1 *> "D:\code\airmap\data\logs\frontend.log"
