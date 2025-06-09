from django.urls import path
from . import views

urlpatterns = [
    path('', views.MovieListView.as_view(), name='movie_list'),
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),
    path('video/<int:pk>/', views.serve_video, name='serve_video'),
    path('movie/<int:pk>/rate/', views.rate_movie, name='rate_movie'),
    path('movie/<int:pk>/progress/', views.update_watch_progress, name='update_watch_progress'),
    path('history/', views.watch_history_view, name='watch_history'),
] 