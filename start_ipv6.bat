@echo off
title 个人影视网站 - IPv6服务器
cd /d "%~dp0"
echo 🎬 启动IPv6服务器（端口8520）...
python start_server_ipv6.py
pause 