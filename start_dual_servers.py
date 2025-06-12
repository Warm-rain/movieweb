#!/usr/bin/env python
"""
个人影视网站双服务器启动脚本
同时启动IPv4（520端口）和IPv6（8520端口）服务
"""

import os
import sys
import threading
import time
import django
from django.core.management import execute_from_command_line
from django.core.management.base import CommandError

def start_ipv4_server():
    """启动IPv4服务器（端口520）"""
    try:
        print("🚀 启动IPv4服务器...")
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            '0.0.0.0:520'  # IPv4绑定
        ])
    except Exception as e:
        print(f"❌ IPv4服务器启动失败: {e}")

def start_ipv6_server():
    """启动IPv6服务器（端口8520）"""
    try:
        print("🚀 启动IPv6服务器...")
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            '[::]:8520'  # IPv6绑定
        ])
    except Exception as e:
        print(f"❌ IPv6服务器启动失败: {e}")

def main():
    """同时启动两个服务器"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    try:
        django.setup()
        
        print("🎬 个人影视网站双服务器模式启动中...")
        print("📡 IPv4服务器: 端口520")
        print("📡 IPv6服务器: 端口8520")
        print()
        print("🔗 访问地址：")
        print("   IPv4本地: http://127.0.0.1:520/")
        print("   IPv4局域网: http://0.0.0.0:520/")
        print("   IPv6本地: http://[::1]:8520/")
        print("   IPv6公网: http://[您的IPv6地址]:8520/")
        print()
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止所有服务器")
        print("=" * 60)
        
        # 使用线程启动IPv6服务器
        ipv6_thread = threading.Thread(target=start_ipv6_server, daemon=True)
        ipv6_thread.start()
        
        # 等待IPv6服务器启动
        time.sleep(2)
        
        # 在主线程启动IPv4服务器
        start_ipv4_server()
        
    except KeyboardInterrupt:
        print("\n🛑 所有服务器已停止")
        return 0
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("\n💡 建议分别启动：")
        print("   IPv4: python start_server_ipv4.py")
        print("   IPv6: python start_server_ipv6.py")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 