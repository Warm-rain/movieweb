import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Avg
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from .models import Movie, WatchHistory, MovieRating
from .forms import MovieRatingForm


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


def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    
    # 增加观看次数
    movie.increment_views()
    
    # 获取用户观看历史
    watch_history = None
    user_rating = None
    
    if request.user.is_authenticated:
        watch_history, created = WatchHistory.objects.get_or_create(
            user=request.user,
            movie=movie
        )
        try:
            user_rating = MovieRating.objects.get(user=request.user, movie=movie)
        except MovieRating.DoesNotExist:
            pass
    
    # 获取平均评分
    avg_rating = MovieRating.objects.filter(movie=movie).aggregate(Avg('rating'))['rating__avg']
    
    # 获取评论
    ratings = MovieRating.objects.filter(movie=movie).select_related('user')
    
    context = {
        'movie': movie,
        'watch_history': watch_history,
        'user_rating': user_rating,
        'avg_rating': avg_rating,
        'ratings': ratings,
        'rating_form': MovieRatingForm(),
    }
    
    return render(request, 'movies/movie_detail.html', context)


def serve_video(request, pk):
    """提供视频文件流服务"""
    movie = get_object_or_404(Movie, pk=pk)
    
    if not os.path.exists(movie.file_path):
        raise Http404("视频文件不存在")
    
    try:
        response = FileResponse(
            open(movie.file_path, 'rb'),
            content_type='video/mp4'
        )
        response['Content-Disposition'] = f'inline; filename="{movie.file_name}"'
        return response
    except Exception as e:
        raise Http404(f"无法播放视频: {str(e)}")


@login_required
@csrf_exempt
def update_watch_progress(request, pk):
    """更新观看进度"""
    if request.method == 'POST':
        movie = get_object_or_404(Movie, pk=pk)
        progress_seconds = int(request.POST.get('progress', 0))
        
        watch_history, created = WatchHistory.objects.get_or_create(
            user=request.user,
            movie=movie
        )
        
        # 将秒转换为时间间隔
        from datetime import timedelta
        watch_history.progress = timedelta(seconds=progress_seconds)
        watch_history.save()
        
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'error'})


@login_required
def rate_movie(request, pk):
    """评分影片"""
    movie = get_object_or_404(Movie, pk=pk)
    
    if request.method == 'POST':
        form = MovieRatingForm(request.POST)
        if form.is_valid():
            rating, created = MovieRating.objects.get_or_create(
                user=request.user,
                movie=movie,
                defaults={
                    'rating': form.cleaned_data['rating'],
                    'comment': form.cleaned_data['comment']
                }
            )
            
            if not created:
                rating.rating = form.cleaned_data['rating']
                rating.comment = form.cleaned_data['comment']
                rating.save()
            
            messages.success(request, '评分提交成功！')
        else:
            messages.error(request, '评分提交失败，请检查输入。')
    
    return redirect('movie_detail', pk=pk)


@login_required
def watch_history_view(request):
    """观看历史页面"""
    history = WatchHistory.objects.filter(user=request.user).select_related('movie')
    
    paginator = Paginator(history, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'movies/watch_history.html', {'page_obj': page_obj}) 