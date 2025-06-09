# 个人影视网站部署指南

## 环境要求

- Windows 10/11
- Python 3.8+
- FFmpeg（可选，用于生成缩略图）

## 快速部署

### 1. 自动部署（推荐）

运行部署脚本：
```bash
deploy\setup.bat
```

这个脚本会自动完成：
- 创建虚拟环境
- 安装依赖包
- 初始化数据库
- 创建超级用户
- 收集静态文件

### 2. 手动部署

#### 2.1 创建虚拟环境

```bash
python -m venv venv
venv\Scripts\activate.bat
```

#### 2.2 安装依赖

```bash
pip install -r requirements.txt
```

#### 2.3 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：
```
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
VIDEO_ROOT_PATH=D:\Videos
```

#### 2.4 初始化数据库

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

#### 2.5 收集静态文件

```bash
python manage.py collectstatic
```

## 运行项目

### 开发环境

```bash
# 使用脚本启动
run_dev.bat

# 或手动启动
venv\Scripts\activate.bat
python manage.py runserver
```

访问：http://127.0.0.1:8000

### 生产环境

```bash
# 使用脚本启动
run_prod.bat

# 或手动启动
venv\Scripts\activate.bat
gunicorn -c deploy/gunicorn_config.py movieweb.wsgi:application
```

## 视频文件管理

### 扫描视频文件

```bash
# 扫描默认目录
python manage.py scan_videos

# 扫描指定目录
python manage.py scan_videos "D:\Movies"

# 生成缩略图（需要FFmpeg）
python manage.py scan_videos "D:\Movies" --generate-thumbnails

# 更新已存在的影片信息
python manage.py scan_videos --update
```

### 支持的视频格式

- .mp4
- .avi
- .mkv
- .mov
- .wmv
- .flv
- .webm
- .m4v

## Nginx配置（可选）

如需使用Nginx作为反向代理，参考 `deploy/nginx.conf` 文件。

### 安装Nginx

1. 下载：https://nginx.org/en/download.html
2. 解压到合适位置
3. 修改配置文件
4. 启动Nginx

### 配置要点

- 静态文件代理
- 视频文件流优化
- 安全头设置
- SSL配置（如需要）

## FFmpeg安装

### Windows

1. 访问：https://ffmpeg.org/download.html
2. 下载Windows版本
3. 解压到系统PATH目录
4. 验证安装：`ffmpeg -version`

### 缩略图生成

FFmpeg用于：
- 生成视频缩略图
- 提取视频信息（时长等）
- 视频格式转换（未来功能）

## 故障排除

### 常见问题

1. **视频无法播放**
   - 检查文件路径是否正确
   - 确认视频格式是否支持
   - 检查文件权限

2. **缩略图不生成**
   - 确认FFmpeg已安装
   - 检查临时目录权限
   - 查看错误日志

3. **性能问题**
   - 调整Gunicorn工作进程数
   - 使用Nginx处理静态文件
   - 考虑使用SSD存储

### 日志查看

- Django日志：控制台输出
- Gunicorn日志：`logs/` 目录
- Nginx日志：Nginx安装目录

## 安全建议

### 生产环境

1. 设置 `DEBUG=False`
2. 使用强密码的SECRET_KEY
3. 配置HTTPS
4. 限制ALLOWED_HOSTS
5. 定期更新依赖包

### 网络安全

1. 使用防火墙限制访问
2. 定期备份数据
3. 监控系统资源
4. 设置访问日志

## 性能优化

### 数据库优化

- 定期清理观看历史
- 添加数据库索引
- 考虑使用PostgreSQL

### 缓存策略

- 使用Redis缓存
- CDN加速静态文件
- 视频文件本地缓存

### 服务器配置

- 调整工作进程数
- 优化内存使用
- 磁盘空间监控 