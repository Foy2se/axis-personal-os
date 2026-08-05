"""数据库模型与初始化 - Personal OS V3.0"""
import sqlite3
import os

# 数据库路径支持环境变量配置，方便 Docker/云部署持久化到卷
DB_PATH = os.environ.get('DB_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'personal_os.db')

# 所有内容表名
CONTENT_TABLES = [
    'tasks', 'work_logs', 'projects', 'project_reviews',
    'inbox', 'notes', 'goals', 'monthly_plans',
    'life_cycles', 'readings', 'learnings',
    'finance_monthly', 'big_expenses', 'purchase_decisions',
    'daily_health', 'cases', 'methodologies', 'viewpoints',
    'calendar_events', 'evening_plans',
    'decision_logs', 'body_rhythm', 'weather_cache',
    'daily_loop_state', 'ai_insights', 'maintenance_items'
]


def get_db():
    """获取数据库连接"""
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA busy_timeout = 30000")
    return db


def init_db():
    """初始化所有表 + 迁移 user_id"""
    db = get_db()

    # 1. 创建用户表
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. 创建备份记录表
    db.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            backup_type TEXT DEFAULT 'auto',
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 2.5 创建用户设置表
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            city TEXT DEFAULT 'Beijing',
            city_name TEXT DEFAULT '北京',
            life_direction TEXT,
            current_stage_goal TEXT,
            work_hours_start TEXT DEFAULT '09:00',
            work_hours_end TEXT DEFAULT '18:00',
            daily_loop_enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 3. 创建内容表（新表直接带 user_id）
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        type TEXT DEFAULT '工作',
        priority TEXT DEFAULT '中',
        deadline DATE,
        status TEXT DEFAULT '未开始',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        scheduled_date DATE
    );

    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        objective TEXT,
        start_date DATE,
        end_date DATE,
        stage TEXT DEFAULT '研究阶段',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS work_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        log_date DATE NOT NULL,
        project_id INTEGER,
        completed TEXT,
        problems TEXT,
        thoughts TEXT,
        tomorrow_focus TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS project_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        project_id INTEGER NOT NULL,
        objective TEXT,
        result TEXT,
        completion TEXT,
        good_points TEXT,
        bad_points TEXT,
        experience TEXT,
        optimization TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );

    CREATE TABLE IF NOT EXISTS inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        title TEXT,
        content TEXT,
        image_path TEXT,
        attachment_path TEXT,
        source TEXT,
        tags TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        title TEXT NOT NULL,
        content TEXT,
        category TEXT DEFAULT '其他',
        tags TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        description TEXT,
        level TEXT DEFAULT '年度目标',
        parent_id INTEGER,
        period TEXT,
        status TEXT DEFAULT '进行中',
        progress INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parent_id) REFERENCES goals(id)
    );

    CREATE TABLE IF NOT EXISTS monthly_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        year_month TEXT NOT NULL,
        work_goal TEXT,
        learning_goal TEXT,
        reading_plan TEXT,
        expense_plan TEXT,
        life_plan TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS life_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        category TEXT DEFAULT '其他',
        last_done_date DATE NOT NULL,
        cycle_number INTEGER NOT NULL,
        cycle_unit TEXT NOT NULL,
        next_date DATE NOT NULL,
        advance_remind TEXT DEFAULT '3天',
        status TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        book_name TEXT NOT NULL,
        author TEXT,
        purchase_status TEXT DEFAULT '未购买',
        reading_status TEXT DEFAULT '未开始',
        reading_goal TEXT,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS learnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        content TEXT NOT NULL,
        goal TEXT,
        period TEXT,
        progress INTEGER DEFAULT 0,
        result TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS finance_monthly (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        year_month TEXT NOT NULL,
        income REAL DEFAULT 0,
        fixed_expense REAL DEFAULT 0,
        free_amount REAL DEFAULT 0,
        summary TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS big_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        item_name TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT DEFAULT '生活',
        reason TEXT,
        satisfaction INTEGER,
        expense_date DATE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS purchase_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        item_name TEXT NOT NULL,
        reason TEXT,
        budget REAL,
        research TEXT,
        decision TEXT,
        result TEXT,
        satisfaction INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS daily_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        record_date DATE NOT NULL,
        sleep_score INTEGER,
        energy_score INTEGER,
        status_score INTEGER,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        industry TEXT,
        type TEXT,
        tags TEXT,
        analysis TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS methodologies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS viewpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        title TEXT NOT NULL,
        content TEXT,
        tags TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS calendar_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        title TEXT NOT NULL,
        event_date DATE NOT NULL,
        event_time TIME,
        type TEXT DEFAULT '工作',
        source_type TEXT,
        source_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS evening_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        plan_date DATE NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT '兴趣娱乐',
        estimated_time TEXT,
        priority TEXT DEFAULT '中',
        status TEXT DEFAULT '待执行',
        deferred_to DATE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME
    );

    CREATE TABLE IF NOT EXISTS decision_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        question TEXT NOT NULL,
        options TEXT,
        reasoning TEXT,
        final_decision TEXT,
        result TEXT,
        lesson TEXT,
        status TEXT DEFAULT '进行中',
        decided_at DATE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS body_rhythm (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        start_date DATE NOT NULL,
        end_date DATE,
        cycle_days INTEGER DEFAULT 28,
        next_predicted_date DATE,
        phase TEXT,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS weather_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        city TEXT NOT NULL,
        data TEXT NOT NULL,
        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS daily_loop_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        loop_date DATE NOT NULL,
        morning_completed INTEGER DEFAULT 0,
        evening_completed INTEGER DEFAULT 0,
        sleep_completed INTEGER DEFAULT 0,
        morning_at DATETIME,
        evening_at DATETIME,
        sleep_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, loop_date)
    );

    CREATE TABLE IF NOT EXISTS ai_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        priority TEXT DEFAULT '中',
        dismissed INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS maintenance_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 1,
        name TEXT NOT NULL,
        category TEXT DEFAULT '生活',
        last_done_date DATE,
        cycle_days INTEGER DEFAULT 30,
        next_date DATE,
        status TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. 迁移：为已存在的表添加 user_id 列（如果还没有）
    # 同时移除 work_logs 和 monthly_plans 和 daily_health 的 UNIQUE 约束
    # 改为 (user_id, date) 组合唯一
    for table in CONTENT_TABLES:
        try:
            # 检查 user_id 列是否存在
            cols = db.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [c['name'] for c in cols]
            if 'user_id' not in col_names:
                db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER DEFAULT 1")
        except Exception:
            pass

    # 5. 字段迁移：为现有表添加 AXIS 3.0 新字段
    migrations = [
        ("tasks", "focus_category", "TEXT DEFAULT 'Work'"),
        ("tasks", "auto_migrated", "INTEGER DEFAULT 0"),
        ("work_logs", "ai_summary", "TEXT"),
        ("work_logs", "achievements", "TEXT"),
        ("daily_health", "mood_score", "INTEGER"),
        ("daily_health", "mood_note", "TEXT"),
        ("inbox", "ai_category", "TEXT"),
    ]
    for table, col, dtype in migrations:
        try:
            cols = db.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [c['name'] for c in cols]
            if col not in col_names:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
        except Exception:
            pass

    # 6. 确保默认用户存在
    default_user = db.execute("SELECT id FROM users WHERE email = ?", ('user@personal-os.local',)).fetchone()
    if not default_user:
        from werkzeug.security import generate_password_hash
        db.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            ('user@personal-os.local', generate_password_hash('personalos'), '默认用户')
        )
        default_user = db.execute("SELECT id FROM users WHERE email = ?", ('user@personal-os.local',)).fetchone()

    # 6.5 确保默认用户设置存在
    uid = default_user['id'] if default_user else 1
    existing_settings = db.execute("SELECT id FROM user_settings WHERE user_id = ?", (uid,)).fetchone()
    if not existing_settings:
        db.execute(
            "INSERT INTO user_settings (user_id, city, city_name) VALUES (?, ?, ?)",
            (uid, 'Beijing', '北京')
        )

    db.commit()
    db.close()


if __name__ == '__main__':
    init_db()
    print(f"数据库已初始化: {DB_PATH}")
