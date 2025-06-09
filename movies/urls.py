from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('series/<int:pk>/', views.series_detail, name='series_detail'),
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),
    path('movie/<int:pk>/play/', views.play_movie, name='play_movie'),
    path('movie/<int:pk>/serve/', views.serve_video, name='serve_video'),
    path('movie/<int:pk>/rate/', views.rate_movie, name='rate_movie'),
    path('movie/<int:pk>/progress/', views.update_progress, name='update_progress'),
    path('history/', views.watch_history_view, name='watch_history'),
] 