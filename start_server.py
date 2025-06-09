#!/usr/bin/env python
"""
个人影视网站启动脚本
支持IPv4和IPv6双栈访问，端口520
"""

import os
import sys
import django
from django.core.management import execute_from_command_line
from django.core.management.base import CommandError

def main():
    """启动Django开发服务器，支持IPv6"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    try:
        django.setup()
        
        print("🎬 个人影视网站启动中...")
        print("📡 支持IPv4和IPv6双栈访问")
        print("🔗 访问地址：")
        print("   IPv4: http://127.0.0.1:520/")
        print("   IPv6: http://[::1]:520/")
        print("   局域网IPv4: http://0.0.0.0:520/")
        print("   局域网IPv6: http://[::]:520/")
        print("   公网IPv6: http://[您的IPv6地址]:520/")
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止服务器")
        print("-" * 50)
        
        # 绑定到所有IPv6和IPv4接口
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            '[::]:520'  # IPv6双栈绑定，同时支持IPv4和IPv6
        ])
        
    except CommandError as e:
        print(f"❌ 启动失败: {e}")
        print("💡 可能的解决方案：")
        print("   1. 确保端口520未被占用")
        print("   2. 在管理员权限下运行（端口<1024需要管理员权限）")
        print("   3. 使用其他端口，如：python start_server.py 8520")
        print("   4. 如果IPv6失败，尝试：python manage.py runserver 0.0.0.0:520")
        return 1
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        return 0

def start_with_port(port=520):
    """使用指定端口启动服务器"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    try:
        django.setup()
        
        print(f"🎬 个人影视网站启动中... (端口: {port})")
        print("📡 支持IPv4和IPv6双栈访问")
        print("🔗 访问地址：")
        print(f"   IPv4: http://127.0.0.1:{port}/")
        print(f"   IPv6: http://[::1]:{port}/")
        print(f"   局域网IPv4: http://0.0.0.0:{port}/")
        print(f"   局域网IPv6: http://[::]:{port}/")
        print(f"   公网IPv6: http://[您的IPv6地址]:{port}/")
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止服务器")
        print("-" * 50)
        
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            f'[::]:{port}'  # IPv6双栈绑定
        ])
        
    except CommandError as e:
        print(f"❌ 启动失败: {e}")
        print("💡 尝试IPv4模式：python manage.py runserver 0.0.0.0:{port}")
        return 1
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        return 0

if __name__ == '__main__':
    # 检查是否指定了端口参数
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            sys.exit(start_with_port(port))
        except ValueError:
            print("❌ 端口必须是数字")
            sys.exit(1)
    else:
        sys.exit(main()) 