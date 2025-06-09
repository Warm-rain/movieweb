import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.views.generic import ListView
from .models import Movie, WatchHistory, MovieRating, Series
from .forms import MovieRatingForm
import json


class MovieListView(ListView):
    model = Movie
    template_name = 'movies/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 12

    def get_queryset(self):
        queryset = Movie.objects.all()
        search = self.request.GET.get('search')
        genre = self.request.GET.get('genre')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
        
        if genre:
            queryset = queryset.filter(genre__icontains=genre)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 获取所有类型用于筛选
        genres = Movie.objects.values_list('genre', flat=True).distinct()
        context['genres'] = [g for g in genres if g]
        context['search'] = self.request.GET.get('search', '')
        context['selected_genre'] = self.request.GET.get('genre', '')
        return context


def index(request):
    """首页视图 - 显示剧集和独立电影"""
    # 获取搜索和筛选参数
    query = request.GET.get('q', '')
    genre_filter = request.GET.get('genre', '')
    year_filter = request.GET.get('year', '')
    view_mode = request.GET.get('view', 'series')  # series 或 movies
    
    # 基础查询
    if view_mode == 'series':
        # 剧集模式：显示剧集
        items = Series.objects.all()
        
        if query:
            items = items.filter(
                Q(title__icontains=query) | 
                Q(original_title__icontains=query) |
                Q(overview__icontains=query)
            )
        
        if genre_filter:
            items = items.filter(genres__icontains=genre_filter)
        
        if year_filter:
            items = items.filter(year=year_filter)
        
        items = items.annotate(
            avg_rating=Avg('movies__movierating__rating'),
            total_views=Count('movies__watchhistory'),
        ).order_by('-created_at')
        
        # 获取独立电影（不属于任何剧集的电影）
        independent_movies = Movie.objects.filter(series__isnull=True)
        
        # 对独立电影进行同样的筛选
        if query:
            independent_movies = independent_movies.filter(
                Q(title__icontains=query) | 
                Q(original_title__icontains=query) |
                Q(description__icontains=query)
            )
        
        if genre_filter:
            independent_movies = independent_movies.filter(genre__icontains=genre_filter)
        
        if year_filter:
            independent_movies = independent_movies.filter(year=year_filter)
        
        independent_movies = independent_movies.annotate(
            avg_rating=Avg('movierating__rating'),
        ).order_by('-created_at')
        
    else:
        # 电影模式：显示所有电影
        items = Movie.objects.all()
        independent_movies = None
        
        if query:
            items = items.filter(
                Q(title__icontains=query) | 
                Q(original_title__icontains=query) |
                Q(description__icontains=query) |
                Q(series__title__icontains=query)
            )
        
        if genre_filter:
            items = items.filter(
                Q(genre__icontains=genre_filter) |
                Q(series__genres__icontains=genre_filter)
            )
        
        if year_filter:
            items = items.filter(
                Q(year=year_filter) |
                Q(series__year=year_filter)
            )
        
        items = items.annotate(
            avg_rating=Avg('movierating__rating'),
        ).select_related('series').order_by('series', 'season_number', 'episode_number', '-created_at')
    
    # 分页
    paginator = Paginator(items, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 获取所有类型和年份用于筛选
    if view_mode == 'series':
        all_genres = set()
        all_years = set()
        
        # 从剧集获取
        for series in Series.objects.all():
            if series.genres:
                all_genres.update([g.strip() for g in series.genres.split(',')])
            if series.year:
                all_years.add(series.year)
        
        # 从独立电影获取
        for movie in Movie.objects.filter(series__isnull=True):
            if movie.genre:
                all_genres.update([g.strip() for g in movie.genre.split(',')])
            if movie.year:
                all_years.add(movie.year)
    else:
        all_genres = set()
        all_years = set()
        
        for movie in Movie.objects.all():
            # 从电影本身获取
            if movie.genre:
                all_genres.update([g.strip() for g in movie.genre.split(',')])
            if movie.year:
                all_years.add(movie.year)
            
            # 从所属剧集获取
            if movie.series:
                if movie.series.genres:
                    all_genres.update([g.strip() for g in movie.series.genres.split(',')])
                if movie.series.year:
                    all_years.add(movie.series.year)
    
    genres = sorted([g for g in all_genres if g])
    years = sorted(all_years, reverse=True)
    
    # 独立电影分页
    independent_page_obj = None
    if independent_movies:
        independent_paginator = Paginator(independent_movies, 6)
        independent_page_obj = independent_paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'independent_page_obj': independent_page_obj,
        'query': query,
        'genre_filter': genre_filter,
        'year_filter': year_filter,
        'view_mode': view_mode,
        'genres': genres,
        'years': years,
        'total_series': Series.objects.count(),
        'total_movies': Movie.objects.count(),
        'total_independent': Movie.objects.filter(series__isnull=True).count(),
    }
    
    return render(request, 'movies/index.html', context)


def series_detail(request, pk):
    """剧集详情页"""
    series = get_object_or_404(Series, pk=pk)
    
    # 获取该剧集下的所有剧集，按季和集数排序
    episodes = series.movies.all().annotate(
        avg_rating=Avg('movierating__rating'),
    ).order_by('season_number', 'episode_number')
    
    # 按季分组
    seasons = {}
    seasons_list = []
    for episode in episodes:
        season_num = episode.season_number or 1
        if season_num not in seasons:
            seasons[season_num] = []
            seasons_list.append(season_num)
        seasons[season_num].append(episode)
    
    # 当前季度
    current_season = request.GET.get('season')
    if current_season:
        try:
            current_season = int(current_season)
        except ValueError:
            current_season = None
    
    if current_season is None and seasons_list:
        current_season = min(seasons_list)
    
    # 用户评分
    user_rating = None
    last_watched = None
    if request.user.is_authenticated:
        # 获取用户对该剧集的平均评分
        user_ratings = MovieRating.objects.filter(
            user=request.user,
            movie__series=series
        )
        if user_ratings.exists():
            user_rating = user_ratings.aggregate(Avg('rating'))['rating__avg']
        
        # 获取最后观看的剧集
        last_watch = WatchHistory.objects.filter(
            user=request.user,
            movie__series=series
        ).select_related('movie').order_by('-watched_at').first()
        
        if last_watch:
            last_watched = last_watch.movie
    
    # 最近观看记录
    recent_watches = None
    if request.user.is_authenticated:
        recent_watches = WatchHistory.objects.filter(
            user=request.user,
            movie__series=series
        ).select_related('movie').order_by('-watched_at')[:5]
    
    context = {
        'series': series,
        'episodes': episodes,
        'seasons': sorted(seasons_list),
        'current_season': current_season,
        'season_episodes_count': len(seasons.get(current_season, [])) if current_season else 0,
        'total_episodes': episodes.count(),
        'user_rating': user_rating,
        'last_watched': last_watched,
        'recent_watches': recent_watches,
        'avg_rating': episodes.aggregate(Avg('movierating__rating'))['movierating__rating__avg'],
        'total_views': WatchHistory.objects.filter(movie__series=series).count(),
    }
    
    return render(request, 'movies/series_detail.html', context)


def movie_detail(request, pk):
    """电影详情页"""
    movie = get_object_or_404(Movie, pk=pk)
    
    # 获取用户评分和观看历史
    user_rating = None
    watch_history = None
    
    if request.user.is_authenticated:
        try:
            user_rating = MovieRating.objects.get(user=request.user, movie=movie)
        except MovieRating.DoesNotExist:
            pass
        
        try:
            watch_history = WatchHistory.objects.get(user=request.user, movie=movie)
        except WatchHistory.DoesNotExist:
            pass
    
    # 获取所有评分
    ratings = MovieRating.objects.filter(movie=movie).select_related('user').order_by('-created_at')
    avg_rating = ratings.aggregate(Avg('rating'))['rating__avg']
    
    # 如果是剧集的一部分，获取其他剧集
    related_episodes = None
    if movie.series:
        related_episodes = movie.series.movies.exclude(pk=movie.pk).order_by('season_number', 'episode_number')
    
    # 推荐电影（同类型或同剧集）
    recommended_movies = Movie.objects.exclude(pk=movie.pk)
    if movie.series:
        # 推荐同剧集的其他集
        recommended_movies = recommended_movies.filter(series=movie.series)
    elif movie.genre:
        # 推荐同类型电影
        recommended_movies = recommended_movies.filter(genre__icontains=movie.genre.split(',')[0])
    
    recommended_movies = recommended_movies.annotate(
        avg_rating=Avg('movierating__rating'),
    ).order_by('-views')[:6]
    
    context = {
        'movie': movie,
        'user_rating': user_rating,
        'watch_history': watch_history,
        'ratings': ratings,
        'avg_rating': avg_rating,
        'rating_form': MovieRatingForm(),
        'related_episodes': related_episodes,
        'recommended_movies': recommended_movies,
    }
    
    return render(request, 'movies/movie_detail.html', context)


def serve_video(request, pk):
    """提供视频文件流服务，支持HTTP Range请求"""
    movie = get_object_or_404(Movie, pk=pk)
    
    if not os.path.exists(movie.file_path):
        raise Http404("视频文件不存在")
    
    try:
        import mimetypes
        from django.http import StreamingHttpResponse
        
        # 获取文件信息
        file_path = movie.file_path
        file_size = os.path.getsize(file_path)
        
        # 确定MIME类型
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = 'video/mp4'
        
        # 检查是否是Range请求
        range_header = request.META.get('HTTP_RANGE')
        
        if range_header:
            # 解析Range头
            range_match = range_header.replace('bytes=', '').split('-')
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if range_match[1] else file_size - 1
            
            # 确保范围有效
            start = max(0, start)
            end = min(file_size - 1, end)
            content_length = end - start + 1
            
            # 创建文件迭代器
            def file_iterator(file_path, start, chunk_size=8192):
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(chunk_size, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            
            # 创建206 Partial Content响应
            response = StreamingHttpResponse(
                file_iterator(file_path, start),
                status=206,
                content_type=content_type
            )
            response['Content-Length'] = str(content_length)
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            
        else:
            # 普通请求，返回整个文件
            def file_iterator(file_path, chunk_size=8192):
                with open(file_path, 'rb') as f:
                    while True:
                        data = f.read(chunk_size)
                        if not data:
                            break
                        yield data
            
            response = StreamingHttpResponse(
                file_iterator(file_path),
                content_type=content_type
            )
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
        
        # 设置缓存和其他头
        response['Content-Disposition'] = f'inline; filename="{movie.file_name}"'
        response['Cache-Control'] = 'no-cache'
        response['X-Content-Type-Options'] = 'nosniff'
        
        return response
        
    except Exception as e:
        raise Http404(f"无法播放视频: {str(e)}")


@login_required
@require_POST
def rate_movie(request, pk):
    """为电影评分"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        data = json.loads(request.body)
        rating_value = int(data.get('rating', 0))
        comment = data.get('comment', '').strip()
        
        if not (1 <= rating_value <= 5):
            return JsonResponse({'success': False, 'error': '评分必须在1-5之间'})
        
        with transaction.atomic():
            rating, created = MovieRating.objects.update_or_create(
                user=request.user,
                movie=movie,
                defaults={
                    'rating': rating_value,
                    'comment': comment
                }
            )
        
        # 计算新的平均评分
        avg_rating = MovieRating.objects.filter(movie=movie).aggregate(
            Avg('rating')
        )['rating__avg']
        
        return JsonResponse({
            'success': True,
            'message': '评分已更新' if not created else '评分已添加',
            'avg_rating': round(avg_rating, 1) if avg_rating else 0,
            'user_rating': rating_value
        })
        
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': '无效的请求数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def update_progress(request, pk):
    """更新观看进度"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        data = json.loads(request.body)
        current_time = float(data.get('currentTime', 0))
        
        if current_time < 0:
            return JsonResponse({'success': False, 'error': '无效的时间'})
        
        from datetime import timedelta
        progress = timedelta(seconds=current_time)
        
        with transaction.atomic():
            watch_history, created = WatchHistory.objects.update_or_create(
                user=request.user,
                movie=movie,
                defaults={
                    'progress': progress,
                    'watched_at': timezone.now()
                }
            )
            
            # 增加观看次数（仅在第一次观看时）
            if created:
                movie.increment_views()
        
        return JsonResponse({
            'success': True,
            'message': '进度已保存',
            'progress_seconds': current_time
        })
        
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': '无效的请求数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def play_movie(request, pk):
    """播放电影"""
    movie = get_object_or_404(Movie, pk=pk)
    
    # 检查文件是否存在
    import os
    if not os.path.exists(movie.file_path):
        raise Http404("视频文件不存在")
    
    # 获取观看历史
    watch_history = None
    if request.user.is_authenticated:
        try:
            watch_history = WatchHistory.objects.get(user=request.user, movie=movie)
        except WatchHistory.DoesNotExist:
            pass
    
    # 获取该剧集的其他集数（如果是剧集的话）
    playlist = None
    current_index = 0
    
    if movie.series:
        playlist = list(movie.series.movies.order_by('season_number', 'episode_number'))
        try:
            current_index = playlist.index(movie)
        except ValueError:
            current_index = 0
    
    context = {
        'movie': movie,
        'watch_history': watch_history,
        'playlist': playlist,
        'current_index': current_index,
        'has_next': playlist and current_index < len(playlist) - 1 if playlist else False,
        'has_prev': playlist and current_index > 0 if playlist else False,
        'next_movie': playlist[current_index + 1] if playlist and current_index < len(playlist) - 1 else None,
        'prev_movie': playlist[current_index - 1] if playlist and current_index > 0 else None,
    }
    
    return render(request, 'movies/play.html', context)


@login_required
def watch_history_view(request):
    """观看历史页面"""
    history = WatchHistory.objects.filter(user=request.user).select_related('movie')
    
    paginator = Paginator(history, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'movies/watch_history.html', {'page_obj': page_obj}) 