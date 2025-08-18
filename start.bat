@echo off
SETLOCAL ENABLEEXTENSIONS
SETLOCAL ENABLEDELAYEDEXPANSION
set ERRLEVEL=0

echo =============================
echo 🔁 Activating virtual environment...
echo =============================
IF NOT EXIST venv (
    echo ⚠️ Virtual environment not found. Creating one...
    python -m venv venv >nul 2>&1
)

call venv\Scripts\activate.bat

echo =============================
echo 🔄 Stashing local tracked changes...
echo =============================
git stash push -k

echo =============================
echo ⬇️ Pulling latest changes from main...
echo =============================
git pull origin main

echo =============================
echo 🔁 Re-applying stashed changes (if any)...
echo =============================
git stash pop || echo No stash to pop

echo =============================
echo 📦 Installing dependencies...
echo =============================
python -m pip install --upgrade pip --no-cache-dir
pip install -r requirements.txt --no-cache-dir

echo =============================
echo 🔄 Applying migrations...
echo =============================
python manage.py makemigrations
python manage.py migrate

echo =============================
echo 🚀 Starting Django server...
echo =============================
python manage.py runserver

start http://127.0.0.1:8000/

ENDLOCAL
pause
