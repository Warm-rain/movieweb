import os
import subprocess
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.files.base import ContentFile
from movies.models import Movie


class Command(BaseCommand):
    help = 'Scan directory for video files and add them to database'

    def add_arguments(self, parser):
        parser.add_argument(
            'directory',
            nargs='?',
            type=str,
            default=settings.VIDEO_ROOT_PATH,
            help='Directory to scan for video files'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing movies metadata',
        )
        parser.add_argument(
            '--generate-thumbnails',
            action='store_true',
            help='Generate thumbnails for videos using ffmpeg',
        )

    def handle(self, *args, **options):
        directory = options['directory']
        update_existing = options['update']
        generate_thumbnails = options['generate_thumbnails']

        if not os.path.exists(directory):
            raise CommandError(f'Directory "{directory}" does not exist.')

        self.stdout.write(f'Scanning directory: {directory}')
        
        # 检查ffmpeg是否可用
        ffmpeg_available = self.check_ffmpeg() if generate_thumbnails else False
        if generate_thumbnails and not ffmpeg_available:
            self.stdout.write(
                self.style.WARNING('FFmpeg not found. Thumbnails will not be generated.')
            )
        elif generate_thumbnails and ffmpeg_available:
            self.stdout.write(
                self.style.SUCCESS('FFmpeg found. Thumbnails will be generated.')
            )

        added_count = 0
        updated_count = 0
        error_count = 0

        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext in settings.VIDEO_EXTENSIONS:
                    try:
                        result = self.process_video_file(
                            file_path, 
                            update_existing, 
                            generate_thumbnails and ffmpeg_available
                        )
                        if result == 'added':
                            added_count += 1
                        elif result == 'updated':
                            updated_count += 1
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(f'Error processing {file_path}: {str(e)}')
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Scan completed. Added: {added_count}, Updated: {updated_count}, Errors: {error_count}'
            )
        )

    def check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def process_video_file(self, file_path, update_existing, generate_thumbnails):
        """处理单个视频文件"""
        file_name = os.path.basename(file_path)
        title = os.path.splitext(file_name)[0]
        file_size = os.path.getsize(file_path)

        # 检查是否已存在
        movie, created = Movie.objects.get_or_create(
            file_path=file_path,
            defaults={
                'title': title,
                'file_size': file_size,
            }
        )

        if created:
            self.stdout.write(f'Added: {file_name}')
            result = 'added'
        elif update_existing:
            movie.title = title
            movie.file_size = file_size
            movie.save()
            self.stdout.write(f'Updated: {file_name}')
            result = 'updated'
        else:
            # 即使不更新，也检查是否需要生成缩略图
            if generate_thumbnails and not movie.thumbnail:
                self.generate_thumbnail(movie)
                result = 'thumbnail_generated'
            else:
                result = 'skipped'
                
        # 获取视频信息
        if created or update_existing:
            self.extract_video_info(movie)

        # 生成缩略图
        if generate_thumbnails and (created or update_existing or not movie.thumbnail):
            self.generate_thumbnail(movie)

        return result

    def extract_video_info(self, movie):
        """使用ffprobe提取视频信息"""
        try:
            # 获取视频时长
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', '-show_streams', movie.file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            data = json.loads(result.stdout)
            
            # 提取时长
            if 'format' in data and 'duration' in data['format']:
                duration_seconds = float(data['format']['duration'])
                movie.duration = timedelta(seconds=duration_seconds)
            
            # 尝试从文件名提取年份
            import re
            year_match = re.search(r'(19|20)\d{2}', movie.title)
            if year_match:
                movie.year = int(year_match.group())
            
            movie.save()
            
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # 如果ffprobe不可用，跳过
            pass

    def generate_thumbnail(self, movie):
        """生成视频缩略图"""
        try:
            # 使用临时文件
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                thumbnail_path = tmp_file.name
            
            # 使用ffmpeg生成缩略图（从视频30秒位置截取）
            cmd = [
                'ffmpeg', '-i', movie.file_path,
                '-ss', '00:00:30',  # 从30秒位置截取
                '-vframes', '1',
                '-f', 'image2',
                '-y',  # 覆盖输出文件
                thumbnail_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                # 将缩略图保存到模型
                with open(thumbnail_path, 'rb') as f:
                    thumbnail_name = f'{movie.pk}_thumb.jpg'
                    movie.thumbnail.save(thumbnail_name, ContentFile(f.read()), save=True)
                
                # 删除临时文件
                try:
                    os.unlink(thumbnail_path)
                except:
                    pass
                
                self.stdout.write(f'Generated thumbnail for: {movie.title}')
            else:
                # 如果30秒位置失败，尝试从10秒位置
                cmd[4] = '00:00:10'
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and os.path.exists(thumbnail_path):
                    with open(thumbnail_path, 'rb') as f:
                        thumbnail_name = f'{movie.pk}_thumb.jpg'
                        movie.thumbnail.save(thumbnail_name, ContentFile(f.read()), save=True)
                    
                    try:
                        os.unlink(thumbnail_path)
                    except:
                        pass
                    
                    self.stdout.write(f'Generated thumbnail for: {movie.title} (10s position)')
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Failed to generate thumbnail for: {movie.title}')
                    )
                    if result.stderr:
                        self.stdout.write(f'FFmpeg error: {result.stderr}')
                
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Failed to generate thumbnail for: {movie.title} - {str(e)}')
            ) 