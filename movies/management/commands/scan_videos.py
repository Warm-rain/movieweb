import os
import json
import tempfile
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from movies.models import Movie, Series
from movies.scraper import VideoScraper
import ffmpeg
import requests


class Command(BaseCommand):
    help = '扫描指定目录下的视频文件并添加到数据库，支持刮削封面和剧集分组'

    def add_arguments(self, parser):
        parser.add_argument('directory', type=str, help='要扫描的目录路径')
        parser.add_argument(
            '--scrape',
            action='store_true',
            help='启用刮削功能获取封面和信息',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='覆盖已存在的电影记录',
        )

    def handle(self, *args, **options):
        directory = options['directory']
        enable_scraping = options['scrape']
        overwrite = options['overwrite']
        
        if not os.path.exists(directory):
            self.stdout.write(self.style.ERROR(f'目录不存在: {directory}'))
            return

        self.stdout.write(f'开始扫描目录: {directory}')
        if enable_scraping:
            self.stdout.write('已启用刮削功能')
        
        # 初始化刮削器
        scraper = VideoScraper() if enable_scraping else None
        
        # 支持的视频格式
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
        
        added_count = 0
        updated_count = 0
        error_count = 0
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext in video_extensions:
                    try:
                        result = self.process_video_file(
                            file_path, scraper, overwrite, enable_scraping
                        )
                        if result == 'added':
                            added_count += 1
                        elif result == 'updated':
                            updated_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'处理文件出错 {file_path}: {str(e)}')
                        )
                        error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'扫描完成! 新增: {added_count}, 更新: {updated_count}, 错误: {error_count}'
            )
        )

    def process_video_file(self, file_path, scraper, overwrite, enable_scraping):
        """处理单个视频文件"""
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # 检查是否已存在
        existing_movie = Movie.objects.filter(file_path=file_path).first()
        if existing_movie and not overwrite:
            self.stdout.write(f'跳过已存在的文件: {filename}')
            return 'skipped'
        
        # 获取视频信息
        try:
            probe = ffmpeg.probe(file_path)
            video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            duration_seconds = float(probe['format']['duration'])
            duration = timedelta(seconds=duration_seconds)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'无法获取视频信息 {filename}: {e}'))
            duration = None
        
        # 初始化电影数据
        movie_data = {
            'title': os.path.splitext(filename)[0],
            'file_path': file_path,
            'file_size': file_size,
            'duration': duration,
        }
        
        series = None
        scrape_result = None
        
        # 如果启用刮削功能
        if enable_scraping and scraper:
            self.stdout.write(f'正在刮削: {filename}')
            scrape_result = scraper.scrape_video_info(file_path)
            
            if scrape_result['success']:
                self.stdout.write(self.style.SUCCESS(f'✓ {scrape_result["message"]}'))
                
                if scrape_result['is_series']:
                    # 处理电视剧
                    series = scrape_result['series']
                    series_info = scrape_result['series_info']
                    
                    movie_data.update({
                        'series': series,
                        'episode_number': series_info['episode_number'],
                        'season_number': series_info['season_number'],
                        'title': series_info.get('episode_title') or movie_data['title'],
                    })
                    
                    # 从剧集信息更新
                    if scrape_result['movie_data']:
                        tv_details = scrape_result['movie_data']
                        movie_data.update({
                            'description': tv_details.get('overview', ''),
                            'genre': ', '.join([genre['name'] for genre in tv_details.get('genres', [])]),
                            'year': int(tv_details.get('first_air_date', '1900-01-01')[:4]) if tv_details.get('first_air_date') else None,
                            'rating': tv_details.get('vote_average', 0),
                            'tmdb_id': tv_details.get('id'),
                        })
                else:
                    # 处理电影
                    if scrape_result['movie_data']:
                        movie_details = scrape_result['movie_data']
                        movie_data.update({
                            'title': movie_details.get('title', movie_data['title']),
                            'original_title': movie_details.get('original_title', ''),
                            'description': movie_details.get('overview', ''),
                            'genre': ', '.join([genre['name'] for genre in movie_details.get('genres', [])]),
                            'year': int(movie_details.get('release_date', '1900-01-01')[:4]) if movie_details.get('release_date') else None,
                            'rating': movie_details.get('vote_average', 0),
                            'tmdb_id': movie_details.get('id'),
                            'poster_url': scraper.get_image_url(movie_details.get('poster_path', '')),
                        })
            else:
                self.stdout.write(self.style.WARNING(f'✗ {scrape_result["message"]}'))
        
        # 创建或更新电影记录
        if existing_movie:
            for key, value in movie_data.items():
                setattr(existing_movie, key, value)
            movie = existing_movie
            movie.save()
            action = 'updated'
        else:
            movie = Movie.objects.create(**movie_data)
            action = 'added'
        
        # 生成缩略图
        self.generate_thumbnail(movie, scrape_result)
        
        self.stdout.write(f'{"更新" if action == "updated" else "添加"}: {movie.title}')
        return action

    def generate_thumbnail(self, movie, scrape_result=None):
        """生成或下载缩略图"""
        try:
            # 如果有刮削结果且是电影，尝试下载海报
            if (scrape_result and not scrape_result['is_series'] and 
                scrape_result.get('movie_data') and movie.poster_url):
                
                response = requests.get(movie.poster_url, timeout=30)
                if response.status_code == 200:
                    poster_file = ContentFile(response.content)
                    movie.poster_image.save(
                        f"movie_{movie.id}_poster.jpg",
                        poster_file,
                        save=True
                    )
                    self.stdout.write(f'✓ 下载海报: {movie.title}')
                    return
            
            # 如果是剧集且有系列海报，跳过缩略图生成
            if movie.series and movie.series.poster_image:
                self.stdout.write(f'✓ 使用剧集海报: {movie.title}')
                return
            
            # 生成FFmpeg缩略图作为备用
            self.generate_ffmpeg_thumbnail(movie)
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'缩略图处理失败 {movie.title}: {e}')
            )

    def generate_ffmpeg_thumbnail(self, movie):
        """使用FFmpeg生成缩略图"""
        try:
            # 使用临时文件避免路径问题
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # 尝试在30秒处截取
                (
                    ffmpeg
                    .input(movie.file_path, ss=30)
                    .output(temp_path, vframes=1, format='image2', vcodec='mjpeg')
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error:
                try:
                    # 如果30秒失败，尝试10秒处截取
                    (
                        ffmpeg
                        .input(movie.file_path, ss=10)
                        .output(temp_path, vframes=1, format='image2', vcodec='mjpeg')
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                except ffmpeg.Error:
                    # 最后尝试在开始处截取
                    (
                        ffmpeg
                        .input(movie.file_path, ss=1)
                        .output(temp_path, vframes=1, format='image2', vcodec='mjpeg')
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
            
            # 检查文件是否生成成功
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, 'rb') as f:
                    thumbnail_file = ContentFile(f.read())
                    movie.thumbnail.save(
                        f"thumb_{movie.id}.jpg",
                        thumbnail_file,
                        save=True
                    )
                self.stdout.write(f'✓ 生成缩略图: {movie.title}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'缩略图文件生成失败: {movie.title}')
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'FFmpeg缩略图生成失败 {movie.title}: {e}')
            )
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path) 