"""
GPU硬解实时转码服务
"""

import os
import subprocess
import threading
import time
import hashlib
from pathlib import Path
from django.conf import settings

class TranscodingService:
    """GPU硬解转码服务"""
    
    def __init__(self):
        self.transcode_dir = Path(settings.MEDIA_ROOT) / 'transcoded'
        self.transcode_dir.mkdir(exist_ok=True)
        self.active_jobs = {}
        
        # 分辨率配置
        self.resolutions = {
            '2160p': {'width': 3840, 'height': 2160, 'bitrate': '15M'},
            '1440p': {'width': 2560, 'height': 1440, 'bitrate': '10M'},
            '1080p': {'width': 1920, 'height': 1080, 'bitrate': '5M'},
            '720p': {'width': 1280, 'height': 720, 'bitrate': '3M'},
            '480p': {'width': 854, 'height': 480, 'bitrate': '1.5M'},
            '360p': {'width': 640, 'height': 360, 'bitrate': '800k'},
        }
        
        # GPU编码器优先级
        self.encoders = {
            'h264': ['h264_nvenc', 'h264_qsv', 'h264_amf', 'libx264'],
            'h265': ['hevc_nvenc', 'hevc_qsv', 'hevc_amf', 'libx265']
        }
        
        # 硬件解码器
        self.decoders = {
            'h264': ['h264_cuvid', 'h264_qsv'],
            'h265': ['hevc_cuvid', 'hevc_qsv'],
            'mpeg4': ['mpeg4_cuvid'],
        }
    
    def get_best_encoder(self, codec='h264'):
        """获取最佳编码器"""
        try:
            result = subprocess.run(['ffmpeg', '-encoders'], 
                                  capture_output=True, text=True, timeout=10)
            available_encoders = result.stdout
            
            for encoder in self.encoders.get(codec, ['libx264']):
                if encoder in available_encoders:
                    return encoder
            
            return 'libx264'  # 默认软件编码器
        except:
            return 'libx264'
    
    def get_best_decoder(self, input_path):
        """获取最佳解码器"""
        try:
            # 检测视频编码格式
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name', '-of', 'csv=p=0',
                input_path
            ], capture_output=True, text=True, timeout=10)
            
            codec = result.stdout.strip().lower()
            
            # 根据编码格式选择解码器
            decoder_candidates = self.decoders.get(codec, [])
            
            # 检查可用的解码器
            decoders_result = subprocess.run(['ffmpeg', '-decoders'], 
                                           capture_output=True, text=True, timeout=10)
            available_decoders = decoders_result.stdout
            
            for decoder in decoder_candidates:
                if decoder in available_decoders:
                    return decoder
            
            return None  # 使用默认软件解码
        except:
            return None
    
    def get_video_info(self, input_path):
        """获取视频信息"""
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_streams', '-show_format', input_path
            ], capture_output=True, text=True, timeout=10)
            
            import json
            info = json.loads(result.stdout)
            
            video_stream = None
            for stream in info['streams']:
                if stream['codec_type'] == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                return {
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'duration': float(info['format'].get('duration', 0)),
                    'codec': video_stream.get('codec_name', 'unknown'),
                    'bitrate': int(info['format'].get('bit_rate', 0))
                }
            
            return None
        except:
            return None
    
    def generate_transcode_id(self, movie_id, resolution):
        """生成转码任务ID"""
        return hashlib.md5(f"{movie_id}_{resolution}".encode()).hexdigest()[:16]
    
    def get_hls_path(self, movie_id, resolution):
        """获取HLS文件路径"""
        transcode_id = self.generate_transcode_id(movie_id, resolution)
        return self.transcode_dir / transcode_id / f"{resolution}.m3u8"
    
    def start_transcoding(self, movie, resolution):
        """开始GPU硬解转码"""
        transcode_id = self.generate_transcode_id(movie.id, resolution)
        output_dir = self.transcode_dir / transcode_id
        output_dir.mkdir(exist_ok=True)
        
        # 检查是否已经在转码或已完成
        hls_file = output_dir / f"{resolution}.m3u8"
        if transcode_id in self.active_jobs:
            return transcode_id, 'transcoding'
        
        if hls_file.exists():
            return transcode_id, 'completed'
        
        # 获取视频信息
        video_info = self.get_video_info(movie.file_path)
        if not video_info:
            return None, 'error'
        
        # 获取最佳编码器和解码器
        encoder = self.get_best_encoder('h264')
        decoder = self.get_best_decoder(movie.file_path)
        
        # 分辨率配置
        res_config = self.resolutions.get(resolution)
        if not res_config:
            return None, 'invalid_resolution'
        
        # 如果原始分辨率小于目标分辨率，不进行放大
        if video_info['height'] < res_config['height']:
            resolution = self.get_suitable_resolution(video_info['height'])
            res_config = self.resolutions[resolution]
            hls_file = output_dir / f"{resolution}.m3u8"
        
        # 构建FFmpeg命令
        cmd = ['ffmpeg', '-y']
        
        # 输入配置
        if decoder:
            cmd.extend(['-c:v', decoder])
        
        cmd.extend(['-i', movie.file_path])
        
        # 视频编码配置
        cmd.extend([
            '-c:v', encoder,
            '-preset', 'fast',  # NVENC预设
            '-b:v', res_config['bitrate'],
            '-maxrate', res_config['bitrate'],
            '-bufsize', str(int(res_config['bitrate'].rstrip('kM')) * 2) + res_config['bitrate'][-1],
            '-vf', f"scale={res_config['width']}:{res_config['height']}:force_original_aspect_ratio=decrease",
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ac', '2',
            '-ar', '44100',
        ])
        
        # HLS输出配置
        cmd.extend([
            '-f', 'hls',
            '-hls_time', '6',  # 每个片段6秒
            '-hls_list_size', '0',  # 保留所有片段
            '-hls_flags', 'delete_segments+append_list',
            '-hls_segment_filename', str(output_dir / f"{resolution}_%03d.ts"),
            str(hls_file)
        ])
        
        # 启动转码进程
        def run_transcoding():
            try:
                print(f"🎬 开始转码: {movie.title} -> {resolution}")
                print(f"📋 命令: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                self.active_jobs[transcode_id] = {
                    'process': process,
                    'movie': movie,
                    'resolution': resolution,
                    'status': 'transcoding',
                    'start_time': time.time()
                }
                
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    print(f"✅ 转码完成: {movie.title} -> {resolution}")
                    self.active_jobs[transcode_id]['status'] = 'completed'
                else:
                    print(f"❌ 转码失败: {movie.title} -> {resolution}")
                    print(f"错误: {stderr}")
                    self.active_jobs[transcode_id]['status'] = 'failed'
                
            except Exception as e:
                print(f"❌ 转码异常: {e}")
                if transcode_id in self.active_jobs:
                    self.active_jobs[transcode_id]['status'] = 'failed'
            
            finally:
                # 清理完成的任务
                if transcode_id in self.active_jobs:
                    del self.active_jobs[transcode_id]
        
        # 在后台线程中运行转码
        thread = threading.Thread(target=run_transcoding)
        thread.daemon = True
        thread.start()
        
        return transcode_id, 'started'
    
    def get_suitable_resolution(self, height):
        """根据视频高度获取合适的分辨率"""
        if height >= 2160:
            return '2160p'
        elif height >= 1440:
            return '1440p'
        elif height >= 1080:
            return '1080p'
        elif height >= 720:
            return '720p'
        elif height >= 480:
            return '480p'
        else:
            return '360p'
    
    def get_available_resolutions(self, movie):
        """获取视频可用的分辨率"""
        video_info = self.get_video_info(movie.file_path)
        if not video_info:
            return ['原画']
        
        available = ['原画']  # 总是包含原画
        
        # 根据原始分辨率添加可用选项
        original_height = video_info['height']
        
        for res_name, res_config in self.resolutions.items():
            if res_config['height'] <= original_height:
                available.append(res_name)
        
        return available
    
    def get_transcode_status(self, transcode_id):
        """获取转码状态"""
        if transcode_id in self.active_jobs:
            job = self.active_jobs[transcode_id]
            elapsed = time.time() - job['start_time']
            return {
                'status': job['status'],
                'elapsed': elapsed,
                'movie': job['movie'].title,
                'resolution': job['resolution']
            }
        
        return None
    
    def cleanup_old_transcodes(self, max_age_hours=24):
        """清理旧的转码文件"""
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        for transcode_dir in self.transcode_dir.iterdir():
            if transcode_dir.is_dir():
                try:
                    if transcode_dir.stat().st_mtime < cutoff_time:
                        import shutil
                        shutil.rmtree(transcode_dir)
                        print(f"🗑️ 清理旧转码: {transcode_dir.name}")
                except:
                    pass

# 全局转码服务实例
transcoding_service = TranscodingService() 