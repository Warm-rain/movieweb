from django.contrib import admin
from .models import Movie, WatchHistory, MovieRating


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['title', 'genre', 'year', 'rating', 'file_size_mb', 'views', 'created_at']
    list_filter = ['genre', 'year', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at', 'views']
    list_per_page = 20

    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_mb.short_description = '文件大小'


@admin.register(WatchHistory)
class WatchHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'movie', 'watched_at', 'progress']
    list_filter = ['watched_at']
    search_fields = ['user__username', 'movie__title']
    readonly_fields = ['watched_at']


@admin.register(MovieRating)
class MovieRatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'movie', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['user__username', 'movie__title', 'comment']
    readonly_fields = ['created_at'] 