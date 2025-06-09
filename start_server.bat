@echo off
chcp 65001 >nul
title 个人影视网站 - IPv6支持

echo.
echo ==========================================
echo   🎬 个人影视网站 - IPv6双栈启动脚本
echo ==========================================
echo.

REM 检查Python是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到Python，请确保Python已安装并添加到PATH
    pause
    exit /b 1
)

REM 检查是否在项目目录
if not exist "manage.py" (
    echo ❌ 错误：请在项目根目录运行此脚本
    pause
    exit /b 1
)

echo 🔍 检查环境...
echo ✅ Python环境正常
echo ✅ Django项目检测成功
echo.

echo 🚀 启动服务器...
python start_server.py

pause 