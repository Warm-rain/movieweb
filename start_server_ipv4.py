#!/usr/bin/env python
"""
个人影视网站IPv4启动脚本
使用520端口，专门用于IPv4访问
"""

import os
import sys
import django
from django.core.management import execute_from_command_line
from django.core.management.base import CommandError

def main():
    """启动Django开发服务器，IPv4模式，端口520"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    # 检查是否指定了端口参数
    port = 520  # IPv4默认端口
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("❌ 端口必须是数字")
            return 1
    
    try:
        django.setup()
        
        print(f"🎬 个人影视网站启动中... (IPv4模式，端口: {port})")
        print("📡 IPv4专用模式")
        print("🔗 访问地址：")
        print(f"   本地: http://127.0.0.1:{port}/")
        print(f"   局域网: http://0.0.0.0:{port}/")
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止服务器")
        print("-" * 50)
        
        # 使用IPv4绑定
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            f'0.0.0.0:{port}'  # IPv4绑定
        ])
        
    except CommandError as e:
        print(f"❌ 启动失败: {e}")
        print("💡 可能的解决方案：")
        print(f"   1. 确保端口{port}未被占用")
        if port < 1024:
            print("   2. 低于1024的端口需要管理员权限，请以管理员身份运行")
        print("   3. 尝试其他端口，如：python start_server_ipv4.py 8000")
        print(f"   4. 手动启动：python manage.py runserver 127.0.0.1:{port}")
        return 1
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        return 0

if __name__ == '__main__':
    sys.exit(main()) 