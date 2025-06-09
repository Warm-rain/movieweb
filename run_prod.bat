@echo off
echo 启动生产服务器 (Gunicorn)...

if not exist "venv" (
    echo 错误: 虚拟环境不存在，请先运行 deploy\setup.bat
    pause
    exit /b 1
)

if not exist "logs" mkdir logs

call venv\Scripts\activate.bat
gunicorn -c deploy/gunicorn_config.py movieweb.wsgi:application

pause 