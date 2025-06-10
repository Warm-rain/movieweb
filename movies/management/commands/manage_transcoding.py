"""
转码管理命令
"""

from django.core.management.base import BaseCommand
from movies.transcoding import transcoding_service
from movies.models import Movie
import os
from pathlib import Path

class Command(BaseCommand):
    help = 'GPU硬解转码管理工具'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['status', 'cleanup', 'test', 'benchmark'],
            help='执行的操作'
        )
        parser.add_argument(
            '--movie-id',
            type=int,
            help='指定视频ID进行测试'
        )
        parser.add_argument(
            '--resolution',
            default='720p',
            help='测试转码的分辨率 (默认: 720p)'
        )
        parser.add_argument(
            '--max-age',
            type=int,
            default=24,
            help='清理文件的最大年龄（小时，默认24）'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'status':
            self.show_status()
        elif action == 'cleanup':
            self.cleanup_transcodes(options['max_age'])
        elif action == 'test':
            self.test_transcoding(options.get('movie_id'), options['resolution'])
        elif action == 'benchmark':
            self.benchmark_performance()

    def show_status(self):
        """显示转码状态"""
        self.stdout.write(self.style.SUCCESS('🚀 GPU硬解转码状态'))
        self.stdout.write('=' * 60)
        
        # 检查FFmpeg和GPU支持
        h264_encoder = transcoding_service.get_best_encoder('h264')
        h265_encoder = transcoding_service.get_best_encoder('h265')
        
        self.stdout.write(f'🔧 H.264编码器: {h264_encoder}')
        self.stdout.write(f'🔧 H.265编码器: {h265_encoder}')
        
        # 检查转码文件
        transcode_dir = transcoding_service.transcode_dir
        if transcode_dir.exists():
            transcode_dirs = list(transcode_dir.glob('*'))
            total_size = 0
            
            for td in transcode_dirs:
                if td.is_dir():
                    size = sum(f.stat().st_size for f in td.glob('*') if f.is_file())
                    total_size += size
            
            self.stdout.write(f'📂 转码目录: {transcode_dir}')
            self.stdout.write(f'📦 缓存任务: {len(transcode_dirs)}个')
            self.stdout.write(f'💾 占用空间: {total_size / 1024 / 1024:.1f} MB')
        else:
            self.stdout.write('📂 转码目录不存在')
        
        # 检查活动任务
        active_jobs = len(transcoding_service.active_jobs)
        self.stdout.write(f'⚡ 活动转码: {active_jobs}个任务')
        
        # 检查视频数量
        total_movies = Movie.objects.count()
        self.stdout.write(f'🎬 视频总数: {total_movies}个')

    def cleanup_transcodes(self, max_age_hours):
        """清理转码文件"""
        self.stdout.write(self.style.WARNING(f'🗑️ 清理{max_age_hours}小时前的转码文件'))
        
        try:
            transcoding_service.cleanup_old_transcodes(max_age_hours)
            self.stdout.write(self.style.SUCCESS('✅ 清理完成'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ 清理失败: {e}'))

    def test_transcoding(self, movie_id, resolution):
        """测试转码功能"""
        self.stdout.write(self.style.SUCCESS(f'🧪 测试转码: {resolution}'))
        
        if movie_id:
            try:
                movie = Movie.objects.get(id=movie_id)
            except Movie.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ 视频ID {movie_id} 不存在'))
                return
        else:
            movie = Movie.objects.first()
            if not movie:
                self.stdout.write(self.style.ERROR('❌ 没有找到视频文件'))
                return
        
        self.stdout.write(f'📹 测试视频: {movie.title}')
        
        # 检查文件存在
        if not os.path.exists(movie.file_path):
            self.stdout.write(self.style.ERROR('❌ 视频文件不存在'))
            return
        
        # 获取视频信息
        video_info = transcoding_service.get_video_info(movie.file_path)
        if video_info:
            self.stdout.write(f'📊 分辨率: {video_info["width"]}x{video_info["height"]}')
            self.stdout.write(f'⏱️ 时长: {video_info["duration"]:.1f}秒')
            self.stdout.write(f'🎞️ 编码: {video_info["codec"]}')
        
        # 获取可用分辨率
        available = transcoding_service.get_available_resolutions(movie)
        self.stdout.write(f'🎯 可用分辨率: {available}')
        
        if resolution not in available:
            self.stdout.write(self.style.ERROR(f'❌ 分辨率 {resolution} 不可用'))
            return
        
        # 开始转码测试
        self.stdout.write(f'🚀 开始转码到 {resolution}...')
        transcode_id, status = transcoding_service.start_transcoding(movie, resolution)
        
        if transcode_id:
            self.stdout.write(self.style.SUCCESS(f'✅ 转码启动: {transcode_id}'))
            self.stdout.write(f'📦 状态: {status}')
            
            if status == 'completed':
                hls_path = transcoding_service.get_hls_path(movie.id, resolution)
                if hls_path.exists():
                    self.stdout.write(f'🎉 HLS文件: {hls_path}')
                    self.stdout.write(f'📦 大小: {hls_path.stat().st_size} bytes')
        else:
            self.stdout.write(self.style.ERROR(f'❌ 转码失败: {status}'))

    def benchmark_performance(self):
        """性能基准测试"""
        self.stdout.write(self.style.SUCCESS('⚡ GPU转码性能基准测试'))
        self.stdout.write('=' * 60)
        
        # 选择测试视频
        movies = Movie.objects.all()[:3]
        
        if not movies:
            self.stdout.write(self.style.ERROR('❌ 没有视频文件进行测试'))
            return
        
        for movie in movies:
            if not os.path.exists(movie.file_path):
                continue
                
            self.stdout.write(f'\n📹 测试: {movie.title}')
            
            video_info = transcoding_service.get_video_info(movie.file_path)
            if not video_info:
                continue
                
            duration = video_info['duration']
            resolution = f"{video_info['width']}x{video_info['height']}"
            
            self.stdout.write(f'   📊 原始: {resolution}, {duration:.1f}秒')
            
            # 估算转码时间（基于RTX 3070的5x实时速度）
            estimated_time = duration / 5
            self.stdout.write(f'   ⏱️ 预估转码时间: {estimated_time:.1f}秒')
            
            # 计算可能的文件大小
            original_bitrate = video_info.get('bitrate', 0)
            if original_bitrate > 0:
                # 720p目标码率3Mbps
                target_bitrate = 3 * 1024 * 1024  # 3Mbps
                estimated_size = (target_bitrate * duration) / 8 / 1024 / 1024  # MB
                self.stdout.write(f'   💾 预估720p大小: {estimated_size:.1f}MB')
            
            break  # 只测试第一个视频 