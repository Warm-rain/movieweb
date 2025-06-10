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
    
    # GPU硬解转码相关路由
    path('movie/<int:pk>/resolutions/', views.get_video_resolutions, name='get_video_resolutions'),
    path('movie/<int:pk>/transcode/', views.start_transcoding, name='start_transcoding'),
    path('transcode/status/<str:transcode_id>/', views.get_transcode_status, name='get_transcode_status'),
    path('movie/<int:pk>/hls/<str:resolution>/', views.serve_hls_video, name='serve_hls_video'),
    path('movie/<int:pk>/hls/<str:resolution>/<str:filename>', views.serve_hls_segment, name='serve_hls_segment'),
    path('management/cleanup-transcodes/', views.cleanup_transcodes, name='cleanup_transcodes'),
    
    # 视频扫描管理路由
    path('management/scan-videos/', views.scan_videos_page, name='scan_videos_page'),
    path('management/scan-videos/start/', views.start_scan_videos, name='start_scan_videos'),
    path('management/scan-videos/status/', views.get_scan_status, name='get_scan_status'),
    
    # 新增实时转码相关API
    path('api/test/', views.test_api, name='test_api'),
    path('api/<int:pk>/resolutions/', views.get_available_resolutions, name='get_available_resolutions'),
    path('api/<int:pk>/realtime/<str:resolution>/', views.realtime_transcode_request, name='realtime_transcode_request'),
    path('api/<int:pk>/realtime/<str:resolution>/<str:session_id>/', views.realtime_hls_stream, name='realtime_hls_stream'),
    path('api/realtime/segment/<str:session_id>/<str:segment_name>', views.realtime_segment, name='realtime_segment'),
    path('api/realtime/stop/', views.stop_realtime_session, name='stop_realtime_session'),
    
    # HLS文件直接访问
    path('api/realtime/<str:session_id>/hls/<str:filename>', views.serve_realtime_hls, name='serve_realtime_hls'),
    path('api/realtime/<str:session_id>/ts/<str:filename>', views.serve_realtime_segment, name='serve_realtime_segment'),
] 