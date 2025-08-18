@echo off
SETLOCAL ENABLEEXTENSIONS
SETLOCAL ENABLEDELAYEDEXPANSION
set ERRLEVEL=0

echo =============================
echo 🔁 Checking Python version...
echo =============================
python --version | findstr "3.11" >nul || (
    echo ❌ Python 3.11 is required. Current version:
    python --version
    pause
    exit /b 1
)

echo =============================
echo 🐍 Activating virtual environment...
echo =============================
IF NOT EXIST venv (
    echo ⚠️ Virtual environment not found. Creating one...
    python -m venv venv
)
call venv\Scripts\activate.bat

echo =============================
echo ⬇️ Pulling latest changes from main...
echo =============================
git pull origin main

echo =============================
echo 🔍 Checking for uncommitted changes...
echo =============================
git diff --quiet || (
    echo ⚠️ You have local changes. Please commit or stash manually.
    pause
    exit /b 1
)

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
start http://127.0.0.1:8000/
python manage.py runserver

ENDLOCAL
pause
