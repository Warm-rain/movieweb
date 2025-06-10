import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.http import JsonResponse, FileResponse, Http404, StreamingHttpResponse, HttpResponseNotFound, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db import transaction
from django.views.generic import ListView
from .models import Movie, WatchHistory, MovieRating, Series
from .forms import MovieRatingForm
from .transcoding import TranscodingService
import json
import mimetypes
from pathlib import Path
import os
import re
import time
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


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
        # 支持两种请求格式：JSON 和 传统表单
        if request.content_type == 'application/json':
            # AJAX JSON 请求
            data = json.loads(request.body)
            rating_value = int(data.get('rating', 0))
            comment = data.get('comment', '').strip()
        else:
            # 传统表单 POST 请求
            rating_value = int(request.POST.get('rating', 0))
            comment = request.POST.get('comment', '').strip()
        
        if not (1 <= rating_value <= 5):
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': '评分必须在1-5之间'})
            else:
                messages.error(request, '评分必须在1-5之间')
                return redirect('movie_detail', pk=pk)
        
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
        
        if request.content_type == 'application/json':
            # AJAX 响应
            return JsonResponse({
                'success': True,
                'message': '评分已更新' if not created else '评分已添加',
                'avg_rating': round(avg_rating, 1) if avg_rating else 0,
                'user_rating': rating_value
            })
        else:
            # 传统表单响应
            messages.success(request, '评分已更新' if not created else '评分已添加')
            return redirect('movie_detail', pk=pk)
        
    except (ValueError, TypeError):
        if request.content_type == 'application/json':
            return JsonResponse({'success': False, 'error': '无效的评分数据'})
        else:
            messages.error(request, '无效的评分数据')
            return redirect('movie_detail', pk=pk)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的JSON数据'})
    except Exception as e:
        if request.content_type == 'application/json':
            return JsonResponse({'success': False, 'error': str(e)})
        else:
            messages.error(request, f'评分失败: {str(e)}')
            return redirect('movie_detail', pk=pk)


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


# ==================== GPU硬解转码相关视图 ====================

def get_video_resolutions(request, pk):
    """获取视频可用分辨率"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        available_resolutions = transcoding_service.get_available_resolutions(movie)
        
        return JsonResponse({
            'success': True,
            'resolutions': available_resolutions,
            'original_info': transcoding_service.get_video_info(movie.file_path)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@require_POST
def start_transcoding(request, pk):
    """开始转码"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        data = json.loads(request.body)
        resolution = data.get('resolution')
        
        if not resolution:
            return JsonResponse({'success': False, 'error': '请指定分辨率'})
        
        if resolution == '原画':
            return JsonResponse({
                'success': True,
                'message': '原画无需转码',
                'status': 'completed',
                'url': f'/movies/{pk}/video/'
            })
        
        # 开始转码
        transcode_id, status = transcoding_service.start_transcoding(movie, resolution)
        
        if not transcode_id:
            return JsonResponse({
                'success': False,
                'error': '转码启动失败',
                'status': status
            })
        
        return JsonResponse({
            'success': True,
            'transcode_id': transcode_id,
            'status': status,
            'message': '转码已开始' if status == 'started' else '转码已完成'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的JSON数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def get_transcode_status(request, transcode_id):
    """获取转码状态"""
    try:
        status = transcoding_service.get_transcode_status(transcode_id)
        
        if not status:
            return JsonResponse({
                'success': False,
                'error': '转码任务不存在'
            })
        
        return JsonResponse({
            'success': True,
            'status': status['status'],
            'elapsed': status['elapsed'],
            'movie': status['movie'],
            'resolution': status['resolution']
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def serve_hls_video(request, pk, resolution):
    """提供HLS视频流"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        # 获取HLS文件路径
        hls_path = transcoding_service.get_hls_path(movie.id, resolution)
        
        if not hls_path.exists():
            return JsonResponse({
                'success': False,
                'error': f'转码文件不存在: {resolution}',
                'need_transcode': True
            })
        
        # 读取并返回m3u8文件
        with open(hls_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 修改相对路径为绝对URL
        lines = content.split('\n')
        modified_lines = []
        
        for line in lines:
            if line.endswith('.ts'):
                # 将.ts文件路径转换为URL
                ts_filename = line
                ts_url = f'/movies/{pk}/hls/{resolution}/{ts_filename}'
                modified_lines.append(ts_url)
            else:
                modified_lines.append(line)
        
        modified_content = '\n'.join(modified_lines)
        
        response = JsonResponse({
            'success': True,
            'content': modified_content,
            'content_type': 'application/vnd.apple.mpegurl'
        })
        
        return response
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def serve_hls_segment(request, pk, resolution, filename):
    """提供HLS视频片段"""
    movie = get_object_or_404(Movie, pk=pk)
    
    try:
        # 构建文件路径
        transcode_id = transcoding_service.generate_transcode_id(movie.id, resolution)
        segment_path = transcoding_service.transcode_dir / transcode_id / filename
        
        if not segment_path.exists():
            raise Http404(f"视频片段不存在: {filename}")
        
        # 流式返回视频片段
        def file_iterator(file_path, chunk_size=8192):
            with open(file_path, 'rb') as f:
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    yield data
        
        response = StreamingHttpResponse(
            file_iterator(segment_path),
            content_type='video/mp2t'
        )
        response['Content-Length'] = str(segment_path.stat().st_size)
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=3600'  # 缓存1小时
        
        return response
        
    except Exception as e:
        raise Http404(f"无法提供视频片段: {str(e)}")


def cleanup_transcodes(request):
    """清理旧的转码文件（管理员功能）"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': '权限不足'})
    
    try:
        transcoding_service.cleanup_old_transcodes()
        return JsonResponse({
            'success': True,
            'message': '转码文件清理完成'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== 视频扫描管理 ====================

@login_required
def scan_videos_page(request):
    """视频扫描管理页面"""
    if not request.user.is_superuser:
        messages.error(request, '只有管理员可以访问此页面')
        return redirect('index')
    
    context = {
        'total_movies': Movie.objects.count(),
        'total_series': Series.objects.count(),
        'recent_movies': Movie.objects.order_by('-created_at')[:5],
    }
    return render(request, 'movies/scan_videos.html', context)


@require_POST
@login_required
def start_scan_videos(request):
    """开始扫描视频"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': '权限不足'})
    
    try:
        data = json.loads(request.body)
        directory = data.get('directory', '').strip()
        enable_scraping = data.get('enable_scraping', False)
        generate_thumbnails = data.get('generate_thumbnails', False)
        overwrite = data.get('overwrite', False)
        
        if not directory:
            return JsonResponse({'success': False, 'error': '请指定扫描目录'})
        
        if not os.path.exists(directory):
            return JsonResponse({'success': False, 'error': '目录不存在'})
        
        # 在后台启动扫描任务
        import threading
        from django.core.management import call_command
        from io import StringIO
        
        def run_scan():
            """后台运行扫描"""
            try:
                # 构建命令参数
                args = [directory]
                kwargs = {}
                
                if enable_scraping:
                    kwargs['scrape'] = True
                if generate_thumbnails:
                    kwargs['generate_thumbnails'] = True
                if overwrite:
                    kwargs['overwrite'] = True
                
                # 捕获输出
                out = StringIO()
                call_command('scan_videos', *args, stdout=out, **kwargs)
                
                # 这里可以存储扫描结果到缓存或数据库
                print(f"✅ 扫描完成: {directory}")
                print(out.getvalue())
                
            except Exception as e:
                print(f"❌ 扫描失败: {e}")
        
        # 启动后台线程
        thread = threading.Thread(target=run_scan)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'message': '视频扫描已开始，请稍等...'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '无效的JSON数据'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required  
def get_scan_status(request):
    """获取扫描状态"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': '权限不足'})
    
    try:
        # 获取最新的电影统计
        total_movies = Movie.objects.count()
        total_series = Series.objects.count()
        recent_count = Movie.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(minutes=10)
        ).count()
        
        return JsonResponse({
            'success': True,
            'total_movies': total_movies,
            'total_series': total_series,
            'recent_added': recent_count,
            'last_update': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def cleanup_transcodes(request):
    """清理旧的转码文件（管理员功能）"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': '权限不足'})
    
    try:
        transcoding_service.cleanup_old_transcodes()
        return JsonResponse({
            'success': True,
            'message': '转码文件清理完成'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== 实时转码相关视图 ====================

def test_api(request):
    """测试API是否可访问"""
    print("🔍 [DEBUG] 测试API被调用")
    return JsonResponse({'success': True, 'message': 'API可以正常访问'})

@login_required
@require_GET
def get_available_resolutions(request, pk):
    """获取视频可用的分辨率选项"""
    print(f"🔍 [DEBUG] 获取分辨率API调用 - Movie ID: {pk}")
    
    movie = get_object_or_404(Movie, pk=pk)
    print(f"📺 [DEBUG] 视频文件: {movie.title}")
    print(f"📁 [DEBUG] 文件路径: {movie.file_path}")
    
    if not movie.file_path or not os.path.exists(movie.file_path):
        print(f"❌ [DEBUG] 视频文件不存在: {movie.file_path}")
        return JsonResponse({'success': False, 'error': '视频文件不存在'})
    
    print(f"✅ [DEBUG] 开始获取可用分辨率...")
    available_resolutions = TranscodingService.get_available_resolutions(movie.file_path)
    print(f"📊 [DEBUG] 可用分辨率: {available_resolutions}")
    
    # 添加原画质量选项
    available_resolutions.insert(0, '原画')
    
    # 获取视频原始信息
    video_info = TranscodingService.get_video_info(movie.file_path)
    print(f"📺 [DEBUG] 视频信息: {video_info}")
    
    result = {
        'success': True, 
        'resolutions': available_resolutions,
        'original_info': video_info
    }
    print(f"✅ [DEBUG] API响应: {result}")
    
    return JsonResponse(result)

@login_required
@require_GET
def realtime_transcode_request(request, pk, resolution):
    """请求实时转码"""
    print(f"🚀 [DEBUG] 实时转码请求 - Movie ID: {pk}, 分辨率: {resolution}")
    
    movie = get_object_or_404(Movie, pk=pk)
    print(f"📺 [DEBUG] 视频文件: {movie.title}")
    print(f"📁 [DEBUG] 文件路径: {movie.file_path}")
    
    if not movie.file_path or not os.path.exists(movie.file_path):
        print(f"❌ [DEBUG] 视频文件不存在: {movie.file_path}")
        return JsonResponse({'success': False, 'error': '视频文件不存在'})
    
    # 获取可用分辨率
    print(f"🔍 [DEBUG] 检查可用分辨率...")
    available_resolutions = TranscodingService.get_available_resolutions(movie.file_path)
    print(f"📊 [DEBUG] 可用分辨率: {available_resolutions}")
    
    # 检查请求的分辨率是否有效
    if resolution != '原画' and resolution not in available_resolutions:
        print(f"❌ [DEBUG] 不支持的分辨率: {resolution}")
        return JsonResponse({'success': False, 'error': f'不支持的分辨率: {resolution}'})
    
    # 如果是原画质量，直接返回成功
    if resolution == '原画':
        print(f"📺 [DEBUG] 使用原画质量，无需转码")
        return JsonResponse({
            'success': True,
            'status': 'ready',
            'realtime': False,
            'message': '使用原始视频质量'
        })
    
    # 开始实时转码
    print(f"🔥 [DEBUG] 开始实时转码: {resolution}")
    result = TranscodingService.start_realtime_transcoding(movie.file_path, resolution)
    print(f"🔥 [DEBUG] 转码结果: {result}")
    
    if result['success']:
        # 记录会话ID到用户会话
        if 'realtime_sessions' not in request.session:
            request.session['realtime_sessions'] = []
        
        # 添加新会话并确保不重复
        if result['session_id'] not in request.session['realtime_sessions']:
            request.session['realtime_sessions'].append(result['session_id'])
            request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'status': 'active',
            'realtime': True,
            'session_id': result['session_id'],
            'resolution': resolution,
            'encoder': result.get('encoder', 'unknown'),
            'rtx_optimized': result.get('rtx_optimized', False),
            'message': f'实时转码已开始: {resolution}'
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('error', '未知错误')
        })

@login_required
@require_GET
def realtime_hls_stream(request, pk, resolution, session_id):
    """获取实时HLS流"""
    movie = get_object_or_404(Movie, pk=pk)
    
    if not movie.file_path or not os.path.exists(movie.file_path):
        return JsonResponse({'success': False, 'error': '视频文件不存在'})
    
    # 验证会话是否属于当前用户
    if 'realtime_sessions' not in request.session or session_id not in request.session['realtime_sessions']:
        return JsonResponse({'success': False, 'error': '无效的转码会话'})
    
    # 获取HLS内容
    result = TranscodingService.get_realtime_hls_content(session_id, resolution)
    
    if result['success']:
        # 返回HLS文件的URL而不是内容
        hls_url = f'/api/realtime/{session_id}/hls/{resolution}.m3u8'
        return JsonResponse({
            'success': True,
            'hls_url': hls_url,
            'realtime': True
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('error', '未知错误'),
            'need_transcode': True  # 提示前端可能需要重新请求转码
        })

@login_required
@require_GET
def realtime_segment(request, session_id, segment_name):
    """获取实时HLS视频片段"""
    # 验证会话是否属于当前用户
    if 'realtime_sessions' not in request.session or session_id not in request.session['realtime_sessions']:
        return HttpResponseNotFound('无效的转码会话')
    
    # 检查会话是否存在
    session_info = TranscodingService.get_realtime_session(session_id)
    if not session_info['success']:
        return HttpResponseNotFound('转码会话不存在')
    
    # 组装片段文件路径
    from django.conf import settings
    TRANSCODED_DIR = os.path.join(settings.MEDIA_ROOT, 'transcoded')
    segment_path = os.path.join(TRANSCODED_DIR, f"realtime_{session_id}", segment_name)
    
    if not os.path.exists(segment_path):
        return HttpResponseNotFound('视频片段不存在')
    
    # 使用StreamingHttpResponse减少内存占用
    def file_iterator(file_path, chunk_size=8192):
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    
    response = StreamingHttpResponse(file_iterator(segment_path), content_type='video/MP2T')
    response['Cache-Control'] = 'max-age=300'  # 缓存5分钟
    
    return response

@require_GET  
def serve_realtime_hls(request, session_id, filename):
    """直接提供实时HLS文件"""
    # 简化版本：直接尝试访问文件，不检查会话（适用于重启后的情况）
    
    # 组装HLS文件路径
    from django.conf import settings
    TRANSCODED_DIR = os.path.join(settings.MEDIA_ROOT, 'transcoded')
    hls_path = os.path.join(TRANSCODED_DIR, f"realtime_{session_id}", filename)
    
    if not os.path.exists(hls_path):
        return HttpResponseNotFound('HLS文件不存在')
    
    try:
        # 读取HLS文件内容
        with open(hls_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 修改.ts文件路径为完整URL
        lines = content.split('\n')
        modified_lines = []
        
        for line in lines:
            if line.endswith('.ts'):
                # 将.ts文件路径转换为URL
                ts_url = f'/api/realtime/{session_id}/ts/{line}'
                modified_lines.append(ts_url)
            else:
                modified_lines.append(line)
        
        modified_content = '\n'.join(modified_lines)
        
        # 返回HLS播放列表
        response = HttpResponse(modified_content, content_type='application/vnd.apple.mpegurl')
        response['Cache-Control'] = 'no-cache'  # HLS文件不应缓存
        response['Access-Control-Allow-Origin'] = '*'  # 允许跨域访问
        
        return response
        
    except Exception as e:
        return HttpResponseNotFound(f'读取HLS文件失败: {str(e)}')

@require_GET
def serve_realtime_segment(request, session_id, filename):
    """直接提供实时HLS片段文件"""  
    # 简化版本：直接尝试访问文件，不检查会话（适用于重启后的情况）
    
    # 组装片段文件路径
    from django.conf import settings
    TRANSCODED_DIR = os.path.join(settings.MEDIA_ROOT, 'transcoded')
    segment_path = os.path.join(TRANSCODED_DIR, f"realtime_{session_id}", filename)
    
    if not os.path.exists(segment_path):
        return HttpResponseNotFound('视频片段不存在')
    
    # 使用StreamingHttpResponse减少内存占用
    def file_iterator(file_path, chunk_size=8192):
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    
    response = StreamingHttpResponse(file_iterator(segment_path), content_type='video/MP2T')
    response['Content-Length'] = str(os.path.getsize(segment_path))
    response['Cache-Control'] = 'max-age=300'  # 缓存5分钟
    response['Access-Control-Allow-Origin'] = '*'  # 允许跨域访问
    
    return response

@login_required
@require_POST
def stop_realtime_session(request):
    """停止实时转码会话"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        if not session_id:
            return JsonResponse({'success': False, 'error': '缺少会话ID'})
        
        # 验证会话是否属于当前用户
        if 'realtime_sessions' not in request.session or session_id not in request.session['realtime_sessions']:
            return JsonResponse({'success': False, 'error': '无效的转码会话'})
        
        # 停止会话
        result = TranscodingService.stop_realtime_session(session_id)
        
        if result['success']:
            # 从用户会话中移除
            request.session['realtime_sessions'].remove(session_id)
            request.session.modified = True
            
            return JsonResponse({
                'success': True,
                'message': '实时转码会话已停止'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', '未知错误')
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }) 