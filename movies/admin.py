from django.contrib import admin
from django.utils.html import format_html
from .models import Movie, WatchHistory, MovieRating, Series, ScrapingLog


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ['title', 'year', 'current_episodes_count', 'tmdb_rating', 'status', 'created_at']
    list_filter = ['year', 'status', 'genres', 'created_at']
    search_fields = ['title', 'original_title', 'overview']
    readonly_fields = ['created_at', 'updated_at', 'current_episodes_count']
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'original_title', 'overview', 'year', 'genres', 'status', 'total_episodes')
        }),
        ('海报和图片', {
            'fields': ('poster_url', 'poster_image', 'backdrop_url', 'backdrop_image'),
            'classes': ('collapse',)
        }),
        ('外部数据库', {
            'fields': ('tmdb_id', 'imdb_id', 'douban_id'),
            'classes': ('collapse',)
        }),
        ('评分信息', {
            'fields': ('tmdb_rating', 'imdb_rating', 'douban_rating'),
            'classes': ('collapse',)
        }),
        ('系统信息', {
            'fields': ('created_at', 'updated_at', 'current_episodes_count'),
            'classes': ('collapse',)
        }),
    )
    
    def current_episodes_count(self, obj):
        return obj.current_episodes_count
    current_episodes_count.short_description = '已有集数'


class MovieInline(admin.TabularInline):
    model = Movie
    extra = 0
    fields = ['episode_number', 'title', 'file_size_mb', 'views']
    readonly_fields = ['file_size_mb']


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['display_title', 'series_info', 'file_size_mb', 'duration', 'rating', 'views', 'created_at']
    list_filter = ['series', 'genre', 'year', 'created_at']
    search_fields = ['title', 'original_title', 'description', 'file_path']
    readonly_fields = ['file_name', 'file_size_mb', 'created_at', 'updated_at']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'original_title', 'file_path', 'file_name', 'file_size', 'file_size_mb', 'duration')
        }),
        ('剧集信息', {
            'fields': ('series', 'season_number', 'episode_number'),
            'classes': ('collapse',)
        }),
        ('内容信息', {
            'fields': ('description', 'genre', 'year', 'rating'),
        }),
        ('图片和缩略图', {
            'fields': ('thumbnail', 'poster_url', 'poster_image'),
            'classes': ('collapse',)
        }),
        ('外部数据库', {
            'fields': ('tmdb_id', 'imdb_id'),
            'classes': ('collapse',)
        }),
        ('统计信息', {
            'fields': ('views', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_title(self, obj):
        return obj.display_title
    display_title.short_description = '显示标题'
    
    def series_info(self, obj):
        if obj.series:
            return f"{obj.series.title} S{obj.season_number or 1:02d}E{obj.episode_number or 0:02d}"
        return "-"
    series_info.short_description = '剧集信息'
    
    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = '文件大小'


@admin.register(WatchHistory)
class WatchHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'movie', 'progress', 'watched_at']
    list_filter = ['watched_at']
    search_fields = ['user__username', 'movie__title']
    readonly_fields = ['watched_at']


@admin.register(MovieRating)
class MovieRatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'movie', 'rating', 'comment_preview', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['user__username', 'movie__title', 'comment']
    readonly_fields = ['created_at']
    
    def comment_preview(self, obj):
        if obj.comment:
            return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
        return '-'
    comment_preview.short_description = '评论预览'


@admin.register(ScrapingLog)
class ScrapingLogAdmin(admin.ModelAdmin):
    list_display = ['search_query', 'source', 'success_status', 'created_at']
    list_filter = ['source', 'success', 'created_at']
    search_fields = ['search_query', 'file_path', 'error_message']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('file_path', 'search_query', 'source', 'success')
        }),
        ('结果数据', {
            'fields': ('result_data',),
            'classes': ('collapse',)
        }),
        ('错误信息', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('系统信息', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def success_status(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✓ 成功</span>')
        else:
            return format_html('<span style="color: red;">✗ 失败</span>')
    success_status.short_description = '状态' 