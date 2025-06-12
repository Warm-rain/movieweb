"""
GPU硬解实时转码服务
"""

import os
import subprocess
import threading
import time
import hashlib
import json
import logging
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('transcoding')

# 转码配置
TRANSCODING_CONFIG = {
    # 输出分辨率和码率
    'resolutions': {
        '2160p': {'width': 3840, 'height': 2160, 'bitrate': '15M', 'maxrate': '18M'},
        '1440p': {'width': 2560, 'height': 1440, 'bitrate': '10M', 'maxrate': '12M'},
        '1080p': {'width': 1920, 'height': 1080, 'bitrate': '5M', 'maxrate': '6M'},
        '720p': {'width': 1280, 'height': 720, 'bitrate': '3M', 'maxrate': '3.5M'},
        '480p': {'width': 854, 'height': 480, 'bitrate': '1.5M', 'maxrate': '2M'},
        '360p': {'width': 640, 'height': 360, 'bitrate': '800k', 'maxrate': '1M'},
        '240p': {'width': 426, 'height': 240, 'bitrate': '400k', 'maxrate': '500k'},  # 新增
        '144p': {'width': 256, 'height': 144, 'bitrate': '200k', 'maxrate': '300k'},  # 新增
    },
    
    # 编码器配置
    'encoders': {
        'nvidia': {
            'h264': 'h264_nvenc',
            'hevc': 'hevc_nvenc',
            'options': '-preset p4 -tune ll -rc cbr -profile:v high'
        },
        'intel': {
            'h264': 'h264_qsv',
            'hevc': 'hevc_qsv',
            'options': '-preset faster -global_quality 23'
        },
        'amd': {
            'h264': 'h264_amf',
            'hevc': 'hevc_amf',
            'options': '-quality balanced -rc cbr'
        },
        'software': {
            'h264': 'libx264',
            'hevc': 'libx265',
            'options': '-preset faster -crf 23'
        }
    },
    
    # HLS参数
    'hls': {
        'segment_time': 6,  # 片段时长(秒)
        'playlist_type': 'event',
        'hls_time': 6,
        'hls_list_size': 0,
        'hls_segment_type': 'mpegts',
        'hls_flags': 'independent_segments'
    },
    
    # 实时转码参数
    'realtime': {
        'enabled': True,
        'buffer_size': '2M',        # 减小缓冲区提高响应速度
        'max_delay': '200000',      # 200ms最大延迟，更低的延迟
        'segment_time': 1,          # 1秒片段，更快的响应时间
        'zerolatency': True,        # 零延迟模式
        'tune': 'zerolatency',      # 低延迟调优
        'nvidia_options': '-preset fast -rc vbr -cq 23', # RTX 3070兼容性优化
        'keyint_min': 15,           # 最小关键帧间隔
        'gpu_index': '0',           # 使用RTX 3070 (GPU 0)
        'gpu_thread_count': 2,      # 最佳GPU线程数
        'preferred_encoder': 'nvidia', # 优先使用NVIDIA
    }
}

# 转码缓存目录
TRANSCODED_DIR = os.path.join(settings.MEDIA_ROOT, 'transcoded')
os.makedirs(TRANSCODED_DIR, exist_ok=True)

# 实时转码会话存储
REALTIME_SESSIONS = {}

class TranscodingService:
    """
    视频转码服务
    - 支持GPU硬件加速(NVIDIA, Intel, AMD)
    - 支持多分辨率输出
    - 支持HLS流媒体
    - 支持缓存和按需转码
    - 新增实时转码功能，无需缓存文件
    """
    
    @staticmethod
    def detect_gpu_encoders():
        """检测系统支持的GPU硬件编码器"""
        encoders = []
        
        try:
            # 检查FFmpeg版本和可用编码器
            ffmpeg_cmd = ['ffmpeg', '-encoders']
            result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = result.stdout
            
            # 检测NVIDIA
            if 'h264_nvenc' in output:
                encoders.append('nvidia')
                logger.info("检测到NVIDIA硬件编码器")
            
            # 检测Intel QSV
            if 'h264_qsv' in output:
                encoders.append('intel')
                logger.info("检测到Intel Quick Sync硬件编码器")
            
            # 检测AMD
            if 'h264_amf' in output:
                encoders.append('amd')
                logger.info("检测到AMD硬件编码器")
                
            # 始终添加软件编码器作为备选
            encoders.append('software')
            logger.info("添加软件编码器作为备选")
            
        except Exception as e:
            logger.error(f"检测GPU编码器时出错: {str(e)}")
            encoders.append('software')  # 出错时默认使用软件编码
        
        return encoders
    
    @staticmethod
    def get_best_encoder(codec='h264'):
        """获取最佳的可用编码器"""
        available_encoders = TranscodingService.detect_gpu_encoders()
        encoders_config = TRANSCODING_CONFIG['encoders']
        
        for encoder_type in available_encoders:
            if encoder_type in encoders_config and codec in encoders_config[encoder_type]:
                return {
                    'type': encoder_type,
                    'name': encoders_config[encoder_type][codec],
                    'options': encoders_config[encoder_type]['options']
                }
        
        # 默认返回软件编码器
        return {
            'type': 'software',
            'name': encoders_config['software'][codec],
            'options': encoders_config['software']['options']
        }
    
    @staticmethod
    def get_video_info(video_path):
        """获取视频文件信息"""
        try:
            cmd = [
                'ffprobe', 
                '-v', 'error', 
                '-select_streams', 'v:0', 
                '-show_entries', 'stream=width,height,codec_name,duration', 
                '-show_entries', 'format=duration', 
                '-of', 'json', 
                video_path
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            info = json.loads(result.stdout)
            
            stream_info = info.get('streams', [{}])[0]
            format_info = info.get('format', {})
            
            return {
                'width': int(stream_info.get('width', 0)),
                'height': int(stream_info.get('height', 0)),
                'codec': stream_info.get('codec_name', 'unknown'),
                'duration': float(stream_info.get('duration') or format_info.get('duration', 0)),
            }
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            return None
    
    @staticmethod
    def get_available_resolutions(video_path):
        """根据原始视频确定可用的转码分辨率"""
        video_info = TranscodingService.get_video_info(video_path)
        if not video_info:
            return []
        
        original_height = video_info['height']
        available_resolutions = []
        
        # 不超过原始分辨率
        for res_name, res_info in TRANSCODING_CONFIG['resolutions'].items():
            if res_info['height'] <= original_height:
                available_resolutions.append(res_name)
        
        logger.info(f"原始视频分辨率: {video_info['width']}x{original_height}, 可用分辨率: {available_resolutions}")
        return available_resolutions
    
    @staticmethod
    def start_cached_transcoding(video_path, resolution):
        """开始转码任务，转码完成后保存到缓存目录"""
        try:
            # 检查分辨率是否有效
            if resolution not in TRANSCODING_CONFIG['resolutions']:
                return {'success': False, 'error': f"不支持的分辨率: {resolution}"}
            
            # 创建唯一的转码ID和输出目录
            transcode_id = str(uuid.uuid4())
            output_dir = os.path.join(TRANSCODED_DIR, transcode_id)
            os.makedirs(output_dir, exist_ok=True)
            
            # 获取分辨率配置
            res_config = TRANSCODING_CONFIG['resolutions'][resolution]
            width, height = res_config['width'], res_config['height']
            bitrate = res_config['bitrate']
            maxrate = res_config['maxrate']
            
            # 获取最佳编码器
            encoder = TranscodingService.get_best_encoder()
            encoder_name = encoder['name']
            encoder_options = encoder['options']
            
            # HLS参数
            hls_config = TRANSCODING_CONFIG['hls']
            segment_time = hls_config['segment_time']
            
            # 输出文件路径
            output_path = os.path.join(output_dir, f"{resolution}.m3u8")
            
            # 构建FFmpeg命令
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # 覆盖输出文件
                '-i', video_path,  # 输入文件
                '-c:v', encoder_name,  # 视频编码器
                *encoder_options.split(),  # 编码器选项
                '-b:v', bitrate,  # 视频码率
                '-maxrate', maxrate,  # 最大码率
                '-bufsize', f"{int(bitrate[:-1]) * 2}M",  # 缓冲区大小
                '-vf', f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",  # 缩放并保持宽高比
                '-c:a', 'aac',  # 音频编码器
                '-b:a', '128k',  # 音频码率
                '-ac', '2',  # 双声道
                '-ar', '44100',  # 采样率
                '-f', 'hls',  # 输出格式
                '-hls_time', str(segment_time),  # 片段时长
                '-hls_playlist_type', hls_config['playlist_type'],  # 播放列表类型
                '-hls_list_size', str(hls_config['hls_list_size']),  # 列表大小(0表示全部保留)
                '-hls_segment_type', hls_config['hls_segment_type'],  # 片段类型
                '-hls_flags', hls_config['hls_flags'],  # HLS标志
                output_path  # 输出文件
            ]
            
            # 启动转码进程
            process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            # 在后台线程中监控进程
            def monitor_process():
                process.wait()
                return_code = process.poll()
                
                if return_code == 0:
                    logger.info(f"转码成功完成: {resolution}, ID: {transcode_id}")
                    # 添加完成标记文件
                    with open(os.path.join(output_dir, 'completed'), 'w') as f:
                        f.write(str(int(time.time())))
                else:
                    error_output = process.stderr.read()
                    logger.error(f"转码失败: {resolution}, ID: {transcode_id}, 错误: {error_output}")
                    # 添加失败标记文件
                    with open(os.path.join(output_dir, 'failed'), 'w') as f:
                        f.write(error_output)
            
            threading.Thread(target=monitor_process, daemon=True).start()
            
            return {
                'success': True, 
                'transcode_id': transcode_id,
                'status': 'started',
                'resolution': resolution,
                'encoder': encoder['type']
            }
        
        except Exception as e:
            logger.error(f"启动转码任务失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_transcoding_status(transcode_id):
        """获取转码任务状态"""
        output_dir = os.path.join(TRANSCODED_DIR, transcode_id)
        
        if not os.path.exists(output_dir):
            return {'success': False, 'error': f"转码任务不存在: {transcode_id}"}
        
        # 检查状态标记文件
        if os.path.exists(os.path.join(output_dir, 'completed')):
            return {'success': True, 'status': 'completed'}
        
        if os.path.exists(os.path.join(output_dir, 'failed')):
            with open(os.path.join(output_dir, 'failed'), 'r') as f:
                error = f.read()
            return {'success': False, 'status': 'failed', 'error': error}
        
        # 检查m3u8文件和分片情况
        m3u8_files = [f for f in os.listdir(output_dir) if f.endswith('.m3u8')]
        if m3u8_files:
            return {'success': True, 'status': 'transcoding', 'progress': 'unknown'}
        
        return {'success': True, 'status': 'pending'}
    
    @staticmethod
    def get_hls_content(transcode_id, resolution):
        """获取HLS播放列表内容"""
        output_dir = os.path.join(TRANSCODED_DIR, transcode_id)
        m3u8_path = os.path.join(output_dir, f"{resolution}.m3u8")
        
        if not os.path.exists(m3u8_path):
            return {'success': False, 'error': f"HLS播放列表不存在: {resolution}"}
        
        try:
            with open(m3u8_path, 'r') as f:
                content = f.read()
            return {'success': True, 'content': content}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def cleanup_old_transcodes(max_age_hours=24):
        """清理旧的转码文件"""
        try:
            count = 0
            total_size = 0
            
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            for item in os.listdir(TRANSCODED_DIR):
                item_path = os.path.join(TRANSCODED_DIR, item)
                
                # 跳过文件和实时转码会话
                if not os.path.isdir(item_path) or item in REALTIME_SESSIONS:
                    continue
                
                # 检查目录修改时间
                mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                
                if mtime < cutoff_time:
                    # 计算目录大小
                    dir_size = sum(os.path.getsize(os.path.join(root, file)) 
                                  for root, _, files in os.walk(item_path) 
                                  for file in files)
                    
                    # 删除目录
                    shutil.rmtree(item_path)
                    
                    count += 1
                    total_size += dir_size
                    logger.info(f"已删除旧转码: {item}, 大小: {dir_size/1024/1024:.2f}MB")
            
            return {
                'success': True, 
                'count': count, 
                'total_size_mb': total_size/1024/1024,
                'cutoff_time': cutoff_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"清理旧转码失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def start_realtime_transcoding(video_path, resolution, session_id=None):
        """开始实时转码流会话 - 针对RTX 3070优化"""
        try:
            # 如果未提供会话ID，创建新的唯一ID
            if not session_id:
                session_id = str(uuid.uuid4())
            
            # 检查分辨率是否有效
            if resolution not in TRANSCODING_CONFIG['resolutions']:
                return {'success': False, 'error': f"不支持的分辨率: {resolution}"}
            
            # 创建输出目录
            output_dir = os.path.join(TRANSCODED_DIR, f"realtime_{session_id}")
            os.makedirs(output_dir, exist_ok=True)
            
            # 获取分辨率配置
            res_config = TRANSCODING_CONFIG['resolutions'][resolution]
            width, height = res_config['width'], res_config['height']
            bitrate = res_config['bitrate']
            maxrate = res_config['maxrate']
            
            # 获取最佳编码器 - 优先尝试使用NVIDIA
            realtime_config = TRANSCODING_CONFIG['realtime']
            preferred_encoder = realtime_config.get('preferred_encoder', None)
            
            if preferred_encoder == 'nvidia':
                # 直接尝试使用NVIDIA编码器
                encoder_config = TRANSCODING_CONFIG['encoders'].get('nvidia', None)
                if encoder_config and 'h264_nvenc' in subprocess.run(['ffmpeg', '-encoders'], 
                                            stdout=subprocess.PIPE, text=True).stdout:
                    encoder = {
                        'type': 'nvidia',
                        'name': encoder_config['h264'],
                        'options': realtime_config.get('nvidia_options', encoder_config['options'])
                    }
                    logger.info("使用NVIDIA RTX编码器进行实时转码")
                else:
                    # 如果无法使用NVIDIA，回退到常规选择
                    encoder = TranscodingService.get_best_encoder()
            else:
                encoder = TranscodingService.get_best_encoder()
            
            encoder_name = encoder['name']
            
            # 实时转码参数
            segment_time = realtime_config['segment_time']
            keyint_min = realtime_config.get('keyint_min', 15)
            
            # 输出HLS文件路径 - 使用绝对路径
            output_path = os.path.abspath(os.path.join(output_dir, f"{resolution}.m3u8"))
            
            # 极简FFmpeg命令 - 使用完整路径避免Python库冲突
            import shutil
            ffmpeg_path = shutil.which('ffmpeg') or 'ffmpeg'
            logger.info(f"🔍 使用FFmpeg路径: {ffmpeg_path}")
            
            ffmpeg_cmd = [
                ffmpeg_path,  # 使用完整路径
                '-y',  # 覆盖输出文件
                '-i', video_path,  # 输入文件
                '-c:v', encoder_name,  # 视频编码器
            ]
            
            # 为NVIDIA编码器添加最基础参数
            if encoder['type'] == 'nvidia':
                ffmpeg_cmd.extend([
                    '-preset', 'fast',   # 使用fast预设
                    '-gpu', '0',         # 指定GPU 0 (RTX 3070)
                ])
            
            # 极简实时转码参数 - 立即生效
            ffmpeg_cmd.extend([
                '-vf', f"scale={width}:{height}",  # 简化缩放
                '-c:a', 'aac',  # 音频编码器
                '-f', 'hls',  # 输出格式
                '-hls_time', '2',  # 2秒片段，极快生成
                '-hls_list_size', '3',  # 只保留3个片段（6秒内容）
                '-hls_flags', 'append_list',  # 简化标志
                '-t', '30',  # 🔥 极短时间：只转码前10秒，立即生效
            ])
            
            # 删除不兼容的GPU线程配置参数
            
            # 输出文件路径
            ffmpeg_cmd.append(output_path)
            
            logger.info(f"实时转码命令: {' '.join(ffmpeg_cmd)}")
            
            # 确保输出目录存在
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"📁 创建输出目录: {output_dir}")
            
            # 使用同步方式启动转码进程 - 修复异步问题
            logger.info("🚀 启动FFmpeg快速转码（前10秒）...")
            try:
                # 🔥 回到同步方式，确保能工作
                start_time = time.time()
                
                # 确保输出目录存在
                os.makedirs(output_dir, exist_ok=True)
                
                logger.info(f"🔍 执行转码命令...")
                logger.info(f"🔍 输出目录: {output_dir}")
                
                # 使用同步方式，但时间很短（10秒）
                result = subprocess.run(
                    ffmpeg_cmd, 
                    stdin=subprocess.DEVNULL,  # 防止等待输入
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True,
                    encoding='utf-8',
                    errors='replace',  # 替换无法解码的字符
                    timeout=60,  # 30秒超时，足够转码10秒内容
                )
                
                duration = time.time() - start_time
                logger.info(f"✅ FFmpeg转码完成，返回码: {result.returncode}, 耗时: {duration:.1f}秒")
                
                if result.stderr:
                    logger.info(f"📄 FFmpeg输出: {result.stderr[:300]}")
                
                if result.returncode != 0:
                    logger.error(f"❌ FFmpeg转码失败，返回码: {result.returncode}")
                    return {'success': False, 'error': f'FFmpeg转码失败，返回码: {result.returncode}'}
                
                # 检查输出文件
                if not os.path.exists(output_path):
                    logger.error(f"❌ HLS文件未生成: {output_path}")
                    return {'success': False, 'error': 'HLS文件未生成'}
                
                # 检查片段文件
                files_in_dir = os.listdir(output_dir) if os.path.exists(output_dir) else []
                segment_files = [f for f in files_in_dir if f.endswith('.ts')]
                
                if not segment_files:
                    logger.error(f"❌ 没有生成HLS片段文件")
                    return {'success': False, 'error': '没有生成HLS片段文件'}
                
                logger.info(f"✅ HLS转码成功，生成片段: {segment_files}")
                
                # 创建假进程对象用于会话管理（因为真实进程已经结束）
                class FakeProcess:
                    def __init__(self):
                        self.pid = None
                        self.returncode = 0
                    
                    def poll(self):
                        return 0  # 总是返回已完成
                    
                    def terminate(self):
                        pass
                    
                    def wait(self, timeout=None):
                        pass
                
                # 存储会话信息
                REALTIME_SESSIONS[session_id] = {
                    'process': FakeProcess(),  # 假进程对象，因为转码已完成
                    'video_path': video_path,
                    'resolution': resolution,
                    'output_dir': output_dir,
                    'start_time': start_time,
                    'encoder': encoder['type'],
                    'last_access': time.time(),
                    'command': ' '.join(ffmpeg_cmd),
                    'completed': True,  # 标记为已完成
                    'streaming': False,   # 不是流式模式，是快速完整转码
                }
                
                logger.info(f"✅ 快速转码会话完成: {session_id}, 分辨率: {resolution}, 编码器: {encoder['type']}")
                
            except subprocess.TimeoutExpired:
                logger.error(f"❌ FFmpeg转码超时")
                return {'success': False, 'error': 'FFmpeg转码超时'}
            except Exception as e:
                logger.error(f"❌ 启动FFmpeg转码失败: {str(e)}")
                return {'success': False, 'error': f'启动FFmpeg转码失败: {str(e)}'}
            
            logger.info(f"🎉 快速转码成功: {session_id}, 分辨率: {resolution}")
            return {
                'success': True,
                'session_id': session_id,
                'status': 'completed',  # 已完成状态
                'resolution': resolution,
                'encoder': encoder['type'],
                'realtime': True,
                'streaming': False,  # 非流式模式，已完成
                'rtx_optimized': encoder['type'] == 'nvidia'
            }
            
        except Exception as e:
            logger.error(f"启动实时转码失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def stop_realtime_session(session_id):
        """停止实时转码会话"""
        if session_id not in REALTIME_SESSIONS:
            return {'success': False, 'error': f"实时转码会话不存在: {session_id}"}
        
        try:
            session = REALTIME_SESSIONS[session_id]
            
            # 关闭FFmpeg进程
            if session['process'].poll() is None:  # 如果进程还在运行
                session['process'].terminate()
                session['process'].wait(timeout=5)
            
            # 删除输出目录
            if os.path.exists(session['output_dir']):
                shutil.rmtree(session['output_dir'])
            
            # 从会话字典中移除
            del REALTIME_SESSIONS[session_id]
            
            logger.info(f"已停止实时转码会话: {session_id}")
            return {'success': True}
        
        except Exception as e:
            logger.error(f"停止实时转码会话失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_realtime_session(session_id):
        """获取实时转码会话信息"""
        if session_id not in REALTIME_SESSIONS:
            return {'success': False, 'error': f"实时转码会话不存在: {session_id}"}
        
        session = REALTIME_SESSIONS[session_id]
        
        # 更新最后访问时间
        session['last_access'] = time.time()
        
        # 检查进程是否还在运行
        is_active = session['process'].poll() is None
        
        return {
            'success': True,
            'session_id': session_id,
            'status': 'active' if is_active else 'stopped',
            'resolution': session['resolution'],
            'encoder': session['encoder'],
            'start_time': session['start_time'],
            'duration': time.time() - session['start_time'],
            'last_access': session['last_access'],
            'realtime': True
        }
    
    @staticmethod
    def get_realtime_hls_content(session_id, resolution):
        """获取实时HLS播放列表内容"""
        if session_id not in REALTIME_SESSIONS:
            return {'success': False, 'error': f"实时转码会话不存在: {session_id}"}
        
        session = REALTIME_SESSIONS[session_id]
        
        # 更新最后访问时间
        session['last_access'] = time.time()
        
        # 检查分辨率是否匹配
        if session['resolution'] != resolution:
            return {'success': False, 'error': f"会话分辨率不匹配: {session['resolution']} != {resolution}"}
        
        m3u8_path = os.path.join(session['output_dir'], f"{resolution}.m3u8")
        
        if not os.path.exists(m3u8_path):
            return {'success': False, 'error': f"HLS播放列表不存在: {resolution}"}
        
        try:
            with open(m3u8_path, 'r') as f:
                content = f.read()
            return {'success': True, 'content': content, 'realtime': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def cleanup_inactive_sessions(inactive_minutes=30):
        """清理不活跃的实时转码会话"""
        try:
            count = 0
            now = time.time()
            inactive_cutoff = now - (inactive_minutes * 60)
            
            sessions_to_stop = []
            
            for session_id, session in REALTIME_SESSIONS.items():
                if session['last_access'] < inactive_cutoff:
                    sessions_to_stop.append(session_id)
            
            for session_id in sessions_to_stop:
                TranscodingService.stop_realtime_session(session_id)
                count += 1
            
            return {'success': True, 'stopped_count': count}
        
        except Exception as e:
            logger.error(f"清理不活跃会话失败: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def start_background_continuation(session_id, video_path, resolution, output_dir):
        """在后台继续转码剩余部分"""
        try:
            import threading
            
            def continue_transcoding():
                try:
                    # 等待一段时间，让用户开始播放
                    time.sleep(20)
                    
                    # 检查会话是否还存在
                    if session_id not in REALTIME_SESSIONS:
                        logger.info(f"会话{session_id}已结束，取消后台转码")
                        return
                    
                    session = REALTIME_SESSIONS[session_id]
                    
                    # 检查用户是否还在观看（最近3分钟内有访问）
                    if time.time() - session['last_access'] > 180:
                        logger.info(f"用户长时间未访问会话{session_id}，停止后台转码")
                        return
                    
                    logger.info(f"🔄 开始后台转码剩余内容: {session_id}")
                    
                    # 获取编码器信息
                    encoder = TranscodingService.get_best_encoder('h264')
                    gpu_index = 0 if encoder['type'] == 'nvidia' else None
                    
                    # 获取分辨率配置
                    resolution_configs = {
                        '2160p': (3840, 2160), '1440p': (2560, 1440),
                        '1080p': (1920, 1080), '720p': (1280, 720),
                        '480p': (854, 480), '360p': (640, 360),
                        '240p': (426, 240), '144p': (256, 144)
                    }
                    
                    if resolution not in resolution_configs:
                        logger.error(f"未知分辨率: {resolution}")
                        return
                    
                    width, height = resolution_configs[resolution]
                    
                    # 完整转码命令 - 转码整个视频
                    ffmpeg_path = shutil.which('ffmpeg') or 'C:\\Windows\\system32\\ffmpeg.EXE'
                    
                    full_output_path = os.path.join(output_dir, f"{resolution}_full.m3u8")
                    
                    ffmpeg_cmd = [ffmpeg_path, '-y', '-i', video_path]
                    
                    # 添加编码器参数
                    if encoder['type'] == 'nvidia':
                        ffmpeg_cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'fast'])
                        if gpu_index is not None:
                            ffmpeg_cmd.extend(['-gpu', str(gpu_index)])
                    else:
                        ffmpeg_cmd.extend(['-c:v', 'libx264', '-preset', 'fast'])
                    
                    # 完整转码参数
                    ffmpeg_cmd.extend([
                        '-vf', f"scale={width}:{height}",
                        '-c:a', 'aac',
                        '-f', 'hls',
                        '-hls_time', '6',  # 标准6秒片段
                        '-hls_list_size', '0',  # 保留所有片段
                        '-hls_flags', 'append_list',
                        '-hls_segment_filename', os.path.join(output_dir, f"{resolution}_full_%03d.ts"),
                        full_output_path
                    ])
                    
                    logger.info(f"🎬 后台开始完整转码: {resolution}")
                    
                    # 执行完整转码
                    result = subprocess.run(
                        ffmpeg_cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=3600,  # 1小时超时
                    )
                    
                    if result.returncode == 0:
                        logger.info(f"✅ 后台完整转码成功: {resolution}")
                        # 更新会话状态
                        if session_id in REALTIME_SESSIONS:
                            REALTIME_SESSIONS[session_id]['completed'] = True
                            REALTIME_SESSIONS[session_id]['full_file'] = full_output_path
                    else:
                        logger.error(f"❌ 后台完整转码失败: {resolution}")
                        
                except Exception as e:
                    logger.error(f"后台转码异常: {str(e)}")
            
            # 启动后台线程
            thread = threading.Thread(target=continue_transcoding, daemon=True)
            thread.start()
            
        except Exception as e:
            logger.error(f"启动后台转码失败: {str(e)}")
    
    @staticmethod
    def get_active_sessions():
        """获取所有活跃的实时转码会话"""
        active_sessions = []
        
        for session_id, session in REALTIME_SESSIONS.items():
            is_active = session['process'].poll() is None
            
            if is_active:
                active_sessions.append({
                    'session_id': session_id,
                    'resolution': session['resolution'],
                    'encoder': session['encoder'],
                    'start_time': session['start_time'],
                    'duration': time.time() - session['start_time'],
                    'last_access': session['last_access'],
                })
        
        return {'success': True, 'sessions': active_sessions}

# 启动清理任务线程
def start_cleanup_thread():
    """启动后台清理线程"""
    def cleanup_task():
        while True:
            try:
                # 每小时清理一次旧的转码缓存
                TranscodingService.cleanup_old_transcodes(max_age_hours=24)
                
                # 每10分钟清理一次不活跃的实时会话
                TranscodingService.cleanup_inactive_sessions(inactive_minutes=30)
                
            except Exception as e:
                logger.error(f"清理任务失败: {str(e)}")
            
            # 每10分钟运行一次
            time.sleep(10 * 60)
    
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    logger.info("已启动自动清理线程")

# 延迟启动清理线程，避免在模块导入时启动
# start_cleanup_thread() 