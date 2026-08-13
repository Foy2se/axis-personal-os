"""工具函数 - 日期计算、ICS生成、导出导入、自动备份"""
from datetime import datetime, date, timedelta, timezone
import calendar
import os
import io
import json
import csv
import zipfile


# 用户本地时区：中国标准时间 (UTC+8)。
# 所有"当前时间/日期"统一使用该偏移，避免部署在 UTC 服务器（如 PythonAnywhere）时
# 时间比用户本地慢 8 小时（跨午夜时日期也会错位）。
CHINA_TZ_OFFSET = timedelta(hours=8)


def now_local():
    """返回用户本地时间（中国 UTC+8）的 naive datetime。"""
    return (datetime.now(timezone.utc) + CHINA_TZ_OFFSET).replace(tzinfo=None)


def today_str():
    return now_local().date().isoformat()


def now_str():
    return now_local().strftime('%Y-%m-%d %H:%M')


def safe_float(value, default=0.0):
    """安全地将表单值转为 float：兼容空字符串、'None'、逗号/空格分隔的数字。

    用于金额等字段，避免 float('') / float('None') 触发 500。
    """
    if value is None:
        return default
    s = str(value).strip().replace(',', '').replace(' ', '')
    if s == '' or s.lower() == 'none':
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """安全地将表单值转为 int（先按 float 解析，兼容 '5' / '5.0' / 空值）。"""
    try:
        return int(safe_float(value, default))
    except (ValueError, TypeError):
        return default


def calculate_next_date(last_done_str, cycle_num, cycle_unit):
    """计算周期事项的下次日期"""
    last = datetime.strptime(last_done_str, '%Y-%m-%d').date()
    if cycle_unit == '天':
        return (last + timedelta(days=cycle_num)).isoformat()
    elif cycle_unit == '周':
        return (last + timedelta(weeks=cycle_num)).isoformat()
    elif cycle_unit == '月':
        month = last.month - 1 + cycle_num
        year = last.year + month // 12
        month = month % 12 + 1
        day = min(last.day, calendar.monthrange(year, month)[1])
        return date(year, month, day).isoformat()
    elif cycle_unit == '年':
        try:
            return date(last.year + cycle_num, last.month, last.day).isoformat()
        except ValueError:
            # 2月29日情况
            return date(last.year + cycle_num, last.month, 28).isoformat()
    return last_done_str


def get_week_range(base_date=None):
    """获取本周范围（周一到周日）"""
    if base_date is None:
        base_date = date.today()
    elif isinstance(base_date, str):
        base_date = datetime.strptime(base_date, '%Y-%m-%d').date()
    monday = base_date - timedelta(days=base_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def get_month_days(year, month):
    """获取某月所有天"""
    _, num_days = calendar.monthrange(year, month)
    return [date(year, month, d) for d in range(1, num_days + 1)]


def get_week_days(base_date=None):
    """获取本周7天的日期列表"""
    monday, _ = get_week_range(base_date)
    return [monday + timedelta(days=i) for i in range(7)]


def parse_advance_days(advance_str):
    """解析提前提醒天数"""
    mapping = {'0天': 0, '1天': 1, '3天': 3, '7天': 7, '30天': 30}
    return mapping.get(advance_str, 3)


def _escape_ics_value(value):
    """转义 ICS 属性值中的特殊字符（RFC 5545）

    - 反斜杠 \\ → \\\\
    - 分号 ; → \\;
    - 逗号 , → \\,
    - 换行符 → \\n（字面反斜杠 n，ICS 标准的换行转义）
    """
    if not value:
        return ''
    return (str(value)
            .replace('\\', '\\\\')   # 反斜杠必须先转义
            .replace(';', '\\;')
            .replace(',', '\\,')
            .replace('\r\n', '\\n')  # Windows 换行
            .replace('\r', '\\n')
            .replace('\n', '\\n'))


def generate_ics():
    """生成自动化提醒的ICS日历文件内容（RFC 5545 兼容）

    关键规范：
    - 行尾使用 CRLF（\\r\\n）
    - 属性值中的特殊字符已转义
    - RRULE 属性完整正确（BYDAY/BYMONTHDAY 附加在同一行）
    """
    # 直接使用 CRLF 作为行尾
    CRLF = '\r\n'
    # ICS DTSTAMP 必须是 UTC（后缀 Z），与用户本地时区无关，使用显式 UTC 而非本地时间
    dtstamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    def make_event(uid, title, description, hour_start, minute_start,
                   hour_end, minute_end, freq, byday=None, interval=1,
                   month_day=None):
        esc_title = _escape_ics_value(title)
        esc_desc = _escape_ics_value(description)

        lines = [
            'BEGIN:VEVENT',
            f'UID:{uid}@personal-os',
            f'DTSTAMP:{dtstamp}',
            f'SUMMARY:{esc_title}',
            f'DESCRIPTION:{esc_desc}',
        ]
        # 使用本地时间格式（浮动时间，无 Z 后缀，跟随设备时区）
        today = date.today()
        lines.append(f'DTSTART:{today.strftime("%Y%m%d")}T{hour_start:02d}{minute_start:02d}00')
        lines.append(f'DTEND:{today.strftime("%Y%m%d")}T{hour_end:02d}{minute_end:02d}00')
        # RRULE 完整构建在单行内
        rrule = f'RRULE:FREQ={freq};INTERVAL={interval}'
        if byday:
            rrule += f';BYDAY={byday}'
        if month_day:
            rrule += f';BYMONTHDAY={month_day}'
        lines.append(rrule)
        lines.append('BEGIN:VALARM')
        lines.append('TRIGGER:-PT0M')
        lines.append('ACTION:DISPLAY')
        lines.append(f'DESCRIPTION:{esc_title}')
        lines.append('END:VALARM')
        lines.append('END:VEVENT')
        return CRLF.join(lines)

    events = []

    # 1. 每日上午9:00 今日规划
    events.append(make_event(
        'daily-planning', '开始今日规划',
        '打开今日任务页面\n填写今天最重要的三件事',
        9, 0, 9, 30, 'DAILY'
    ))

    # 2. 每日晚上18:50 工作日志
    events.append(make_event(
        'daily-worklog', '完成今日工作记录',
        '打开工作日志\n填写：今天完成 / 今天问题 / 明日重点',
        18, 50, 20, 0, 'DAILY'
    ))

    # 3. 每日晚上19:30 今晚计划引导
    events.append(make_event(
        'daily-evening-plan', '规划今晚个人时间',
        '工作日志已完成\n规划今晚：工作延续 / 学习成长 / 生活事项 / 兴趣娱乐',
        19, 30, 20, 0, 'DAILY'
    ))

    # 4. 每日晚上22:00 睡前确认今晚计划
    events.append(make_event(
        'daily-evening-review', '确认今晚计划完成情况',
        '睡前回顾\n未完成项可延后 / 重排 / 放弃',
        22, 0, 22, 30, 'DAILY'
    ))

    # 5. 每周日 周复盘
    events.append(make_event(
        'weekly-review', '完成周复盘',
        '本周完成\n未完成事项\n问题\n调整方向',
        20, 0, 21, 0, 'WEEKLY', byday='SU'
    ))

    # 6. 每月1号 月度规划
    events.append(make_event(
        'monthly-plan', '完成月度规划',
        '目标规划\n阅读计划\n消费规划\n生活计划',
        10, 0, 11, 0, 'MONTHLY', month_day=1
    ))

    ics_lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Personal OS//Personal OS V1.0//CN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        *events,
        'END:VCALENDAR',
    ]
    return CRLF.join(ics_lines) + CRLF


def get_stars(score, max_score=5):
    """生成星级显示"""
    if score is None:
        score = 0
    return '★' * score + '☆' * (max_score - score)


# ===================== 数据导出/导入 =====================

# 所有需要导出的表名
EXPORT_TABLES = [
    'tasks', 'work_logs', 'projects', 'project_reviews',
    'inbox', 'notes', 'goals', 'monthly_plans',
    'life_cycles', 'readings', 'learnings',
    'finance_monthly', 'big_expenses', 'purchase_decisions',
    'daily_health', 'cases', 'methodologies', 'viewpoints',
    'calendar_events', 'evening_plans',
    'decision_logs', 'body_rhythm', 'weather_cache',
    'daily_loop_state', 'ai_insights', 'maintenance_items'
]

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')


def export_all_data(user_id=None):
    """导出所有表数据为字典（按用户过滤）"""
    from models import get_db
    db = get_db()
    data = {}
    for table in EXPORT_TABLES:
        if user_id:
            rows = db.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchall()
        else:
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = [dict(row) for row in rows]

    user_info = None
    if user_id:
        user_info = db.execute("SELECT email, name FROM users WHERE id = ?", (user_id,)).fetchone()
        user_info = dict(user_info) if user_info else None

    db.close()
    return {
        "version": "3.0",
        "user": user_info,
        "exported_at": now_local().isoformat(),
        "table_count": len(EXPORT_TABLES),
        "tables": data
    }


def import_all_data(json_data, mode='replace', user_id=None):
    """从JSON数据导入（按用户隔离）
    mode: 'replace' 清空后导入, 'merge' 追加导入
    """
    from models import get_db
    db = get_db()
    imported = {}

    for table in EXPORT_TABLES:
        if table not in json_data.get('tables', {}):
            continue

        rows = json_data['tables'][table]
        if not rows:
            imported[table] = 0
            continue

        if mode == 'replace':
            if user_id:
                db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            else:
                db.execute(f"DELETE FROM {table}")

        # 获取列名，过滤掉 user_id（用当前用户的）
        col_names = [c for c in rows[0].keys() if c != 'user_id']
        col_names_str = ', '.join(['user_id'] + col_names)
        placeholders = ', '.join(['?'] * (len(col_names) + 1))

        count = 0
        for row in rows:
            values = [user_id or 1] + [row.get(col) for col in col_names]
            try:
                db.execute(
                    f"INSERT OR REPLACE INTO {table} ({col_names_str}) VALUES ({placeholders})",
                    values
                )
                count += 1
            except Exception:
                pass
        imported[table] = count

    db.commit()
    db.close()
    return imported


def export_csv_data(user_id):
    """导出CSV格式（zip包，每张表一个CSV文件）"""
    from models import get_db
    import csv
    db = get_db()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for table in EXPORT_TABLES:
            rows = db.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,)).fetchall()
            if not rows:
                continue
            csv_buf = io.StringIO()
            col_names = rows[0].keys()
            writer = csv.DictWriter(csv_buf, fieldnames=col_names)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
            zf.writestr(f"{table}.csv", csv_buf.getvalue())

    db.close()
    buf.seek(0)
    return buf


def export_markdown_data(user_id):
    """导出Markdown格式（zip包，按内容类型组织目录）"""
    from models import get_db
    db = get_db()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # README 索引
        readme = "# Personal OS 数据导出\n\n"
        readme += f"导出时间: {now_local().strftime('%Y-%m-%d %H:%M')}\n\n"
        readme += "## 目录结构\n\n"
        readme += "- `notes/` - 思考笔记（按分类组织）\n"
        readme += "- `work_logs/` - 工作日志（按日期）\n"
        readme += "- `inbox/` - 灵感收集\n"
        readme += "- `projects/` - 项目与复盘\n"
        readme += "- `goals/` - 目标规划\n"
        readme += "- `archive/` - 知识资产（案例/方法论/观点）\n"
        readme += "- `evening_plans/` - 今晚计划\n"
        readme += "- `finance/` - 财务记录\n"
        readme += "- `health/` - 健康记录\n"
        readme += "- `reading/` - 阅读计划\n"
        readme += "- `learning/` - 学习计划\n"
        readme += "- `life_cycles/` - 周期事项\n"
        zf.writestr("README.md", readme)

        # 思考笔记
        notes = db.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        for n in notes:
            category = n['category'] or '其他'
            title = _safe_filename(n['title'])
            md = f"# {n['title']}\n\n"
            md += f"**分类:** {category}\n"
            if n['tags']:
                md += f"**标签:** {n['tags']}\n"
            md += f"**创建时间:** {n['created_at']}\n\n"
            md += f"{n['content'] or ''}\n"
            zf.writestr(f"notes/{category}/{title}.md", md)

        # 工作日志
        logs = db.execute("SELECT * FROM work_logs WHERE user_id = ? ORDER BY log_date DESC", (user_id,)).fetchall()
        for l in logs:
            md = f"# 工作日志 {l['log_date']}\n\n"
            if l['completed']:
                md += f"## 今日完成\n{l['completed']}\n\n"
            if l['problems']:
                md += f"## 遇到的问题\n{l['problems']}\n\n"
            if l['thoughts']:
                md += f"## 新思考\n{l['thoughts']}\n\n"
            if l['tomorrow_focus']:
                md += f"## 明日重点\n{l['tomorrow_focus']}\n\n"
            zf.writestr(f"work_logs/{l['log_date']}.md", md)

        # 灵感收集
        inbox_items = db.execute("SELECT * FROM inbox WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        for item in inbox_items:
            title = _safe_filename(item['title'] or f"灵感_{item['id']}")
            md = f"# {item['title'] or '无标题'}\n\n"
            if item['source']:
                md += f"**来源:** {item['source']}\n"
            if item['tags']:
                md += f"**标签:** {item['tags']}\n"
            md += f"**创建时间:** {item['created_at']}\n\n"
            md += f"{item['content'] or ''}\n"
            zf.writestr(f"inbox/{title}.md", md)

        # 项目与复盘
        projects = db.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        for p in projects:
            proj_dir = _safe_filename(p['name'])
            md = f"# {p['name']}\n\n"
            md += f"**目标:** {p['objective'] or ''}\n"
            md += f"**阶段:** {p['stage']}\n"
            md += f"**周期:** {p['start_date'] or ''} ~ {p['end_date'] or ''}\n\n"
            zf.writestr(f"projects/{proj_dir}/项目信息.md", md)

            review = db.execute("SELECT * FROM project_reviews WHERE project_id = ? AND user_id = ?", (p['id'], user_id)).fetchone()
            if review:
                rmd = f"# {p['name']} - 项目复盘\n\n"
                rmd += f"## 项目目标\n{review['objective'] or ''}\n\n"
                rmd += f"## 最终结果\n{review['result'] or ''}\n\n"
                rmd += f"## 完成情况\n{review['completion'] or ''}\n\n"
                rmd += f"## 做得好的地方\n{review['good_points'] or ''}\n\n"
                rmd += f"## 不足的地方\n{review['bad_points'] or ''}\n\n"
                rmd += f"## 经验总结\n{review['experience'] or ''}\n\n"
                rmd += f"## 未来优化\n{review['optimization'] or ''}\n"
                zf.writestr(f"projects/{proj_dir}/复盘.md", rmd)

        # 目标规划
        goals = db.execute("SELECT * FROM goals WHERE user_id = ? ORDER BY level, created_at DESC", (user_id,)).fetchall()
        goals_md = "# 目标规划\n\n"
        for g in goals:
            goals_md += f"## {g['name']}（{g['level']}）\n"
            goals_md += f"- **状态:** {g['status']}\n"
            goals_md += f"- **进度:** {g['progress']}%\n"
            if g['period']:
                goals_md += f"- **周期:** {g['period']}\n"
            if g['description']:
                goals_md += f"- **描述:** {g['description']}\n"
            goals_md += "\n"
        zf.writestr("goals/目标规划.md", goals_md)

        # 知识资产
        for table, folder, title_col, content_col in [
            ('cases', 'cases', 'name', 'analysis'),
            ('methodologies', 'methods', 'title', 'content'),
            ('viewpoints', 'viewpoints', 'title', 'content'),
        ]:
            items = db.execute(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
            for item in items:
                title = _safe_filename(item[title_col])
                md = f"# {item[title_col]}\n\n"
                if 'tags' in item.keys() and item['tags']:
                    md += f"**标签:** {item['tags']}\n"
                if 'industry' in item.keys() and item['industry']:
                    md += f"**行业:** {item['industry']}\n"
                if 'type' in item.keys() and item['type']:
                    md += f"**类型:** {item['type']}\n"
                md += f"**创建时间:** {item['created_at']}\n\n"
                md += f"{item[content_col] or ''}\n"
                zf.writestr(f"archive/{folder}/{title}.md", md)

        # 今晚计划
        plans = db.execute("SELECT * FROM evening_plans WHERE user_id = ? ORDER BY plan_date DESC", (user_id,)).fetchall()
        plans_md = "# 今晚计划记录\n\n"
        for p in plans:
            plans_md += f"## {p['plan_date']} - {p['name']}\n"
            plans_md += f"- **分类:** {p['category']}\n"
            plans_md += f"- **状态:** {p['status']}\n"
            if p['estimated_time']:
                plans_md += f"- **预计时间:** {p['estimated_time']}\n"
            plans_md += "\n"
        if plans:
            zf.writestr("evening_plans/今晚计划.md", plans_md)

        # 财务
        expenses = db.execute("SELECT * FROM big_expenses WHERE user_id = ? ORDER BY expense_date DESC", (user_id,)).fetchall()
        fin_md = "# 大额消费记录\n\n| 商品 | 金额 | 分类 | 日期 | 满意度 |\n|------|------|------|------|--------|\n"
        for e in expenses:
            stars = '★' * (e['satisfaction'] or 0)
            fin_md += f"| {e['item_name']} | ¥{e['amount']} | {e['category']} | {e['expense_date'] or ''} | {stars} |\n"
        zf.writestr("finance/大额消费.md", fin_md)

        # 健康
        health = db.execute("SELECT * FROM daily_health WHERE user_id = ? ORDER BY record_date DESC", (user_id,)).fetchall()
        health_md = "# 健康记录\n\n| 日期 | 睡眠 | 精力 | 状态 | 备注 |\n|------|------|------|------|------|\n"
        for h in health:
            health_md += f"| {h['record_date']} | {'★'*h['sleep_score'] if h['sleep_score'] else '-'} | {'★'*h['energy_score'] if h['energy_score'] else '-'} | {'★'*h['status_score'] if h['status_score'] else '-'} | {h['note'] or ''} |\n"
        zf.writestr("health/健康记录.md", health_md)

        # 阅读
        books = db.execute("SELECT * FROM readings WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        read_md = "# 阅读计划\n\n| 书名 | 作者 | 状态 | 目标 |\n|------|------|------|------|\n"
        for b in books:
            read_md += f"| {b['book_name']} | {b['author'] or ''} | {b['reading_status']} | {b['reading_goal'] or ''} |\n"
        zf.writestr("reading/阅读计划.md", read_md)

        # 周期事项
        cycles = db.execute("SELECT * FROM life_cycles WHERE user_id = ? ORDER BY next_date ASC", (user_id,)).fetchall()
        cycle_md = "# 周期事项\n\n| 事项 | 分类 | 周期 | 下次日期 | 状态 |\n|------|------|------|---------|------|\n"
        for c in cycles:
            cycle_md += f"| {c['name']} | {c['category']} | {c['cycle_number']}{c['cycle_unit']} | {c['next_date']} | {c['status']} |\n"
        zf.writestr("life_cycles/周期事项.md", cycle_md)

    db.close()
    buf.seek(0)
    return buf


def _safe_filename(name):
    """生成安全的文件名"""
    if not name:
        return 'untitled'
    # 替换文件系统不安全的字符
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\n', '\r']:
        name = name.replace(ch, '_')
    return name[:80]


# ===================== 自动备份 =====================

def auto_backup(user_id):
    """自动备份数据库到本地目录，每天最多一次"""
    from models import get_db
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = today_str()

    db = get_db()
    # 检查今天是否已备份
    existing = db.execute(
        "SELECT id FROM backups WHERE user_id = ? AND backup_type = 'auto' AND date(created_at) = date('now')",
        (user_id,)
    ).fetchone()

    if existing:
        db.close()
        return {'status': 'skipped', 'message': '今日已自动备份'}

    # 执行备份（导出当前用户的JSON数据）
    data = export_all_data(user_id)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    user_backup_dir = os.path.join(BACKUP_DIR, f'user_{user_id}')
    os.makedirs(user_backup_dir, exist_ok=True)
    file_path = os.path.join(user_backup_dir, f'backup_{today}.json')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(json_str)

    file_size = os.path.getsize(file_path)

    # 记录备份
    db.execute(
        "INSERT INTO backups (user_id, backup_type, file_path, file_size) VALUES (?, 'auto', ?, ?)",
        (user_id, file_path, file_size)
    )
    db.commit()

    # 清理30天前的备份
    cleanup_old_backups(user_id, days=30)

    # 预留云备份接口
    cloud_backup_hook(user_id, file_path)

    db.close()
    return {'status': 'success', 'file_path': file_path, 'file_size': file_size}


def cleanup_old_backups(user_id, days=30):
    """清理过期备份"""
    from models import get_db
    db = get_db()
    cutoff = (now_local() - timedelta(days=days)).strftime('%Y-%m-%d')
    old_backups = db.execute(
        "SELECT * FROM backups WHERE user_id = ? AND date(created_at) < ?",
        (user_id, cutoff)
    ).fetchall()

    for b in old_backups:
        if b['file_path'] and os.path.exists(b['file_path']):
            try:
                os.remove(b['file_path'])
            except Exception:
                pass
        db.execute("DELETE FROM backups WHERE id = ?", (b['id'],))

    db.commit()
    db.close()
    return len(old_backups)


def get_backup_history(user_id, limit=30):
    """获取备份历史"""
    from models import get_db
    db = get_db()
    backups = db.execute(
        "SELECT * FROM backups WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    db.close()
    return backups


def cloud_backup_hook(user_id, backup_path):
    """云备份预留接口 - 未来接入 iCloud / 第三方云存储

    可选实现：
    - 上传到 AWS S3 / 阿里云 OSS
    - 同步到 iCloud Drive
    - 推送到 Google Drive / Dropbox
    """
    # TODO: 实现云备份逻辑
    pass


# ===================== AXIS 3.0 新增：天气模块 =====================

import requests


def get_user_settings(user_id):
    """获取用户设置，不存在则创建默认"""
    from models import get_db
    db = get_db()
    row = db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        db.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        db.commit()
        row = db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    db.close()
    return dict(row)


def save_user_settings(user_id, data):
    """保存用户设置"""
    from models import get_db
    db = get_db()
    fields = []
    values = []
    for col in ['city', 'city_name', 'life_direction', 'current_stage_goal',
                'work_hours_start', 'work_hours_end', 'daily_loop_enabled']:
        if col in data:
            fields.append(f"{col} = ?")
            values.append(data[col])
    if not fields:
        db.close()
        return False
    values.append(user_id)
    db.execute(f"UPDATE user_settings SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", values)
    db.commit()
    db.close()
    return True


def get_weather(city='Beijing', city_name='北京', user_id=None):
    """获取天气，优先从缓存读取（1小时），否则调用 Open-Meteo"""
    from models import get_db
    db = get_db()
    today = today_str()
    now = now_local()

    # 检查缓存
    if user_id:
        cached = db.execute(
            "SELECT * FROM weather_cache WHERE user_id = ? AND city = ? AND cached_at > datetime('now', '-1 hour') ORDER BY cached_at DESC LIMIT 1",
            (user_id, city)
        ).fetchone()
        if cached:
            try:
                data = json.loads(cached['data'])
                data['from_cache'] = True
                db.close()
                return data
            except Exception:
                pass

    # 调用 Open-Meteo（无需 API key）
    try:
        # 先通过 geocoding 获取坐标
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh&format=json"
        geo_resp = requests.get(geo_url, timeout=10)
        geo_data = geo_resp.json()
        if not geo_data.get('results'):
            db.close()
            return _fallback_weather(city_name)
        lat = geo_data['results'][0]['latitude']
        lon = geo_data['results'][0]['longitude']
        display_name = geo_data['results'][0].get('name', city_name)

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,is_day"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min"
            f"&timezone=auto&forecast_days=2"
        )
        w_resp = requests.get(weather_url, timeout=10)
        w_data = w_resp.json()

        current = w_data.get('current', {})
        daily = w_data.get('daily', {})
        weather_code = current.get('weather_code', 0)

        result = {
            'city': city,
            'city_name': display_name,
            'temperature': current.get('temperature_2m'),
            'humidity': current.get('relative_humidity_2m'),
            'is_day': current.get('is_day', 1),
            'weather_code': weather_code,
            'condition': _weather_code_to_text(weather_code),
            'icon': _weather_code_to_icon(weather_code, current.get('is_day', 1)),
            'today_max': daily.get('temperature_2m_max', [None])[0],
            'today_min': daily.get('temperature_2m_min', [None])[0],
            'tomorrow_max': daily.get('temperature_2m_max', [None, None])[1],
            'tomorrow_min': daily.get('temperature_2m_min', [None, None])[1],
            'tomorrow_code': daily.get('weather_code', [None, None])[1],
            'unit': '°C',
            'from_cache': False,
            'updated_at': now.strftime('%H:%M')
        }

        # 写入缓存
        if user_id:
            db.execute("DELETE FROM weather_cache WHERE user_id = ? AND city = ?", (user_id, city))
            db.execute(
                "INSERT INTO weather_cache (user_id, city, data, cached_at) VALUES (?, ?, ?, ?)",
                (user_id, city, json.dumps(result, ensure_ascii=False), now)
            )
            db.commit()

        db.close()
        return result
    except Exception as e:
        db.close()
        return _fallback_weather(city_name, error=str(e))


def _fallback_weather(city_name, error=None):
    return {
        'city_name': city_name,
        'temperature': '--',
        'condition': '获取失败',
        'icon': '❓',
        'today_max': None,
        'today_min': None,
        'unit': '°C',
        'from_cache': False,
        'error': error
    }


def _weather_code_to_text(code):
    """WMO Weather interpretation codes (WW)"""
    codes = {
        0: '晴朗', 1: '大部晴朗', 2: '多云', 3: '阴天',
        45: '雾', 48: '雾凇',
        51: '毛毛雨', 53: '中度毛毛雨', 55: '大毛毛雨',
        56: '冻毛毛雨', 57: '强冻毛毛雨',
        61: '小雨', 63: '中雨', 65: '大雨',
        66: '冻雨', 67: '强冻雨',
        71: '小雪', 73: '中雪', 75: '大雪',
        77: '雪粒',
        80: '小阵雨', 81: '中阵雨', 82: '强阵雨',
        85: '小阵雪', 86: '强阵雪',
        95: '雷雨', 96: '雷雨伴冰雹', 99: '强雷雨伴冰雹'
    }
    return codes.get(code, '未知')


def _weather_code_to_icon(code, is_day=1):
    sun = '☀️'
    moon = '🌙'
    icons = {
        0: sun if is_day else moon,
        1: '🌤️',
        2: '⛅',
        3: '☁️',
        45: '🌫️', 48: '🌫️',
        51: '🌦️', 53: '🌦️', 55: '🌧️',
        56: '🌧️', 57: '🌧️',
        61: '🌧️', 63: '🌧️', 65: '🌧️',
        66: '🌨️', 67: '🌨️',
        71: '🌨️', 73: '🌨️', 75: '🌨️',
        77: '🌨️',
        80: '🌦️', 81: '🌧️', 82: '🌧️',
        85: '🌨️', 86: '🌨️',
        95: '⛈️', 96: '⛈️', 99: '⛈️'
    }
    return icons.get(code, sun if is_day else moon)


# ===================== AXIS 3.0 新增：Daily Loop =====================

def get_daily_loop_state(user_id, loop_date=None):
    """获取某日的 Daily Loop 状态"""
    from models import get_db
    if loop_date is None:
        loop_date = today_str()
    db = get_db()
    row = db.execute(
        "SELECT * FROM daily_loop_state WHERE user_id = ? AND loop_date = ?",
        (user_id, loop_date)
    ).fetchone()
    if not row:
        db.execute(
            "INSERT INTO daily_loop_state (user_id, loop_date) VALUES (?, ?)",
            (user_id, loop_date)
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM daily_loop_state WHERE user_id = ? AND loop_date = ?",
            (user_id, loop_date)
        ).fetchone()
    db.close()
    return dict(row)


def update_daily_loop_state(user_id, loop_date, field, value):
    """更新 Daily Loop 状态字段"""
    from models import get_db
    db = get_db()
    # 确保记录存在
    existing = db.execute(
        "SELECT id FROM daily_loop_state WHERE user_id = ? AND loop_date = ?",
        (user_id, loop_date)
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO daily_loop_state (user_id, loop_date) VALUES (?, ?)",
            (user_id, loop_date)
        )
    allowed = {'morning_completed', 'evening_completed', 'sleep_completed',
               'morning_at', 'evening_at', 'sleep_at'}
    if field in allowed:
        db.execute(
            f"UPDATE daily_loop_state SET {field} = ? WHERE user_id = ? AND loop_date = ?",
            (value, user_id, loop_date)
        )
        db.commit()
    db.close()


def get_current_loop_phase(user_id):
    """判断当前应显示的 loop 阶段：morning / evening / sleep / none"""
    from models import get_db
    now = now_local()
    hour = now.hour
    minute = now.minute
    settings = get_user_settings(user_id)
    state = get_daily_loop_state(user_id)

    # 解析工作时间
    try:
        work_start = datetime.strptime(settings.get('work_hours_start', '09:00'), '%H:%M').time()
        work_end = datetime.strptime(settings.get('work_hours_end', '18:00'), '%H:%M').time()
    except Exception:
        work_start = datetime.strptime('09:00', '%H:%M').time()
        work_end = datetime.strptime('18:00', '%H:%M').time()

    current_time = now.time()

    # Morning: 工作日开始前 30 分钟到工作开始 1 小时后
    morning_start = (datetime.combine(date.today(), work_start) - timedelta(minutes=30)).time()
    morning_end = (datetime.combine(date.today(), work_start) + timedelta(hours=1)).time()

    # Evening: 工作结束前 10 分钟到 21:00
    evening_start = (datetime.combine(date.today(), work_end) - timedelta(minutes=10)).time()
    evening_end = datetime.strptime('21:00', '%H:%M').time()

    # Sleep: 21:00 到 23:59
    sleep_start = datetime.strptime('21:00', '%H:%M').time()

    if morning_start <= current_time <= morning_end and not state.get('morning_completed'):
        return 'morning'
    if evening_start <= current_time <= evening_end and not state.get('evening_completed'):
        return 'evening'
    if current_time >= sleep_start and not state.get('sleep_completed'):
        return 'sleep'

    return 'none'


# ===================== AXIS 3.0 新增：AI Insight 规则引擎 =====================

def generate_ai_insights(user_id):
    """基于本地数据生成 AI 洞察，返回洞察列表"""
    from models import get_db
    db = get_db()
    today = today_str()
    insights = []

    # 1. 睡眠提醒
    recent_health = db.execute(
        "SELECT * FROM daily_health WHERE user_id = ? AND record_date >= date('now', '-3 days') ORDER BY record_date DESC",
        (user_id,)
    ).fetchall()
    low_sleep_days = [h for h in recent_health if h['sleep_score'] and h['sleep_score'] <= 2]
    if len(low_sleep_days) >= 2:
        insights.append({
            'type': 'health',
            'title': '连续睡眠质量偏低',
            'content': f'最近 {len(low_sleep_days)} 天睡眠评分≤2星，建议今晚提前 30 分钟入睡，避免睡前使用屏幕。',
            'priority': '高'
        })

    # 2. 高优先级任务堆积
    high_tasks = db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND priority = '高' AND status != '已完成'",
        (user_id,)
    ).fetchone()['c']
    if high_tasks >= 3:
        insights.append({
            'type': 'task',
            'title': f'有 {high_tasks} 个高优先级任务待处理',
            'content': '高优先级任务堆积可能影响核心目标推进，建议从最重要的一项开始。',
            'priority': '高'
        })

    # 3. 周期事项提醒
    due_cycles = db.execute(
        "SELECT * FROM life_cycles WHERE user_id = ? AND status = 'active' AND next_date <= ? ORDER BY next_date ASC LIMIT 3",
        (user_id, today)
    ).fetchall()
    for c in due_cycles:
        insights.append({
            'type': 'cycle',
            'title': f'周期事项到期：{c["name"]}',
            'content': f'该事项已于 {c["next_date"]} 到期，建议尽快处理。',
            'priority': '中'
        })

    # 4. 目标偏离提醒
    active_goals = db.execute(
        "SELECT * FROM goals WHERE user_id = ? AND status = '进行中' AND progress < 20 ORDER BY created_at DESC LIMIT 3",
        (user_id,)
    ).fetchall()
    old_goals = [g for g in active_goals if g['created_at'] and g['created_at'] < (now_local() - timedelta(days=30)).isoformat()]
    if old_goals:
        names = '、'.join([g['name'] for g in old_goals[:2]])
        insights.append({
            'type': 'goal',
            'title': '长期目标推进缓慢',
            'content': f'「{names}」等目标创建超过30天但进度仍低于20%，建议拆解为更小的行动步骤。',
            'priority': '中'
        })

    # 5. 工作记录缺失
    today_log = db.execute(
        "SELECT id FROM work_logs WHERE user_id = ? AND log_date = ?",
        (user_id, today)
    ).fetchone()
    if not today_log:
        now = now_local()
        if now.hour >= 18:
            insights.append({
                'type': 'work',
                'title': '今日工作记录尚未完成',
                'content': '现在是晚间回顾时间，记录今天的工作可以帮助 AI 整理和规划明天。',
                'priority': '中'
            })

    # 6. 今日 focus 建议
    focus_count = db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND scheduled_date = ? AND status != '已完成'",
        (user_id, today)
    ).fetchone()['c']
    if focus_count == 0:
        insights.append({
            'type': 'focus',
            'title': '今日尚未设定重点任务',
            'content': '设定 1-3 个 Today Focus 可以让一天更有方向感。',
            'priority': '低'
        })

    db.close()

    # 写入/更新 ai_insights 表（未 dismiss 的）
    _save_ai_insights(user_id, insights)
    return insights


def _save_ai_insights(user_id, insights):
    """保存洞察到数据库，同一天同类型同标题不重复"""
    from models import get_db
    db = get_db()
    today = today_str()
    for ins in insights:
        existing = db.execute(
            "SELECT id FROM ai_insights WHERE user_id = ? AND type = ? AND title = ? AND date(created_at) = ? AND dismissed = 0",
            (user_id, ins['type'], ins['title'], today)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO ai_insights (user_id, type, title, content, priority) VALUES (?, ?, ?, ?, ?)",
                (user_id, ins['type'], ins['title'], ins['content'], ins.get('priority', '中'))
            )
    db.commit()
    db.close()


def get_recent_ai_insights(user_id, limit=5):
    """获取最近未忽略的洞察"""
    from models import get_db
    db = get_db()
    rows = db.execute(
        "SELECT * FROM ai_insights WHERE user_id = ? AND dismissed = 0 ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def dismiss_ai_insight(insight_id, user_id):
    """忽略某条洞察"""
    from models import get_db
    db = get_db()
    db.execute(
        "UPDATE ai_insights SET dismissed = 1 WHERE id = ? AND user_id = ?",
        (insight_id, user_id)
    )
    db.commit()
    db.close()


# ===================== AXIS 3.0 新增：任务自动迁移 =====================

def migrate_overdue_tasks(user_id):
    """将昨日及之前的未完成任务自动迁移到今天，仅迁移一次"""
    from models import get_db
    db = get_db()
    today = today_str()

    # 找出昨天及之前未完成、且未自动迁移过的任务
    overdue = db.execute(
        """SELECT * FROM tasks WHERE user_id = ? AND status != '已完成'
           AND scheduled_date < ? AND (auto_migrated = 0 OR auto_migrated IS NULL)
           ORDER BY priority DESC, deadline ASC""",
        (user_id, today)
    ).fetchall()

    migrated = 0
    for t in overdue:
        db.execute(
            "UPDATE tasks SET scheduled_date = ?, auto_migrated = 1 WHERE id = ?",
            (today, t['id'])
        )
        migrated += 1

    db.commit()
    db.close()
    return migrated


# ===================== AXIS 3.0 新增：AI 自动分类 =====================

def categorize_inbox(text):
    """根据关键词给灵感自动分类"""
    if not text:
        return '其他'
    text = text.lower()
    categories = {
        '设计': ['设计', 'ui', 'ux', '界面', '视觉', 'figma', '原型', '排版', '色彩'],
        '商业': ['商业', '商业模式', '创业', '产品', '盈利', '市场', '客户', '用户增长', '运营', '营销'],
        '生活': ['生活', '家居', '旅行', '饮食', '健康', '家庭', '朋友', '关系', '爬山', '运动', '周末', '购物', '烹饪'],
        '成长': ['学习', '成长', '技能', '阅读', '课程', '知识', '认知', '习惯', '自律', '反思'],
        '技术': ['代码', '开发', '技术', '编程', 'python', '架构', 'api', '数据库', '算法', '部署']
    }
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in categories.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else '其他'


def summarize_work_log(completed, problems, thoughts):
    """基于工作记录内容生成 AI 整理摘要"""
    lines = []
    if completed:
        items = [line.strip() for line in completed.split('\n') if line.strip()]
        if items:
            lines.append('完成事项：' + '；'.join(items[:5]))
    if problems:
        lines.append('待解决问题：' + problems.strip()[:80])
    if thoughts:
        lines.append('关键思考：' + thoughts.strip()[:80])
    if not lines:
        return '今日暂无工作记录。'
    return '\n'.join(lines)


def get_greeting_by_time():
    """根据当前时间返回问候语"""
    hour = now_local().hour
    if hour < 6:
        return '夜深了', 'Good Night'
    elif hour < 11:
        return '早安', 'Morning'
    elif hour < 14:
        return '午安', 'Afternoon'
    elif hour < 19:
        return '下午好', 'Afternoon'
    else:
        return '晚上好', 'Evening'
