@echo off
title 个人影视网站 - IPv4服务器
cd /d "%~dp0"
echo 🎬 启动IPv4服务器（端口520）...
python start_server_ipv4.py
pause 