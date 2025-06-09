import os
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


class Movie(models.Model):
    title = models.CharField(max_length=200, verbose_name='标题')
    file_path = models.CharField(max_length=500, unique=True, verbose_name='文件路径')
    file_size = models.BigIntegerField(verbose_name='文件大小(字节)')
    duration = models.DurationField(null=True, blank=True, verbose_name='时长')
    thumbnail = models.ImageField(upload_to='thumbnails/', null=True, blank=True, verbose_name='缩略图')
    description = models.TextField(blank=True, verbose_name='描述')
    genre = models.CharField(max_length=100, blank=True, verbose_name='类型')
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='年份')
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, verbose_name='评分')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    views = models.PositiveIntegerField(default=0, verbose_name='观看次数')

    class Meta:
        verbose_name = '影片'
        verbose_name_plural = '影片'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('movie_detail', kwargs={'pk': self.pk})

    @property
    def file_name(self):
        return os.path.basename(self.file_path)

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)

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
        return f'{self.user.username} - {self.movie.title}'


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
        return f'{self.user.username} - {self.movie.title} - {self.rating}星' 