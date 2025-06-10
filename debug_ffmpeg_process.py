#!/usr/bin/env python
# -*- coding: utf-8 -*-

import subprocess
import os
import time
import threading

def monitor_process_real_time():
    """实时监控FFmpeg进程"""
    print("🧪 实时监控FFmpeg进程...")
    
    # 视频路径
    video_path = r"D:\qbittorrent\[仙逆].Renegade.Immortal.2023.S01.Complete.2160p.WEB-DL.H265.AAC-UBWEB\[仙逆].Renegade.Immortal.2023.S01E92.2160p.WEB-DL.H265.AAC-UBWEB.mp4"
    
    # 输出目录
    output_dir = "debug_realtime_output"
    os.makedirs(output_dir, exist_ok=True)
    
    # 输出文件
    output_file = os.path.join(output_dir, "360p.m3u8")
    
    # FFmpeg命令 - 与转码代码完全一致
    ffmpeg_cmd = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',
        '-vf', 'scale=640:360',
        '-c:a', 'aac',
        '-t', '30',
        '-f', 'hls',
        '-hls_time', '2',
        '-hls_list_size', '3',
        '-hls_flags', 'delete_segments',
        output_file
    ]
    
    print(f"命令: {' '.join(ffmpeg_cmd)}")
    
    try:
        # 启动进程 - 与转码代码一致
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=os.getcwd(),
            shell=False,
        )
        
        print(f"✅ 进程启动，PID: {process.pid}")
        
        # 启动后台线程读取输出
        def read_stderr():
            for line in iter(process.stderr.readline, ''):
                if line.strip():
                    print(f"FFmpeg: {line.strip()}")
        
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # 实时监控文件生成
        max_wait = 20
        wait_start = time.time()
        
        while time.time() - wait_start < max_wait:
            # 检查进程状态
            return_code = process.poll()
            
            # 检查文件生成
            if os.path.exists(output_file):
                print(f"📝 发现HLS索引文件: {output_file}")
                # 检查片段文件
                try:
                    files = os.listdir(output_dir)
                    ts_files = [f for f in files if f.endswith('.ts')]
                    print(f"📼 片段文件: {ts_files}")
                    if ts_files:
                        print("✅ HLS流已准备好！")
                        break
                except Exception as e:
                    print(f"❌ 检查文件时出错: {e}")
            
            # 显示目录内容
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                if files:
                    print(f"📁 目录文件: {files}")
            
            # 检查进程状态
            if return_code is not None:
                print(f"🔍 进程已退出，返回码: {return_code}")
                if return_code == 0:
                    print("✅ 进程正常完成")
                    break
                else:
                    print("❌ 进程异常退出")
                    break
            
            time.sleep(2)  # 每2秒检查一次
        
        # 最终状态
        process.terminate()
        print(f"🏁 监控结束")
        
        # 显示最终文件状态
        if os.path.exists(output_dir):
            files = os.listdir(output_dir)
            print(f"📁 最终文件: {files}")
            
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    content = f.read()
                print(f"📄 HLS内容:\n{content}")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    monitor_process_real_time() 