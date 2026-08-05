# AXIS Personal OS 3.0

个人操作系统：Organize. Reflect. Evolve.

## 快速部署

### 方式一：Docker（推荐）

```bash
# 解压后进入目录
cd AXIS-Personal-OS

# 设置密钥（生产环境必须修改）
export SECRET_KEY=your-secret-key-here

# 启动
docker-compose up -d

# 访问 http://localhost:5000
```

### 方式二：直接运行

```bash
cd AXIS-Personal-OS
pip install -r requirements.txt
python app.py
# 访问 http://localhost:5000
```

## 技术栈

- Flask 3.0 + Jinja2
- SQLite (WAL mode)
- Tailwind CSS (CDN)
- PWA (manifest + icons)

## 项目结构

```
├── app.py              # Flask 主应用（90+ 路由）
├── models.py           # 数据模型 + 迁移
├── auth.py             # 认证（自动登录默认用户）
├── utils.py            # 工具函数（ICS生成/AI分析/数据导出等）
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 镜像
├── docker-compose.yml  # Docker Compose 配置
├── templates/          # 22 个 Jinja2 模板
└── static/             # CSS/JS/图标/manifest
```

## 功能模块

| 模块 | 说明 |
|------|------|
| Core | 首页 Dashboard、天气、AI 洞察 |
| Plan | 日历、任务、目标、周期事项 |
| Log | 工作日志、项目复盘 |
| Think | 灵感收集、思考笔记 |
| Growth | 阅读、学习、知识资产 |
| Life | 健康、财务、月度计划 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DB_PATH | ./personal_os.db | 数据库路径 |
| SECRET_KEY | change-me-in-production | Session 密钥 |
| HOST | 0.0.0.0 | 绑定地址 |
| PORT | 5000 | 端口 |

## 数据持久化

Docker 部署时数据库存储在 `./data/` 目录，删除容器不会丢数据。

## License

Personal use.
