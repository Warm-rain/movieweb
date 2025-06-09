import os
import re
import json
import requests
import tempfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from django.conf import settings
from tmdbv3api import TMDb, TV, Movie as TMDbMovie
from .models import Movie, Series, ScrapingLog


class VideoScraper:
    """视频信息刮削器"""
    
    def __init__(self):
        self.tmdb = TMDb()
        # 设置TMDB API密钥 - 需要在settings.py中配置
        self.tmdb.api_key = getattr(settings, 'TMDB_API_KEY', '')
        self.tmdb.language = 'zh-CN'
        self.tmdb.debug = False
        
        self.tv_api = TV()
        self.movie_api = TMDbMovie()
        
        # 常见视频格式
        self.video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
        
        # 电视剧名称清理正则
        self.tv_patterns = [
            r'第(\d+)集',  # 第XX集
            r'[Ee](\d+)',  # E01, e01
            r'[Ss](\d+)[Ee](\d+)',  # S01E01
            r'\[(\d+)\]',  # [01]
            r'(\d+)',  # 单纯数字
        ]
        
        # 中国动漫名称映射（中文 -> 英文）
        self.chinese_anime_mapping = {
            '完美世界': 'Perfect World',
            '仙逆': 'Renegade Immortal', 
            '斗罗大陆': 'Soul Land',
            '绝世唐门': 'The Peerless Tang Clan',
            '斗罗大陆Ⅱ绝世唐门': 'Soul Land 2 The Peerless Tang Clan',
            '武神主宰': 'Martial God Asura',
            '万界独尊': 'Supreme Realm',
            '元龙': 'Yuan Long',
            '吞噬星空': 'Swallowed Star',
        }
    
    def extract_series_info(self, filename: str) -> Dict:
        """从文件名提取剧集信息"""
        result = {
            'series_name': filename,
            'season_number': 1,
            'episode_number': None,
            'episode_title': None
        }
        
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        
        # 匹配 S01E01 格式
        season_episode_match = re.search(r'[Ss](\d+)[Ee](\d+)', name)
        if season_episode_match:
            result['season_number'] = int(season_episode_match.group(1))
            result['episode_number'] = int(season_episode_match.group(2))
            result['series_name'] = re.sub(r'[Ss]\d+[Ee]\d+.*', '', name).strip()
            return result
        
        # 匹配 第XX集 格式
        episode_match = re.search(r'第(\d+)集', name)
        if episode_match:
            result['episode_number'] = int(episode_match.group(1))
            result['series_name'] = re.sub(r'第\d+集.*', '', name).strip()
            return result
        
        # 匹配 E01 格式
        episode_match = re.search(r'[Ee](\d+)', name)
        if episode_match:
            result['episode_number'] = int(episode_match.group(1))
            result['series_name'] = re.sub(r'[Ee]\d+.*', '', name).strip()
            return result
        
        # 匹配数字格式 [01] 或纯数字
        number_match = re.search(r'\[(\d+)\]', name)
        if number_match:
            result['episode_number'] = int(number_match.group(1))
            result['series_name'] = re.sub(r'\[\d+\].*', '', name).strip()
            return result
        
        # 尝试匹配末尾的数字
        end_number_match = re.search(r'(\d+)$', name)
        if end_number_match:
            result['episode_number'] = int(end_number_match.group(1))
            result['series_name'] = re.sub(r'\d+$', '', name).strip()
            return result
        
        return result
    
    def search_tmdb_tv(self, query: str) -> Optional[Dict]:
        """在TMDB搜索电视剧"""
        try:
            # 构建搜索词列表
            search_queries = [query]
            
            # 添加中文映射的英文名称
            for chinese, english in self.chinese_anime_mapping.items():
                if chinese in query:
                    search_queries.append(english)
                    search_queries.append(query.replace(chinese, english))
            
            # 添加文件名清理变体
            search_queries.extend([
                query.replace('.', ' '),  # Perfect.World -> Perfect World
                query.replace('_', ' '),  # Soul_Land -> Soul Land  
                query.split('.')[0],      # Perfect.World -> Perfect
                query.replace('Ⅱ', '2'),  # 斗罗大陆Ⅱ -> 斗罗大陆2
                query.replace('II', '2'), # Soul Land II -> Soul Land 2
            ])
            
            # 尝试每个搜索词
            for search_query in search_queries:
                if not search_query or search_query.strip() == '':
                    continue
                    
                try:
                    print(f"尝试搜索: {search_query}")
                    results = self.tv_api.search(search_query.strip())
                    if results:
                        print(f"✓ 找到结果: {results[0].get('name', 'Unknown')}")
                        return results[0]
                except Exception as search_error:
                    print(f"搜索 '{search_query}' 失败: {search_error}")
                    continue
                        
        except Exception as e:
            print(f"TMDB TV搜索错误: {e}")
        return None
    
    def search_tmdb_movie(self, query: str) -> Optional[Dict]:
        """在TMDB搜索电影"""
        try:
            results = self.movie_api.search(query)
            if results:
                return results[0]  # 返回第一个结果
        except Exception as e:
            print(f"TMDB电影搜索错误: {e}")
        return None
    
    def get_tv_details(self, tv_id: int) -> Optional[Dict]:
        """获取电视剧详细信息"""
        try:
            # 确保tv_id是整数
            if isinstance(tv_id, dict):
                tv_id = tv_id.get('id')
            tv_id = int(tv_id)
            return self.tv_api.details(tv_id)
        except Exception as e:
            print(f"获取TV详情错误: {e}")
        return None
    
    def get_movie_details(self, movie_id: int) -> Optional[Dict]:
        """获取电影详细信息"""
        try:
            return self.movie_api.details(movie_id)
        except Exception as e:
            print(f"获取电影详情错误: {e}")
        return None
    
    def download_image(self, url: str, save_to: str) -> bool:
        """下载图片到本地"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(save_to, 'wb') as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"下载图片失败 {url}: {e}")
            return False
    
    def get_image_url(self, path: str, size: str = 'w500') -> str:
        """构建完整的图片URL"""
        if not path:
            return ''
        return f"https://image.tmdb.org/t/p/{size}{path}"
    
    def scrape_tv_series(self, series_info: Dict, file_path: str) -> Tuple[Optional['Series'], Optional[Dict]]:
        """刮削电视剧信息"""
        series_name = series_info['series_name']
        
        # 记录刮削日志
        log_data = {
            'search_query': series_name,
            'source': 'tmdb_tv',
            'file_path': file_path
        }
        
        try:
            # 搜索电视剧
            tmdb_result = self.search_tmdb_tv(series_name)
            if not tmdb_result:
                # 如果TMDB找不到，创建本地系列记录
                print(f"TMDB未找到 {series_name}，创建本地系列记录")
                
                series, created = Series.objects.get_or_create(
                    title=series_name,
                    defaults={
                        'overview': f'本地扫描的系列: {series_name}',
                        'status': '本地系列',
                    }
                )
                
                ScrapingLog.objects.create(
                    success=True,
                    error_message=f"TMDB未找到，已创建本地系列: {series_name}",
                    **log_data
                )
                
                return series, None
            
            # 获取详细信息
            tv_details = self.get_tv_details(tmdb_result['id'])
            if not tv_details:
                ScrapingLog.objects.create(
                    success=False,
                    error_message=f"无法获取电视剧详情: {tmdb_result['id']}",
                    **log_data
                )
                return None, None
            
            # 查找或创建Series
            series, created = Series.objects.get_or_create(
                tmdb_id=tv_details['id'],
                defaults={
                    'title': tv_details.get('name', series_name),
                    'original_title': tv_details.get('original_name', ''),
                    'overview': tv_details.get('overview', ''),
                    'year': int(tv_details.get('first_air_date', '1900-01-01')[:4]) if tv_details.get('first_air_date') else None,
                    'genres': ', '.join([genre['name'] for genre in tv_details.get('genres', [])]),
                    'status': tv_details.get('status', ''),
                    'total_episodes': tv_details.get('number_of_episodes', 0),
                    'tmdb_rating': tv_details.get('vote_average', 0),
                    'poster_url': self.get_image_url(tv_details.get('poster_path', '')),
                    'backdrop_url': self.get_image_url(tv_details.get('backdrop_path', '')),
                }
            )
            
            # 下载海报
            if created and series.poster_url:
                poster_response = requests.get(series.poster_url, timeout=30)
                if poster_response.status_code == 200:
                    poster_file = ContentFile(poster_response.content)
                    series.poster_image.save(
                        f"series_{series.id}_poster.jpg",
                        poster_file,
                        save=True
                    )
            
            ScrapingLog.objects.create(
                success=True,
                result_data=tv_details,
                **log_data
            )
            
            return series, tv_details
            
        except Exception as e:
            ScrapingLog.objects.create(
                success=False,
                error_message=str(e),
                **log_data
            )
            return None, None
    
    def scrape_movie(self, title: str, file_path: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """刮削电影信息"""
        log_data = {
            'search_query': title,
            'source': 'tmdb_movie',
            'file_path': file_path
        }
        
        try:
            # 搜索电影
            tmdb_result = self.search_tmdb_movie(title)
            if not tmdb_result:
                ScrapingLog.objects.create(
                    success=False,
                    error_message=f"未找到电影: {title}",
                    **log_data
                )
                return None, None
            
            # 获取详细信息
            movie_details = self.get_movie_details(tmdb_result['id'])
            if not movie_details:
                ScrapingLog.objects.create(
                    success=False,
                    error_message=f"无法获取电影详情: {tmdb_result['id']}",
                    **log_data
                )
                return None, None
            
            ScrapingLog.objects.create(
                success=True,
                result_data=movie_details,
                **log_data
            )
            
            return tmdb_result, movie_details
            
        except Exception as e:
            ScrapingLog.objects.create(
                success=False,
                error_message=str(e),
                **log_data
            )
            return None, None
    
    def is_tv_series(self, filename: str) -> bool:
        """判断是否为电视剧文件"""
        # 检查是否有集数标识
        for pattern in self.tv_patterns:
            if re.search(pattern, filename):
                return True
        return False
    
    def scrape_video_info(self, file_path: str) -> Dict:
        """刮削视频信息的主要方法"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]
        
        result = {
            'success': False,
            'is_series': False,
            'series': None,
            'movie_data': None,
            'series_info': None,
            'message': ''
        }
        
        # 判断是否为电视剧
        if self.is_tv_series(filename):
            result['is_series'] = True
            series_info = self.extract_series_info(filename)
            result['series_info'] = series_info
            
            # 刮削电视剧信息
            series, tv_details = self.scrape_tv_series(series_info, file_path)
            if series:
                result['success'] = True
                result['series'] = series
                result['movie_data'] = tv_details
                result['message'] = f"成功刮削电视剧: {series.title}"
            else:
                result['message'] = f"无法刮削电视剧信息: {series_info['series_name']}"
        else:
            # 刮削电影信息
            movie_result, movie_details = self.scrape_movie(name_without_ext, file_path)
            if movie_result:
                result['success'] = True
                result['movie_data'] = movie_details
                result['message'] = f"成功刮削电影: {movie_details.get('title', name_without_ext)}"
            else:
                result['message'] = f"无法刮削电影信息: {name_without_ext}"
        
        return result 