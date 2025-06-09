@echo off
echo 启动开发服务器...

if not exist "venv" (
    echo 错误: 虚拟环境不存在，请先运行 deploy\setup.bat
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python manage.py runserver

pause 