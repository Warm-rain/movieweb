import os
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


class Series(models.Model):
    """剧集/系列模型"""
    title = models.CharField(max_length=200, verbose_name='剧集名称')
    original_title = models.CharField(max_length=200, blank=True, verbose_name='原始标题')
    overview = models.TextField(blank=True, verbose_name='剧情简介')
    poster_url = models.URLField(blank=True, verbose_name='海报URL')
    backdrop_url = models.URLField(blank=True, verbose_name='背景图URL')
    poster_image = models.ImageField(upload_to='posters/', blank=True, null=True, verbose_name='本地海报')
    backdrop_image = models.ImageField(upload_to='backdrops/', blank=True, null=True, verbose_name='本地背景图')
    
    # 外部数据库信息
    tmdb_id = models.IntegerField(null=True, blank=True, verbose_name='TMDB ID')
    imdb_id = models.CharField(max_length=20, blank=True, verbose_name='IMDB ID')
    douban_id = models.CharField(max_length=20, blank=True, verbose_name='豆瓣ID')
    
    # 基本信息
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='年份')
    genres = models.CharField(max_length=200, blank=True, verbose_name='类型')
    status = models.CharField(max_length=50, blank=True, verbose_name='状态')
    total_episodes = models.PositiveIntegerField(null=True, blank=True, verbose_name='总集数')
    
    # 评分信息
    tmdb_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name='TMDB评分')
    imdb_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name='IMDB评分')
    douban_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name='豆瓣评分')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '剧集'
        verbose_name_plural = '剧集'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('series_detail', kwargs={'pk': self.pk})

    @property
    def current_episodes_count(self):
        return self.movies.count()

    @property
    def average_user_rating(self):
        ratings = MovieRating.objects.filter(movie__series=self)
        if ratings.exists():
            return ratings.aggregate(models.Avg('rating'))['rating__avg']
        return None


class Movie(models.Model):
    title = models.CharField(max_length=200, verbose_name='标题')
    original_title = models.CharField(max_length=200, blank=True, verbose_name='原始标题')
    file_path = models.CharField(max_length=500, unique=True, verbose_name='文件路径')
    file_size = models.BigIntegerField(verbose_name='文件大小(字节)')
    duration = models.DurationField(null=True, blank=True, verbose_name='时长')
    
    # 关联剧集
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='movies', null=True, blank=True, verbose_name='所属剧集')
    episode_number = models.PositiveIntegerField(null=True, blank=True, verbose_name='集数')
    season_number = models.PositiveIntegerField(null=True, blank=True, verbose_name='季数')
    
    # 封面图片
    thumbnail = models.ImageField(upload_to='thumbnails/', null=True, blank=True, verbose_name='缩略图')
    poster_url = models.URLField(blank=True, verbose_name='海报URL')
    poster_image = models.ImageField(upload_to='episode_posters/', blank=True, null=True, verbose_name='剧集海报')
    
    # 视频信息
    description = models.TextField(blank=True, verbose_name='描述')
    genre = models.CharField(max_length=100, blank=True, verbose_name='类型')
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='年份')
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name='评分')
    
    # 外部数据库信息
    tmdb_id = models.IntegerField(null=True, blank=True, verbose_name='TMDB ID')
    imdb_id = models.CharField(max_length=20, blank=True, verbose_name='IMDB ID')
    
    # 统计信息
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    views = models.PositiveIntegerField(default=0, verbose_name='观看次数')

    class Meta:
        verbose_name = '影片'
        verbose_name_plural = '影片'
        ordering = ['series', 'season_number', 'episode_number', '-created_at']

    def __str__(self):
        if self.series and self.episode_number:
            return f"{self.series.title} S{self.season_number or 1:02d}E{self.episode_number:02d}"
        return self.title

    def get_absolute_url(self):
        return reverse('movie_detail', kwargs={'pk': self.pk})

    @property
    def file_name(self):
        return os.path.basename(self.file_path)

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)

    @property
    def display_title(self):
        if self.series and self.episode_number:
            title = f"第{self.episode_number}集"
            if self.title and self.title != self.series.title:
                title += f" - {self.title}"
            return title
        return self.title

    def increment_views(self):
        self.views += 1
        self.save(update_fields=['views'])


class WatchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, verbose_name='影片')
    watched_at = models.DateTimeField(auto_now_add=True, verbose_name='观看时间')
    progress = models.DurationField(null=True, blank=True, verbose_name='观看进度')

    class Meta:
        verbose_name = '观看历史'
        verbose_name_plural = '观看历史'
        unique_together = ['user', 'movie']
        ordering = ['-watched_at']

    def __str__(self):
        return f'{self.user.username} - {self.movie}'


class MovieRating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, verbose_name='影片')
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)], verbose_name='评分')
    comment = models.TextField(blank=True, verbose_name='评论')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '影片评分'
        verbose_name_plural = '影片评分'
        unique_together = ['user', 'movie']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.movie} - {self.rating}星'


class ScrapingLog(models.Model):
    """刮削日志"""
    file_path = models.CharField(max_length=500, verbose_name='文件路径')
    search_query = models.CharField(max_length=200, verbose_name='搜索关键词')
    source = models.CharField(max_length=50, verbose_name='数据源')  # tmdb, douban, etc.
    success = models.BooleanField(default=False, verbose_name='是否成功')
    result_data = models.JSONField(null=True, blank=True, verbose_name='结果数据')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '刮削日志'
        verbose_name_plural = '刮削日志'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.search_query} - {self.source} - {"成功" if self.success else "失败"}' 