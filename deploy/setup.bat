@echo off
echo 个人影视网站部署脚本 for Windows
echo ====================================

echo 1. 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo 错误: Python未安装或未配置到PATH
    pause
    exit /b 1
)

echo 2. 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo 虚拟环境创建完成
) else (
    echo 虚拟环境已存在
)

echo 3. 激活虚拟环境...
call venv\Scripts\activate.bat

echo 4. 安装依赖包...
pip install -r requirements.txt

echo 5. 检查FFmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo 警告: FFmpeg未找到，缩略图生成功能将不可用
    echo 请从 https://ffmpeg.org/download.html 下载并安装FFmpeg
    pause
)

echo 6. 创建数据库...
python manage.py makemigrations
python manage.py migrate

echo 7. 创建超级用户...
echo 请创建管理员账号:
python manage.py createsuperuser

echo 8. 收集静态文件...
python manage.py collectstatic --noinput

echo 9. 创建必要目录...
if not exist "media" mkdir media
if not exist "media\thumbnails" mkdir media\thumbnails
if not exist "logs" mkdir logs

echo ====================================
echo 部署完成！
echo.
echo 开发环境运行:
echo   python manage.py runserver
echo.
echo 生产环境运行:
echo   gunicorn -c deploy/gunicorn_config.py movieweb.wsgi:application
echo.
echo 扫描视频文件:
echo   python manage.py scan_videos "D:\Videos" --generate-thumbnails
echo ====================================
pause 