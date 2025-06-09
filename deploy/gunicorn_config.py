# Gunicorn配置文件
import multiprocessing

# 服务器套接字
bind = "127.0.0.1:8000"
backlog = 2048

# 工作进程
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# 重启
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# 日志
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"

# 进程名称
proc_name = "movieweb"

# 用户和组
# user = "www-data"
# group = "www-data"

# 临时文件目录
tmp_upload_dir = None

# SSL (如果需要)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile" 