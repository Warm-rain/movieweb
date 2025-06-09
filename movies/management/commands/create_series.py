from django.core.management.base import BaseCommand
from movies.models import Movie, Series
from movies.scraper import VideoScraper
import re


class Command(BaseCommand):
    help = '手动创建剧集并关联电影文件'

    def add_arguments(self, parser):
        parser.add_argument('series_name', type=str, help='剧集名称')
        parser.add_argument('pattern', type=str, help='匹配文件名的模式')
        parser.add_argument(
            '--description',
            type=str,
            default='',
            help='剧集描述',
        )

    def handle(self, *args, **options):
        series_name = options['series_name']
        pattern = options['pattern']
        description = options['description']
        
        self.stdout.write(f'创建剧集: {series_name}')
        self.stdout.write(f'匹配模式: {pattern}')
        
        # 查找匹配的电影文件
        movies = Movie.objects.filter(
            title__icontains=pattern,
            series__isnull=True
        )
        
        if not movies.exists():
            self.stdout.write(self.style.ERROR(f'未找到匹配的电影文件: {pattern}'))
            return
        
        self.stdout.write(f'找到 {movies.count()} 个匹配的文件')
        
        # 创建剧集
        series, created = Series.objects.get_or_create(
            title=series_name,
            defaults={
                'overview': description or f'本地创建的剧集: {series_name}',
                'status': '本地系列',
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ 创建剧集: {series.title}'))
        else:
            self.stdout.write(f'剧集已存在: {series.title}')
        
        # 初始化刮削器用于文件名解析
        scraper = VideoScraper()
        
        # 将匹配的电影关联到这个剧集
        updated_count = 0
        for movie in movies:
            # 从文件名提取集数信息
            episode_info = scraper.extract_series_info(movie.file_name)
            
            movie.series = series
            movie.episode_number = episode_info['episode_number']
            movie.season_number = episode_info['season_number'] or 1
            movie.save()
            updated_count += 1
            
            episode_display = f"S{movie.season_number:02d}E{movie.episode_number:02d}" if movie.episode_number else "未知集数"
            self.stdout.write(f'✓ 关联: {movie.file_name} -> {episode_display}')
        
        self.stdout.write(self.style.SUCCESS(f'完成! 已关联 {updated_count} 个文件到剧集 {series.title}'))
        
        # 显示统计信息
        total_episodes = series.movies.count()
        self.stdout.write(f'剧集 "{series.title}" 现在有 {total_episodes} 集') 