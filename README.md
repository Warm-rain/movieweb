# 个人影视网站 - MovieWeb

基于Django的个人影视网站，支持自动扫描本地视频文件，在线播放，生成缩略图等功能。

## 功能特点

- 🎬 自动扫描本地视频文件
- 📺 在线视频播放
- 🖼️ 自动生成视频缩略图
- 👤 用户认证系统
- 🎨 现代化界面设计
- 📱 响应式布局

## 环境要求

- Python 3.8+
- FFmpeg（用于缩略图生成）
- Windows 10/11

## 安装步骤

### 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 2. 安装FFmpeg

下载并安装 FFmpeg：https://ffmpeg.org/download.html
确保 ffmpeg 命令可在命令行中使用。

### 3. 初始化数据库

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. 创建超级用户

```bash
python manage.py createsuperuser
```

### 5. 运行开发服务器

```bash
python manage.py runserver
```

### 6. 扫描视频文件

```bash
python manage.py scan_videos "D:\Videos"
```

## 生产部署

使用 Gunicorn + Nginx 进行生产部署：

```bash
gunicorn movieweb.wsgi:application --bind 127.0.0.1:8000
```

## 配置说明

在 `.env` 文件中配置：

```
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com,127.0.0.1
VIDEO_ROOT_PATH=D:\Videos
``` 