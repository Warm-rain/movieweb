from django.core.management.base import BaseCommand
from movies.models import Movie, Series
from movies.scraper import VideoScraper


class Command(BaseCommand):
    help = '为指定剧集名称刮削信息'

    def add_arguments(self, parser):
        parser.add_argument('series_name', type=str, help='要刮削的剧集名称')
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制重新刮削已有信息的剧集',
        )

    def handle(self, *args, **options):
        series_name = options['series_name']
        force = options['force']
        
        self.stdout.write(f'正在搜索剧集: {series_name}')
        
        # 查找匹配的电影文件
        movies = Movie.objects.filter(
            title__icontains=series_name
        ).filter(series__isnull=True)
        
        if not movies.exists():
            self.stdout.write(self.style.ERROR(f'未找到匹配的电影文件: {series_name}'))
            return
        
        self.stdout.write(f'找到 {movies.count()} 个匹配的文件')
        
        # 初始化刮削器
        scraper = VideoScraper()
        
        # 刮削剧集信息
        series_info = scraper.extract_series_info(series_name)
        series, tv_details = scraper.scrape_tv_series(series_info, movies.first().file_path)
        
        if series:
            self.stdout.write(self.style.SUCCESS(f'✓ 成功创建剧集: {series.title}'))
            
            # 将匹配的电影关联到这个剧集
            updated_count = 0
            for movie in movies:
                episode_info = scraper.extract_series_info(movie.file_name)
                movie.series = series
                movie.episode_number = episode_info['episode_number']
                movie.season_number = episode_info['season_number']
                movie.save()
                updated_count += 1
                
                self.stdout.write(f'✓ 关联: {movie.title} -> S{movie.season_number:02d}E{movie.episode_number:02d}')
            
            self.stdout.write(self.style.SUCCESS(f'完成! 已关联 {updated_count} 个文件到剧集 {series.title}'))
        else:
            self.stdout.write(self.style.ERROR(f'✗ 刮削失败: {series_name}')) 