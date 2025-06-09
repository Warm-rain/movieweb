#!/usr/bin/env python
"""
个人影视网站IPv6启动脚本
专门用于IPv6公网访问
"""

import os
import sys
import django
from django.core.management import execute_from_command_line
from django.core.management.base import CommandError

def main():
    """启动Django开发服务器，专用IPv6模式"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    try:
        django.setup()
        
        print("🎬 个人影视网站启动中... (IPv6专用模式)")
        print("📡 绑定到所有IPv6接口")
        print("🔗 访问地址：")
        print("   本地IPv6: http://[::1]:8520/")
        print("   公网IPv6: http://[2409:8a62:5952:6b00:d16b:b43d:82cd:2c2b]:8520/")
        print("   任何IPv6: http://[您的IPv6地址]:8520/")
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止服务器")
        print("-" * 60)
        
        # 强制绑定到IPv6，端口8520
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            '[::]:8520'  # 绑定所有IPv6接口
        ])
        
    except CommandError as e:
        print(f"❌ IPv6启动失败: {e}")
        print("💡 可能的解决方案：")
        print("   1. 确保系统支持IPv6")
        print("   2. 检查防火墙设置")
        print("   3. 以管理员权限运行")
        print("   4. 检查端口8520是否被占用")
        print("   5. 尝试其他端口：python start_server_ipv6.py 9520")
        return 1
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        return 0

def start_with_port(port):
    """使用指定端口启动IPv6服务器"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movieweb.settings')
    
    try:
        django.setup()
        
        print(f"🎬 个人影视网站启动中... (IPv6模式, 端口: {port})")
        print("📡 绑定到所有IPv6接口")
        print("🔗 访问地址：")
        print(f"   本地IPv6: http://[::1]:{port}/")
        print(f"   公网IPv6: http://[2409:8a62:5952:6b00:d16b:b43d:82cd:2c2b]:{port}/")
        print(f"   任何IPv6: http://[您的IPv6地址]:{port}/")
        print("📋 管理后台: /admin/")
        print("👤 用户注册: /accounts/signup/")
        print("⏹️  按 Ctrl+C 停止服务器")
        print("-" * 60)
        
        execute_from_command_line([
            'manage.py', 
            'runserver', 
            f'[::]:{port}'
        ])
        
    except CommandError as e:
        print(f"❌ 启动失败: {e}")
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