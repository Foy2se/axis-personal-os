"""Personal OS V3.0 - Flask 主应用（账号系统+多设备同步+多格式导出）"""
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, send_file, session
from models import get_db, init_db, CONTENT_TABLES, get_categories, SYSTEM_CATEGORY
from auth import (hash_password, verify_password, create_session, destroy_session,
                  get_current_user, login_required, get_user_id)
from utils import (today_str, now_str, calculate_next_date, get_week_range,
                   get_week_days, get_month_days, parse_advance_days,
                   generate_ics, get_stars, export_all_data, import_all_data,
                   export_csv_data, export_markdown_data, auto_backup,
                   cleanup_old_backups, get_backup_history,
                   get_user_settings, save_user_settings, get_weather,
                   get_daily_loop_state, update_daily_loop_state, get_current_loop_phase,
                   generate_ai_insights, get_recent_ai_insights, dismiss_ai_insight,
                   migrate_overdue_tasks, categorize_inbox, summarize_work_log,
                   get_greeting_by_time)
from datetime import datetime, date, timedelta
import calendar
import json
import io
import os
import zipfile

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'personal-os-v3-secret')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# 静态文件缓存策略：图标不缓存（便于更新）；其余静态资源缓存 10 分钟，加速重复访问
@app.after_request
def add_header(response):
    if request.path.startswith('/static/'):
        if request.path.startswith('/static/icons/'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        else:
            # 静态资源缓存 1 天，减少页面切换时的重复下载（手机端提速明显）
            response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

# 启动时初始化数据库
init_db()

# 允许访问的路由（无需登录）
PUBLIC_ENDPOINTS = {'login', 'register', 'logout', 'static', 'manifest', 'sw', 'splash', 'ping'}


# ===================== 请求前钩子 =====================
@app.before_request
def require_login():
    """自动登录默认用户，跳过登录页"""
    if not get_current_user():
        # 自动设置 session 为默认用户（user_id=1）
        session['user_id'] = 1
        session.permanent = True


# ===================== 全局上下文 =====================
@app.context_processor
def inject_globals():
    user = get_current_user()
    return dict(active_page='', today=today_str(), current_user=user)


# ===================== 认证路由 =====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        next_url = request.form.get('next', '') or url_for('dashboard')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user and verify_password(password, user['password_hash']):
            create_session(user['id'], remember=remember)
            return redirect(next_url)
        return render_template('login.html', error='邮箱或密码错误', next=next_url)
    return render_template('login.html', next=request.args.get('next', ''))


@app.route('/register', methods=['POST'])
def register():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    name = request.form.get('name', '')

    if len(password) < 6:
        return render_template('login.html', error='密码至少6位', next='')

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return render_template('login.html', error='该邮箱已注册', next='')

    user_id = db.execute(
        "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
        (email, hash_password(password), name or email.split('@')[0])
    ).lastrowid
    db.commit()
    db.close()

    create_session(user_id, remember=True)
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    destroy_session()
    return redirect(url_for('login'))


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    uid = get_user_id()
    old_pwd = request.form.get('old_password', '')
    new_pwd = request.form.get('new_password', '')

    if len(new_pwd) < 6:
        return redirect(url_for('settings', msg='error|新密码至少6位'))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not verify_password(old_pwd, user['password_hash']):
        db.close()
        return redirect(url_for('settings', msg='error|原密码错误'))

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_pwd), uid))
    db.commit()
    db.close()
    return redirect(url_for('settings', msg='success|密码修改成功'))


# ===================== 首页 Dashboard =====================
@app.route('/app-direct')
def app_direct():
    """直接入口 - 不经过 axis-app.html，不注册 SW，直接渲染首页"""
    # 自动登录
    if not get_current_user():
        session['user_id'] = 1
        session.permanent = True
    
    # 直接渲染 dashboard，不经过 iframe
    return redirect('/?pwa=1&direct=1')


@app.route('/')
def dashboard():
    uid = get_user_id()
    db = get_db()
    today = today_str()
    now = datetime.now()

    # AXIS 3.0: 自动迁移昨日未完成任务
    migrate_overdue_tasks(uid)

    # 用户设置
    settings = get_user_settings(uid)

    # 问候语
    greeting, greeting_en = get_greeting_by_time()

    # Personal Status: 今日健康
    today_health = db.execute(
        "SELECT * FROM daily_health WHERE record_date = ? AND user_id = ?", (today, uid)
    ).fetchone()

    # Weather
    weather = get_weather(
        city=settings.get('city') or 'Beijing',
        city_name=settings.get('city_name') or '北京',
        user_id=uid
    )

    # Today Focus（按 Work / Life / Growth 分类）
    focus_categories = {'Work': '工作', 'Life': '生活', 'Growth': '成长'}
    today_focus = {}
    for fc, type_name in focus_categories.items():
        rows = db.execute(
            """SELECT * FROM tasks WHERE user_id = ? AND status != '已完成'
               AND focus_category = ? AND (scheduled_date = ? OR scheduled_date IS NULL)
               ORDER BY priority DESC, created_at ASC LIMIT 3""",
            (uid, fc, today)
        ).fetchall()
        today_focus[fc] = rows

    # Timeline：今日事件 + 周期事项 + 任务
    today_events = db.execute(
        "SELECT * FROM calendar_events WHERE event_date = ? AND user_id = ? ORDER BY event_time",
        (today, uid)
    ).fetchall()

    today_tasks_for_timeline = db.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND scheduled_date = ? AND status != '已完成' ORDER BY priority DESC LIMIT 10",
        (uid, today)
    ).fetchall()

    due_cycles = db.execute(
        "SELECT * FROM life_cycles WHERE user_id = ? AND status = 'active' AND next_date <= ? ORDER BY next_date ASC LIMIT 5",
        (uid, today)
    ).fetchall()

    # 今日今晚安排（显示在时间线中）
    today_evening_plans = db.execute(
        "SELECT * FROM evening_plans WHERE plan_date = ? AND user_id = ? AND status = '待执行' ORDER BY priority DESC, created_at ASC",
        (today, uid)
    ).fetchall()

    # Daily Loop
    loop_state = get_daily_loop_state(uid, today)
    current_loop_phase = get_current_loop_phase(uid)

    # AXIS Insight
    generate_ai_insights(uid)
    ai_insights = get_recent_ai_insights(uid)

    # 今日工作日志
    today_log = db.execute(
        "SELECT * FROM work_logs WHERE log_date = ? AND user_id = ?", (today, uid)
    ).fetchone()

    # 快速统计
    stats = {
        'today_tasks': len(today_tasks_for_timeline),
        'completed_tasks': db.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE user_id = ? AND status = '已完成' AND date(completed_at) = ?",
            (uid, today)
        ).fetchone()['c'],
        'due_cycles': len(due_cycles),
        'today_log': bool(today_log)
    }

    db.close()

    return render_template('dashboard.html',
        active_page='dashboard',
        today=today,
        now=now,
        greeting=greeting,
        greeting_en=greeting_en,
        today_health=today_health,
        weather=weather,
        today_focus=today_focus,
        today_events=today_events,
        today_tasks_for_timeline=today_tasks_for_timeline,
        due_cycles=due_cycles,
        today_evening_plans=today_evening_plans,
        loop_state=loop_state,
        current_loop_phase=current_loop_phase,
        ai_insights=ai_insights,
        today_log=today_log,
        stats=stats,
        settings=settings,
        get_stars=get_stars)


# ===================== Daily Loop & Insight =====================
@app.route('/daily-loop/complete', methods=['POST'])
@login_required
def daily_loop_complete():
    """标记 Daily Loop 某阶段完成"""
    uid = get_user_id()
    phase = request.form.get('phase')
    today = today_str()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    field_map = {
        'morning': ('morning_completed', 'morning_at'),
        'evening': ('evening_completed', 'evening_at'),
        'sleep': ('sleep_completed', 'sleep_at')
    }
    if phase in field_map:
        complete_field, at_field = field_map[phase]
        update_daily_loop_state(uid, today, complete_field, 1)
        update_daily_loop_state(uid, today, at_field, now)
    return redirect(url_for('dashboard'))


@app.route('/insight/<int:iid>/dismiss', methods=['POST'])
@login_required
def insight_dismiss(iid):
    """忽略 AI 洞察"""
    dismiss_ai_insight(iid, get_user_id())
    return redirect(url_for('dashboard'))


# ===================== 日历系统 =====================
@app.route('/calendar')
def calendar_view():
    uid = get_user_id()
    db = get_db()
    view = request.args.get('view', 'week')
    date_str = request.args.get('date', today_str())
    base_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    events_by_date = {}

    if view == 'day':
        dates = [base_date]
    elif view == 'week':
        dates = get_week_days(base_date)
    else:  # month
        dates = get_month_days(base_date.year, base_date.month)

    start = dates[0].isoformat()
    end = dates[-1].isoformat()

    # 获取日历事件
    cal_events = db.execute(
        "SELECT * FROM calendar_events WHERE event_date >= ? AND event_date <= ? AND user_id = ? ORDER BY event_date, event_time",
        (start, end, uid)
    ).fetchall()
    for ev in cal_events:
        d = ev['event_date']
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append({'type': 'event', 'data': ev})

    # 获取任务（按截止日期和安排日期）
    tasks = db.execute(
        "SELECT * FROM tasks WHERE ((deadline >= ? AND deadline <= ?) OR (scheduled_date >= ? AND scheduled_date <= ?)) AND user_id = ?",
        (start, end, start, end, uid)
    ).fetchall()
    for t in tasks:
        for field in ['deadline', 'scheduled_date']:
            d = t[field]
            if d and start <= d <= end:
                if d not in events_by_date:
                    events_by_date[d] = []
                events_by_date[d].append({'type': 'task', 'data': t})

    # 获取周期事项
    cycles = db.execute(
        "SELECT * FROM life_cycles WHERE next_date >= ? AND next_date <= ? AND status = 'active' AND user_id = ?",
        (start, end, uid)
    ).fetchall()
    for c in cycles:
        d = c['next_date']
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append({'type': 'cycle', 'data': c})

    # 获取工作日志
    logs = db.execute(
        "SELECT * FROM work_logs WHERE log_date >= ? AND log_date <= ? AND user_id = ?",
        (start, end, uid)
    ).fetchall()
    for l in logs:
        d = l['log_date']
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append({'type': 'worklog', 'data': l})

    db.close()

    # 前后导航日期
    if view == 'day':
        prev_date = (base_date - timedelta(days=1)).isoformat()
        next_date = (base_date + timedelta(days=1)).isoformat()
    elif view == 'week':
        prev_date = (base_date - timedelta(weeks=1)).isoformat()
        next_date = (base_date + timedelta(weeks=1)).isoformat()
    else:
        if base_date.month == 1:
            prev_date = date(base_date.year - 1, 12, 1).isoformat()
        else:
            prev_date = date(base_date.year, base_date.month - 1, 1).isoformat()
        if base_date.month == 12:
            next_date = date(base_date.year + 1, 1, 1).isoformat()
        else:
            next_date = date(base_date.year, base_date.month + 1, 1).isoformat()

    return render_template('calendar.html',
        active_page='calendar',
        view=view,
        base_date=base_date,
        dates=dates,
        events_by_date=events_by_date,
        prev_date=prev_date,
        next_date=next_date,
        today=today_str())


@app.route('/calendar/event/add', methods=['POST'])
def calendar_event_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO calendar_events (user_id, title, event_date, event_time, type) VALUES (?, ?, ?, ?, ?)",
        (uid, request.form['title'], request.form['event_date'],
         request.form.get('event_time') or None, request.form.get('type', '工作'))
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('calendar_view'))


@app.route('/calendar/event/<int:eid>/delete', methods=['POST'])
def calendar_event_delete(eid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM calendar_events WHERE id = ? AND user_id = ?", (eid, uid))
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('calendar_view'))


# ===================== 任务系统 =====================
@app.route('/tasks')
def tasks():
    uid = get_user_id()
    db = get_db()
    today = today_str()
    tab = request.args.get('tab', 'today')

    # 分类视图：Today / Upcoming / Long-term
    if tab == 'today':
        task_list = db.execute(
            """SELECT * FROM tasks WHERE user_id = ? AND status != '已完成'
               AND (scheduled_date = ? OR scheduled_date IS NULL OR scheduled_date <= ?)
               ORDER BY CASE priority WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END, deadline ASC, created_at DESC""",
            (uid, today, today)
        ).fetchall()
    elif tab == 'upcoming':
        task_list = db.execute(
            """SELECT * FROM tasks WHERE user_id = ? AND status != '已完成'
               AND scheduled_date > ?
               ORDER BY scheduled_date ASC, priority ASC""",
            (uid, today)
        ).fetchall()
    else:  # long-term
        task_list = db.execute(
            """SELECT * FROM tasks WHERE user_id = ? AND status != '已完成'
               AND (deadline IS NULL OR scheduled_date IS NULL)
               ORDER BY created_at DESC""",
            (uid,)
        ).fetchall()

    db.close()

    return render_template('tasks.html',
        active_page='tasks',
        tasks=task_list,
        tab=tab,
        today=today)


@app.route('/tasks/add', methods=['POST'])
def task_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        """INSERT INTO tasks (user_id, name, type, priority, deadline, status, scheduled_date, focus_category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         request.form['name'],
         request.form.get('type', '工作'),
         request.form.get('priority', '中'),
         request.form.get('deadline') or None,
         request.form.get('status', '未开始'),
         request.form.get('scheduled_date') or None,
         request.form.get('focus_category', 'Work'))
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/update', methods=['POST'])
def task_update(tid):
    uid = get_user_id()
    db = get_db()
    status = request.form.get('status')
    if status == '已完成':
        db.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE id = ? AND user_id = ?",
                   (status, datetime.now().isoformat(), tid, uid))
    else:
        db.execute("UPDATE tasks SET status = ?, completed_at = NULL WHERE id = ? AND user_id = ?",
                   (status, tid, uid))
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/edit', methods=['POST'])
def task_edit(tid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        """UPDATE tasks SET name=?, type=?, priority=?, deadline=?, scheduled_date=?, focus_category=? WHERE id=? AND user_id=?""",
        (request.form['name'],
         request.form.get('type', '工作'),
         request.form.get('priority', '中'),
         request.form.get('deadline') or None,
         request.form.get('scheduled_date') or None,
         request.form.get('focus_category', 'Work'),
         tid, uid)
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/<int:tid>/delete', methods=['POST'])
def task_delete(tid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (tid, uid))
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('tasks'))


@app.route('/tasks/quick', methods=['POST'])
def task_quick_add():
    """Dashboard快速添加任务"""
    uid = get_user_id()
    db = get_db()
    name = request.form.get('name', '').strip()
    if name:
        db.execute(
            """INSERT INTO tasks (user_id, name, type, priority, status, scheduled_date, focus_category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, name, request.form.get('type', '工作'),
             request.form.get('priority', '中'), '未开始',
             today_str(), request.form.get('focus_category', 'Work'))
        )
        db.commit()
    db.close()
    return redirect(url_for('dashboard'))


# ===================== 工作日志 =====================
@app.route('/work-logs')
def work_logs():
    uid = get_user_id()
    db = get_db()
    logs = db.execute(
        "SELECT w.*, p.name as project_name FROM work_logs w LEFT JOIN projects p ON w.project_id = p.id WHERE w.user_id = ? ORDER BY w.log_date DESC",
        (uid,)
    ).fetchall()
    projects = db.execute("SELECT id, name FROM projects WHERE user_id = ? ORDER BY name", (uid,)).fetchall()
    db.close()

    return render_template('work_logs.html',
        active_page='work_logs',
        logs=logs,
        projects=projects)


@app.route('/work-logs/save', methods=['POST'])
def work_log_save():
    uid = get_user_id()
    db = get_db()
    log_date = request.form.get('log_date', today_str())
    project_id = request.form.get('project_id') or None
    completed = request.form.get('completed', '')
    problems = request.form.get('problems', '')
    thoughts = request.form.get('thoughts', '')
    tomorrow = request.form.get('tomorrow_focus', '')

    # AXIS AI 整理
    ai_summary = summarize_work_log(completed, problems, thoughts)
    achievements = '\n'.join([line.strip() for line in completed.split('\n') if line.strip()][:5])

    # 使用 INSERT OR REPLACE 避免 UNIQUE 约束冲突
    # 注意：需要同时匹配 user_id + log_date 才能正确替换
    existing = db.execute("SELECT id FROM work_logs WHERE log_date = ? AND user_id = ?", (log_date, uid)).fetchone()
    if existing:
        db.execute(
            """UPDATE work_logs SET project_id=?, completed=?, problems=?, thoughts=?, tomorrow_focus=?, ai_summary=?, achievements=?
               WHERE id=?""",
            (project_id, completed, problems, thoughts, tomorrow, ai_summary, achievements, existing['id'])
        )
    else:
        db.execute(
            """INSERT OR IGNORE INTO work_logs (user_id, log_date, project_id, completed, problems, thoughts, tomorrow_focus, ai_summary, achievements)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, log_date, project_id, completed, problems, thoughts, tomorrow, ai_summary, achievements)
        )
        # 如果 IGNORE 导致没插入（理论上不会，但防御性处理），尝试 UPDATE
        if db.total_changes == 0:
            db.execute(
                """UPDATE work_logs SET project_id=?, completed=?, problems=?, thoughts=?, tomorrow_focus=?, ai_summary=?, achievements=?
                   WHERE log_date=? AND user_id=?""",
                (project_id, completed, problems, thoughts, tomorrow, ai_summary, achievements, log_date, uid)
            )
    db.commit()
    db.close()

    # 标记 Evening Loop 完成（使用独立连接）
    update_daily_loop_state(uid, log_date, 'evening_completed', 1)
    update_daily_loop_state(uid, log_date, 'evening_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 保存工作日志后，引导用户规划今晚个人时间
    return redirect(url_for('evening_plan', from_context='worklog'))


@app.route('/work-logs/<int:lid>/delete', methods=['POST'])
def work_log_delete(lid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM work_logs WHERE id = ? AND user_id = ?", (lid, uid))
    db.commit()
    db.close()
    return redirect(url_for('work_logs'))


@app.route('/work-logs/today', methods=['POST'])
def work_log_today():
    """Dashboard快速记录工作日志"""
    uid = get_user_id()
    db = get_db()
    log_date = today_str()
    completed = request.form.get('completed', '')
    problems = request.form.get('problems', '')
    tomorrow = request.form.get('tomorrow_focus', '')

    # AXIS AI 整理
    ai_summary = summarize_work_log(completed, problems, '')
    achievements = '\n'.join([line.strip() for line in completed.split('\n') if line.strip()][:5])

    existing = db.execute("SELECT id FROM work_logs WHERE log_date = ? AND user_id = ?", (log_date, uid)).fetchone()
    if existing:
        db.execute(
            "UPDATE work_logs SET completed=?, problems=?, tomorrow_focus=?, ai_summary=?, achievements=? WHERE log_date=? AND user_id=?",
            (completed, problems, tomorrow, ai_summary, achievements, log_date, uid)
        )
    else:
        db.execute(
            "INSERT INTO work_logs (user_id, log_date, completed, problems, tomorrow_focus, ai_summary, achievements) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, log_date, completed, problems, tomorrow, ai_summary, achievements)
        )
    db.commit()
    db.close()

    # 标记 Evening Loop 完成
    update_daily_loop_state(uid, log_date, 'evening_completed', 1)
    update_daily_loop_state(uid, log_date, 'evening_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 保存工作日志后，引导用户规划今晚个人时间
    return redirect(url_for('evening_plan', from_context='worklog'))


# ===================== 项目管理 =====================
@app.route('/projects')
def projects():
    uid = get_user_id()
    db = get_db()
    proj_list = db.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()

    # 获取每个项目的日志数和复盘
    projects_with_stats = []
    for p in proj_list:
        log_count = db.execute(
            "SELECT COUNT(*) as c FROM work_logs WHERE project_id = ? AND user_id = ?", (p['id'], uid)
        ).fetchone()['c']
        review = db.execute(
            "SELECT * FROM project_reviews WHERE project_id = ? AND user_id = ?", (p['id'], uid)
        ).fetchone()
        projects_with_stats.append({**dict(p), 'log_count': log_count, 'review': review})

    db.close()

    return render_template('projects.html',
        active_page='projects',
        projects=projects_with_stats)


@app.route('/projects/add', methods=['POST'])
def project_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        """INSERT INTO projects (user_id, name, objective, start_date, end_date, stage)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (uid,
         request.form['name'],
         request.form.get('objective', ''),
         request.form.get('start_date') or None,
         request.form.get('end_date') or None,
         request.form.get('stage', '研究阶段'))
    )
    db.commit()
    db.close()
    return redirect(url_for('projects'))


@app.route('/projects/<int:pid>/update', methods=['POST'])
def project_update(pid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        """UPDATE projects SET name=?, objective=?, start_date=?, end_date=?, stage=? WHERE id=? AND user_id=?""",
        (request.form['name'],
         request.form.get('objective', ''),
         request.form.get('start_date') or None,
         request.form.get('end_date') or None,
         request.form.get('stage', '研究阶段'),
         pid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('projects'))


@app.route('/projects/<int:pid>/delete', methods=['POST'])
def project_delete(pid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (pid, uid))
    db.execute("DELETE FROM project_reviews WHERE project_id = ? AND user_id = ?", (pid, uid))
    db.execute("UPDATE work_logs SET project_id = NULL WHERE project_id = ? AND user_id = ?", (pid, uid))
    db.commit()
    db.close()
    return redirect(url_for('projects'))


@app.route('/projects/<int:pid>/review', methods=['GET', 'POST'])
def project_review(pid):
    uid = get_user_id()
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND user_id = ?", (pid, uid)).fetchone()

    if request.method == 'POST':
        existing = db.execute("SELECT id FROM project_reviews WHERE project_id = ? AND user_id = ?", (pid, uid)).fetchone()
        if existing:
            db.execute(
                """UPDATE project_reviews SET objective=?, result=?, completion=?, good_points=?, bad_points=?, experience=?, optimization=?
                WHERE project_id=? AND user_id=?""",
                (request.form.get('objective',''), request.form.get('result',''),
                 request.form.get('completion',''), request.form.get('good_points',''),
                 request.form.get('bad_points',''), request.form.get('experience',''),
                 request.form.get('optimization',''), pid, uid)
            )
        else:
            db.execute(
                """INSERT INTO project_reviews (user_id, project_id, objective, result, completion, good_points, bad_points, experience, optimization)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, pid, request.form.get('objective',''), request.form.get('result',''),
                 request.form.get('completion',''), request.form.get('good_points',''),
                 request.form.get('bad_points',''), request.form.get('experience',''),
                 request.form.get('optimization',''))
            )
        db.commit()
        db.close()
        return redirect(url_for('project_review', pid=pid))

    review = db.execute("SELECT * FROM project_reviews WHERE project_id = ? AND user_id = ?", (pid, uid)).fetchone()
    logs = db.execute(
        "SELECT * FROM work_logs WHERE project_id = ? AND user_id = ? ORDER BY log_date DESC", (pid, uid)
    ).fetchall()
    db.close()

    return render_template('project_review.html',
        active_page='projects',
        project=project,
        review=review,
        logs=logs)


# ===================== 灵感收集 =====================
@app.route('/inbox')
def inbox():
    uid = get_user_id()
    db = get_db()
    items = db.execute("SELECT * FROM inbox WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
    db.close()

    return render_template('inbox.html', active_page='inbox', items=items)


@app.route('/inbox/add', methods=['POST'])
def inbox_add():
    uid = get_user_id()
    db = get_db()
    title = request.form.get('title', '')
    content = request.form.get('content', '')
    # AXIS AI 自动分类
    ai_category = categorize_inbox((title + ' ' + content).strip())
    db.execute(
        "INSERT INTO inbox (user_id, title, content, source, tags, ai_category) VALUES (?, ?, ?, ?, ?, ?)",
        (uid,
         title,
         content,
         request.form.get('source', ''),
         request.form.get('tags', ''),
         ai_category)
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('inbox'))


@app.route('/inbox/<int:iid>/edit', methods=['POST'])
def inbox_edit(iid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE inbox SET title=?, content=?, source=?, tags=? WHERE id=? AND user_id=?",
        (request.form.get('title',''), request.form.get('content',''),
         request.form.get('source',''), request.form.get('tags',''), iid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('inbox'))


@app.route('/inbox/<int:iid>/delete', methods=['POST'])
def inbox_delete(iid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM inbox WHERE id = ? AND user_id = ?", (iid, uid))
    db.commit()
    db.close()
    return redirect(url_for('inbox'))


@app.route('/inbox/quick', methods=['POST'])
def inbox_quick_add():
    """Dashboard快速记录想法"""
    uid = get_user_id()
    db = get_db()
    content = request.form.get('content', '').strip()
    if content:
        title = request.form.get('title', '') or content[:20]
        # AXIS AI 自动分类
        ai_category = categorize_inbox(title + ' ' + content)
        db.execute(
            "INSERT INTO inbox (user_id, title, content, source, ai_category) VALUES (?, ?, ?, ?, ?)",
            (uid, title, content, '快速记录', ai_category)
        )
        db.commit()
    db.close()
    return redirect(url_for('dashboard'))


# ===================== 思考笔记 =====================
@app.route('/notes')
def notes():
    uid = get_user_id()
    db = get_db()
    category = request.args.get('category', '')
    query = "SELECT * FROM notes WHERE 1=1 AND user_id = ?"
    params = [uid]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY created_at DESC"
    note_list = db.execute(query, params).fetchall()
    db.close()

    return render_template('notes.html',
        active_page='notes',
        notes=note_list,
        current_category=category)


@app.route('/notes/add', methods=['POST'])
def note_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO notes (user_id, title, content, category, tags) VALUES (?, ?, ?, ?, ?)",
        (uid,
         request.form['title'],
         request.form.get('content', ''),
         request.form.get('category', '其他'),
         request.form.get('tags', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('notes'))


@app.route('/notes/<int:nid>/edit', methods=['POST'])
def note_edit(nid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE notes SET title=?, content=?, category=?, tags=? WHERE id=? AND user_id=?",
        (request.form.get('title',''), request.form.get('content',''),
         request.form.get('category','其他'), request.form.get('tags',''), nid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('notes'))


@app.route('/notes/<int:nid>/delete', methods=['POST'])
def note_delete(nid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (nid, uid))
    db.commit()
    db.close()
    return redirect(url_for('notes'))


# ===================== 目标规划 =====================
@app.route('/goals')
def goals():
    uid = get_user_id()
    db = get_db()
    # 获取自定义分类（层级），按排序字段排列
    goal_categories = get_categories(uid, 'goals')
    # 按 sort_order 取全部目标，分组时保持排序
    all_goals = db.execute("SELECT * FROM goals WHERE user_id = ? ORDER BY sort_order ASC, created_at DESC", (uid,)).fetchall()

    # 构建树结构（仅保留自定义分类下的目标，其余归入对应层级）
    goal_tree = {c: [] for c in goal_categories}
    for g in all_goals:
        level = g['level']
        if level not in goal_tree:
            goal_tree[level] = []
        goal_tree[level].append(dict(g))

    db.close()

    return render_template('goals.html',
        active_page='goals',
        goal_tree=goal_tree,
        goal_categories=goal_categories,
        all_goals=all_goals)


@app.route('/goals/add', methods=['POST'])
def goal_add():
    uid = get_user_id()
    db = get_db()
    parent_id = request.form.get('parent_id') or None
    cats = get_categories(uid, 'goals')
    level = request.form.get('level') or (cats[0] if cats else '年度目标')
    max_so = db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM goals WHERE user_id = ?", (uid,)).fetchone()[0]
    db.execute(
        "INSERT INTO goals (user_id, name, description, level, parent_id, period, status, progress, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid,
         request.form['name'],
         request.form.get('description', ''),
         level,
         parent_id,
         request.form.get('period', ''),
         request.form.get('status', '进行中'),
         int(request.form.get('progress', 0) or 0),
         max_so + 1)
    )
    db.commit()
    db.close()
    return redirect(url_for('goals'))


@app.route('/goals/<int:gid>/update', methods=['POST'])
def goal_update(gid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE goals SET name=?, description=?, level=?, period=?, status=?, progress=? WHERE id=? AND user_id=?",
        (request.form.get('name',''), request.form.get('description',''),
         request.form.get('level','年度目标'), request.form.get('period',''),
         request.form.get('status','进行中'),
         int(request.form.get('progress', 0) or 0),
         gid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('goals'))


@app.route('/goals/<int:gid>/delete', methods=['POST'])
def goal_delete(gid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (gid, uid))
    db.execute("UPDATE goals SET parent_id = NULL WHERE parent_id = ? AND user_id = ?", (gid, uid))
    db.commit()
    db.close()
    return redirect(url_for('goals'))


# ===================== 计划自定义分类 / 排序 API =====================
@app.route('/api/categories')
def api_categories():
    """获取某模块的分类列表（JSON）"""
    uid = get_user_id()
    module = request.args.get('module', '')
    return jsonify({'categories': get_categories(uid, module)})


@app.route('/api/categories/add', methods=['POST'])
def api_categories_add():
    """新增自定义分类"""
    uid = get_user_id()
    data = request.get_json(force=True, silent=True) or {}
    module = data.get('module', '')
    name = (data.get('name') or '').strip()
    if not name or name == SYSTEM_CATEGORY:
        return jsonify({'ok': False, 'error': '分类名称无效'}), 400
    db = get_db()
    exist = db.execute(
        "SELECT 1 FROM plan_categories WHERE user_id=? AND module=? AND name=?",
        (uid, module, name)
    ).fetchone()
    if exist:
        db.close()
        return jsonify({'ok': False, 'error': '分类已存在'}), 400
    max_so = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM plan_categories WHERE user_id=? AND module=?",
        (uid, module)
    ).fetchone()[0]
    db.execute(
        "INSERT INTO plan_categories (user_id, module, name, sort_order) VALUES (?, ?, ?, ?)",
        (uid, module, name, max_so + 1)
    )
    db.commit()
    db.close()
    return jsonify({'ok': True, 'categories': get_categories(uid, module)})


@app.route('/api/categories/delete', methods=['POST'])
def api_categories_delete():
    """删除自定义分类（相关项归到系统分类「未分类」）"""
    uid = get_user_id()
    data = request.get_json(force=True, silent=True) or {}
    module = data.get('module', '')
    name = (data.get('name') or '').strip()
    if name == SYSTEM_CATEGORY:
        return jsonify({'ok': False, 'error': '系统分类不可删除'}), 400
    db = get_db()
    if module == 'goals':
        db.execute("UPDATE goals SET level=? WHERE user_id=? AND level=?", (SYSTEM_CATEGORY, uid, name))
    elif module == 'evening_plan':
        db.execute("UPDATE evening_plans SET category=? WHERE user_id=? AND category=?", (SYSTEM_CATEGORY, uid, name))
    db.execute(
        "DELETE FROM plan_categories WHERE user_id=? AND module=? AND name=?",
        (uid, module, name)
    )
    db.commit()
    db.close()
    return jsonify({'ok': True, 'categories': get_categories(uid, module)})


@app.route('/api/goals/reorder', methods=['POST'])
def goals_reorder():
    """保存目标排序（拖拽后调用）"""
    uid = get_user_id()
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get('ids', [])
    db = get_db()
    for i, gid in enumerate(ids):
        db.execute("UPDATE goals SET sort_order=? WHERE id=? AND user_id=?", (i, gid, uid))
    db.commit()
    db.close()
    return jsonify({'ok': True})


@app.route('/api/evening-plan/reorder', methods=['POST'])
def evening_plan_reorder():
    """保存今晚计划排序（拖拽后调用，按日期隔离）"""
    uid = get_user_id()
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get('ids', [])
    plan_date = data.get('date')
    db = get_db()
    for i, pid in enumerate(ids):
        db.execute(
            "UPDATE evening_plans SET sort_order=? WHERE id=? AND user_id=? AND plan_date=?",
            (i, pid, uid, plan_date)
        )
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ===================== 月度计划 =====================
@app.route('/monthly-plan')
def monthly_plan():
    uid = get_user_id()
    db = get_db()
    # 默认显示当月
    year_month = request.args.get('ym', datetime.now().strftime('%Y-%m'))
    plan = db.execute(
        "SELECT * FROM monthly_plans WHERE year_month = ? AND user_id = ?", (year_month, uid)
    ).fetchone()

    # 获取有记录的月份列表
    all_plans = db.execute(
        "SELECT year_month FROM monthly_plans WHERE user_id = ? ORDER BY year_month DESC", (uid,)
    ).fetchall()
    db.close()

    return render_template('monthly_plan.html',
        active_page='monthly_plan',
        plan=plan,
        year_month=year_month,
        all_plans=all_plans)


@app.route('/monthly-plan/save', methods=['POST'])
def monthly_plan_save():
    uid = get_user_id()
    db = get_db()
    ym = request.form.get('year_month')
    existing = db.execute("SELECT id FROM monthly_plans WHERE year_month = ? AND user_id = ?", (ym, uid)).fetchone()
    if existing:
        db.execute(
            """UPDATE monthly_plans SET work_goal=?, learning_goal=?, reading_plan=?, expense_plan=?, life_plan=?
            WHERE year_month=? AND user_id=?""",
            (request.form.get('work_goal',''), request.form.get('learning_goal',''),
             request.form.get('reading_plan',''), request.form.get('expense_plan',''),
             request.form.get('life_plan',''), ym, uid)
        )
    else:
        db.execute(
            """INSERT INTO monthly_plans (user_id, year_month, work_goal, learning_goal, reading_plan, expense_plan, life_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, ym, request.form.get('work_goal',''), request.form.get('learning_goal',''),
             request.form.get('reading_plan',''), request.form.get('expense_plan',''),
             request.form.get('life_plan',''))
        )
    db.commit()
    db.close()
    return redirect(url_for('monthly_plan', ym=ym))


# ===================== 周期事项 =====================
@app.route('/life-cycle')
def life_cycle():
    uid = get_user_id()
    db = get_db()
    today = today_str()
    cycles = db.execute("SELECT * FROM life_cycles WHERE status = 'active' AND user_id = ? ORDER BY next_date ASC", (uid,)).fetchall()

    # 获取用户已使用的所有分类（去重）
    existing_cats = [row['category'] for row in db.execute(
        "SELECT DISTINCT category FROM life_cycles WHERE user_id = ? ORDER BY category", (uid,)
    ).fetchall()]
    # 合并预设分类
    preset_cats = ['宠物', '健康', '家庭', '设备', '财务', '其他']
    all_cats = list(dict.fromkeys(existing_cats + preset_cats))

    # 计算状态
    cycle_list = []
    for c in cycles:
        c_dict = dict(c)
        days_until = (datetime.strptime(c['next_date'], '%Y-%m-%d').date() - date.today()).days
        c_dict['days_until'] = days_until
        c_dict['is_overdue'] = days_until < 0
        c_dict['is_due_soon'] = 0 <= days_until <= parse_advance_days(c['advance_remind'])
        cycle_list.append(c_dict)

    db.close()

    return render_template('life_cycle.html',
        active_page='life_cycle',
        cycles=cycle_list,
        today=today,
        existing_categories=all_cats)


@app.route('/life-cycle/add', methods=['POST'])
def life_cycle_add():
    uid = get_user_id()
    db = get_db()
    name = request.form['name']
    category = request.form.get('category', '其他')
    last_done = request.form['last_done_date']
    cycle_num = int(request.form['cycle_number'])
    cycle_unit = request.form['cycle_unit']
    advance = request.form.get('advance_remind', '3天')

    next_date = calculate_next_date(last_done, cycle_num, cycle_unit)

    db.execute(
        """INSERT INTO life_cycles (user_id, name, category, last_done_date, cycle_number, cycle_unit, next_date, advance_remind)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, name, category, last_done, cycle_num, cycle_unit, next_date, advance)
    )
    db.commit()
    db.close()
    return redirect(url_for('life_cycle'))


@app.route('/life-cycle/<int:cid>/complete', methods=['POST'])
def life_cycle_complete(cid):
    """标记完成，自动更新下次日期"""
    uid = get_user_id()
    db = get_db()
    cycle = db.execute("SELECT * FROM life_cycles WHERE id = ? AND user_id = ?", (cid, uid)).fetchone()
    if cycle:
        new_done = request.form.get('done_date', today_str())
        next_date = calculate_next_date(new_done, cycle['cycle_number'], cycle['cycle_unit'])
        db.execute(
            "UPDATE life_cycles SET last_done_date=?, next_date=? WHERE id=? AND user_id=?",
            (new_done, next_date, cid, uid)
        )
        db.commit()
    db.close()
    return redirect(url_for('life_cycle'))


@app.route('/life-cycle/<int:cid>/edit', methods=['POST'])
def life_cycle_edit(cid):
    uid = get_user_id()
    db = get_db()
    cycle_num = int(request.form['cycle_number'])
    cycle_unit = request.form['cycle_unit']
    last_done = request.form['last_done_date']
    next_date = calculate_next_date(last_done, cycle_num, cycle_unit)

    db.execute(
        """UPDATE life_cycles SET name=?, category=?, last_done_date=?, cycle_number=?, cycle_unit=?, next_date=?, advance_remind=?
        WHERE id=? AND user_id=?""",
        (request.form['name'], request.form.get('category','其他'),
         last_done, cycle_num, cycle_unit, next_date,
         request.form.get('advance_remind','3天'), cid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('life_cycle'))


@app.route('/life-cycle/<int:cid>/delete', methods=['POST'])
def life_cycle_delete(cid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM life_cycles WHERE id = ? AND user_id = ?", (cid, uid))
    db.commit()
    db.close()
    return redirect(url_for('life_cycle'))


# ===================== 健康记录 =====================
@app.route('/health')
def health():
    uid = get_user_id()
    db = get_db()
    today = today_str()
    today_record = db.execute(
        "SELECT * FROM daily_health WHERE record_date = ? AND user_id = ?", (today, uid)
    ).fetchone()

    # 最近30天记录
    records = db.execute(
        "SELECT * FROM daily_health WHERE user_id = ? ORDER BY record_date DESC LIMIT 30", (uid,)
    ).fetchall()
    db.close()

    return render_template('health.html',
        active_page='health',
        today_record=today_record,
        records=records,
        today=today,
        get_stars=get_stars)


@app.route('/health/save', methods=['POST'])
def health_save():
    uid = get_user_id()
    db = get_db()
    record_date = request.form.get('record_date', today_str())
    sleep = int(request.form.get('sleep_score', 0) or 0)
    energy = int(request.form.get('energy_score', 0) or 0)
    status = int(request.form.get('status_score', 0) or 0)
    note = request.form.get('note', '')

    existing = db.execute("SELECT id FROM daily_health WHERE record_date = ? AND user_id = ?", (record_date, uid)).fetchone()
    if existing:
        db.execute(
            "UPDATE daily_health SET sleep_score=?, energy_score=?, status_score=?, note=? WHERE record_date=? AND user_id=?",
            (sleep, energy, status, note, record_date, uid)
        )
    else:
        db.execute(
            "INSERT INTO daily_health (user_id, record_date, sleep_score, energy_score, status_score, note) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, record_date, sleep, energy, status, note)
        )
    db.commit()
    db.close()
    return redirect(url_for('health'))


@app.route('/health/<int:hid>/delete', methods=['POST'])
def health_delete(hid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM daily_health WHERE id = ? AND user_id = ?", (hid, uid))
    db.commit()
    db.close()
    return redirect(url_for('health'))


@app.route('/health/today', methods=['POST'])
def health_today():
    """Dashboard快速记录今日状态"""
    uid = get_user_id()
    db = get_db()
    today = today_str()
    sleep = int(request.form.get('sleep_score', 0) or 0)
    energy = int(request.form.get('energy_score', 0) or 0)
    status = int(request.form.get('status_score', 0) or 0)

    existing = db.execute("SELECT id FROM daily_health WHERE record_date = ? AND user_id = ?", (today, uid)).fetchone()
    if existing:
        db.execute(
            "UPDATE daily_health SET sleep_score=?, energy_score=?, status_score=? WHERE record_date=? AND user_id=?",
            (sleep, energy, status, today, uid)
        )
    else:
        db.execute(
            "INSERT INTO daily_health (user_id, record_date, sleep_score, energy_score, status_score) VALUES (?, ?, ?, ?, ?)",
            (uid, today, sleep, energy, status)
        )
    db.commit()
    db.close()
    return redirect(url_for('dashboard'))


# ===================== 财务管理 =====================
@app.route('/finance')
def finance():
    uid = get_user_id()
    db = get_db()
    ym = request.args.get('ym', datetime.now().strftime('%Y-%m'))
    monthly = db.execute(
        "SELECT * FROM finance_monthly WHERE year_month = ? AND user_id = ?", (ym, uid)
    ).fetchone()

    expenses = db.execute(
        "SELECT * FROM big_expenses WHERE user_id = ? ORDER BY expense_date DESC LIMIT 20", (uid,)
    ).fetchall()

    decisions = db.execute(
        "SELECT * FROM purchase_decisions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (uid,)
    ).fetchall()

    all_months = db.execute(
        "SELECT year_month FROM finance_monthly WHERE user_id = ? ORDER BY year_month DESC", (uid,)
    ).fetchall()
    db.close()

    return render_template('finance.html',
        active_page='finance',
        monthly=monthly,
        expenses=expenses,
        decisions=decisions,
        year_month=ym,
        all_months=all_months)


@app.route('/finance/monthly/save', methods=['POST'])
def finance_monthly_save():
    uid = get_user_id()
    db = get_db()
    ym = request.form.get('year_month')
    income = float(request.form.get('income', 0) or 0)
    fixed = float(request.form.get('fixed_expense', 0) or 0)
    free = float(request.form.get('free_amount', 0) or 0)
    summary = request.form.get('summary', '')

    existing = db.execute("SELECT id FROM finance_monthly WHERE year_month = ? AND user_id = ?", (ym, uid)).fetchone()
    if existing:
        db.execute(
            "UPDATE finance_monthly SET income=?, fixed_expense=?, free_amount=?, summary=? WHERE year_month=? AND user_id=?",
            (income, fixed, free, summary, ym, uid)
        )
    else:
        db.execute(
            "INSERT INTO finance_monthly (user_id, year_month, income, fixed_expense, free_amount, summary) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, ym, income, fixed, free, summary)
        )
    db.commit()
    db.close()
    return redirect(url_for('finance', ym=ym))


@app.route('/finance/expense/add', methods=['POST'])
def finance_expense_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        """INSERT INTO big_expenses (user_id, item_name, amount, category, reason, satisfaction, expense_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         request.form['item_name'],
         float(request.form.get('amount', 0)),
         request.form.get('category', '生活'),
         request.form.get('reason', ''),
         int(request.form.get('satisfaction', 0) or 0),
         request.form.get('expense_date') or None)
    )
    db.commit()
    db.close()
    return redirect(url_for('finance'))


@app.route('/finance/expense/<int:eid>/delete', methods=['POST'])
def finance_expense_delete(eid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM big_expenses WHERE id = ? AND user_id = ?", (eid, uid))
    db.commit()
    db.close()
    return redirect(url_for('finance'))


@app.route('/finance/decision/add', methods=['POST'])
def finance_decision_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        """INSERT INTO purchase_decisions (user_id, item_name, reason, budget, research, decision, result, satisfaction)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid,
         request.form['item_name'],
         request.form.get('reason', ''),
         float(request.form.get('budget', 0) or 0),
         request.form.get('research', ''),
         request.form.get('decision', ''),
         request.form.get('result', ''),
         int(request.form.get('satisfaction', 0) or 0))
    )
    db.commit()
    db.close()
    return redirect(url_for('finance'))


@app.route('/finance/decision/<int:did>/delete', methods=['POST'])
def finance_decision_delete(did):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM purchase_decisions WHERE id = ? AND user_id = ?", (did, uid))
    db.commit()
    db.close()
    return redirect(url_for('finance'))


# ===================== 阅读计划 =====================
@app.route('/reading')
def reading():
    uid = get_user_id()
    db = get_db()
    status = request.args.get('status', '')
    query = "SELECT * FROM readings WHERE 1=1 AND user_id = ?"
    params = [uid]
    if status:
        query += " AND reading_status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    books = db.execute(query, params).fetchall()
    db.close()

    return render_template('reading.html',
        active_page='reading',
        books=books,
        current_status=status)


@app.route('/reading/add', methods=['POST'])
def reading_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO readings (user_id, book_name, author, purchase_status, reading_status, reading_goal, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uid,
         request.form['book_name'],
         request.form.get('author', ''),
         request.form.get('purchase_status', '未购买'),
         request.form.get('reading_status', '未开始'),
         request.form.get('reading_goal', ''),
         request.form.get('notes', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('reading'))


@app.route('/reading/<int:rid>/update', methods=['POST'])
def reading_update(rid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE readings SET book_name=?, author=?, purchase_status=?, reading_status=?, reading_goal=?, notes=? WHERE id=? AND user_id=?",
        (request.form.get('book_name',''), request.form.get('author',''),
         request.form.get('purchase_status','未购买'),
         request.form.get('reading_status','未开始'),
         request.form.get('reading_goal',''),
         request.form.get('notes',''), rid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('reading'))


@app.route('/reading/<int:rid>/delete', methods=['POST'])
def reading_delete(rid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM readings WHERE id = ? AND user_id = ?", (rid, uid))
    db.commit()
    db.close()
    return redirect(url_for('reading'))


# ===================== 学习计划 =====================
@app.route('/learning')
def learning():
    uid = get_user_id()
    db = get_db()
    items = db.execute("SELECT * FROM learnings WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
    db.close()

    return render_template('learning.html', active_page='learning', items=items)


@app.route('/learning/add', methods=['POST'])
def learning_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO learnings (user_id, content, goal, period, progress, result) VALUES (?, ?, ?, ?, ?, ?)",
        (uid,
         request.form['content'],
         request.form.get('goal', ''),
         request.form.get('period', ''),
         int(request.form.get('progress', 0) or 0),
         request.form.get('result', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('learning'))


@app.route('/learning/<int:lid>/update', methods=['POST'])
def learning_update(lid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE learnings SET content=?, goal=?, period=?, progress=?, result=? WHERE id=? AND user_id=?",
        (request.form.get('content',''), request.form.get('goal',''),
         request.form.get('period',''),
         int(request.form.get('progress', 0) or 0),
         request.form.get('result',''), lid, uid)
    )
    db.commit()
    db.close()
    return redirect(url_for('learning'))


@app.route('/learning/<int:lid>/delete', methods=['POST'])
def learning_delete(lid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM learnings WHERE id = ? AND user_id = ?", (lid, uid))
    db.commit()
    db.close()
    return redirect(url_for('learning'))


# ===================== 知识资产 =====================
@app.route('/archive')
def archive():
    uid = get_user_id()
    db = get_db()
    tab = request.args.get('tab', 'cases')

    cases = db.execute("SELECT * FROM cases WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
    methods = db.execute("SELECT * FROM methodologies WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()
    views = db.execute("SELECT * FROM viewpoints WHERE user_id = ? ORDER BY created_at DESC", (uid,)).fetchall()

    db.close()

    return render_template('archive.html',
        active_page='archive',
        tab=tab,
        cases=cases,
        methods=methods,
        views=views)


@app.route('/archive/case/add', methods=['POST'])
def archive_case_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO cases (user_id, name, industry, type, tags, analysis) VALUES (?, ?, ?, ?, ?, ?)",
        (uid,
         request.form['name'],
         request.form.get('industry', ''),
         request.form.get('type', ''),
         request.form.get('tags', ''),
         request.form.get('analysis', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='cases'))


@app.route('/archive/case/<int:cid>/delete', methods=['POST'])
def archive_case_delete(cid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM cases WHERE id = ? AND user_id = ?", (cid, uid))
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='cases'))


@app.route('/archive/method/add', methods=['POST'])
def archive_method_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO methodologies (user_id, title, content, tags) VALUES (?, ?, ?, ?)",
        (uid,
         request.form['title'],
         request.form.get('content', ''),
         request.form.get('tags', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='methods'))


@app.route('/archive/method/<int:mid>/delete', methods=['POST'])
def archive_method_delete(mid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM methodologies WHERE id = ? AND user_id = ?", (mid, uid))
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='methods'))


@app.route('/archive/viewpoint/add', methods=['POST'])
def archive_viewpoint_add():
    uid = get_user_id()
    db = get_db()
    db.execute(
        "INSERT INTO viewpoints (user_id, title, content, tags) VALUES (?, ?, ?, ?)",
        (uid,
         request.form['title'],
         request.form.get('content', ''),
         request.form.get('tags', ''))
    )
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='views'))


@app.route('/archive/viewpoint/<int:vid>/delete', methods=['POST'])
def archive_viewpoint_delete(vid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM viewpoints WHERE id = ? AND user_id = ?", (vid, uid))
    db.commit()
    db.close()
    return redirect(url_for('archive', tab='views'))


# ===================== 自动化提醒 =====================
@app.route('/automation')
def automation():
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute
    current_time_val = current_hour * 60 + current_minute
    today_weekday = now.weekday()  # 0=Monday, 6=Sunday
    today_day = now.day

    # 判断当前应激活的提醒
    reminders = []

    # 1. 今日规划 9:00-9:30
    if 540 <= current_time_val <= 570:
        reminders.append({
            'title': '开始今日规划',
            'time_range': '09:00 - 09:30',
            'description': '打开今日任务页面，填写今天最重要的三件事',
            'action_url': url_for('tasks'),
            'action_text': '打开任务页面',
            'active': True
        })
    else:
        reminders.append({
            'title': '开始今日规划',
            'time_range': '09:00 - 09:30',
            'description': '打开今日任务页面，填写今天最重要的三件事',
            'action_url': url_for('tasks'),
            'action_text': '打开任务页面',
            'active': False,
            'scheduled': '每天 09:00-09:30'
        })

    # 2. 工作日志 18:50-20:00
    if 1130 <= current_time_val <= 1200:
        reminders.append({
            'title': '完成今日工作记录',
            'time_range': '18:50 - 20:00',
            'description': '填写：今天完成 / 今天问题 / 明日重点',
            'action_url': url_for('work_logs'),
            'action_text': '打开工作日志',
            'active': True
        })
    else:
        reminders.append({
            'title': '完成今日工作记录',
            'time_range': '18:50 - 20:00',
            'description': '填写：今天完成 / 今天问题 / 明日重点',
            'action_url': url_for('work_logs'),
            'action_text': '打开工作日志',
            'active': False,
            'scheduled': '每天 18:50-20:00'
        })

    # 3. 今晚计划引导（工作日志后，19:00-21:00）
    if 1140 <= current_time_val <= 1260:
        reminders.append({
            'title': '规划今晚个人时间',
            'time_range': '19:00 - 21:00',
            'description': '工作记录已完成，花几分钟规划今晚：工作延续 / 学习成长 / 生活事项 / 兴趣娱乐',
            'action_url': url_for('evening_plan', from_context='worklog'),
            'action_text': '打开今晚计划',
            'active': True
        })
    else:
        reminders.append({
            'title': '规划今晚个人时间',
            'time_range': '19:00 - 21:00',
            'description': '工作记录完成后，规划今晚个人时间',
            'action_url': url_for('evening_plan'),
            'action_text': '打开今晚计划',
            'active': False,
            'scheduled': '每天 19:00-21:00（工作日志后）'
        })

    # 4. 睡前确认今晚计划完成情况（22:00-23:30）
    if 1320 <= current_time_val <= 1410:
        reminders.append({
            'title': '确认今晚计划完成情况',
            'time_range': '22:00 - 23:30',
            'description': '睡前回顾：今晚计划哪些完成了？未完成的可延后、重排或放弃',
            'action_url': url_for('evening_plan'),
            'action_text': '回顾今晚计划',
            'active': True
        })
    else:
        reminders.append({
            'title': '确认今晚计划完成情况',
            'time_range': '22:00 - 23:30',
            'description': '睡前回顾今晚计划，未完成项可延后、重排或放弃',
            'action_url': url_for('evening_plan'),
            'action_text': '打开今晚计划',
            'active': False,
            'scheduled': '每天 22:00-23:30'
        })

    # 5. 周复盘（每周日）
    if today_weekday == 6:
        reminders.append({
            'title': '完成周复盘',
            'time_range': '今日（周日）',
            'description': '本周完成 / 未完成事项 / 问题 / 调整方向',
            'action_url': url_for('work_logs'),
            'action_text': '开始周复盘',
            'active': True
        })
    else:
        weekdays = ['周一','周二','周三','周四','周五','周六','周日']
        reminders.append({
            'title': '完成周复盘',
            'time_range': '每周日',
            'description': '本周完成 / 未完成事项 / 问题 / 调整方向',
            'action_url': url_for('work_logs'),
            'action_text': '查看工作日志',
            'active': False,
            'scheduled': f'今天{weekdays[today_weekday]}，周日提醒'
        })

    # 6. 月度规划（每月1号）
    if today_day == 1:
        reminders.append({
            'title': '完成月度规划',
            'time_range': '今日（每月1号）',
            'description': '目标规划 / 阅读计划 / 消费规划 / 生活计划',
            'action_url': url_for('monthly_plan'),
            'action_text': '开始月度规划',
            'active': True
        })
    else:
        reminders.append({
            'title': '完成月度规划',
            'time_range': '每月1号',
            'description': '目标规划 / 阅读计划 / 消费规划 / 生活计划',
            'action_url': url_for('monthly_plan'),
            'action_text': '查看月度计划',
            'active': False,
            'scheduled': f'今天{today_day}号，1号提醒'
        })

    return render_template('automation.html',
        active_page='automation',
        reminders=reminders,
        current_time=now.strftime('%H:%M'))


@app.route('/automation/export-ics')
def automation_export_ics():
    """导出 ICS 日历文件

    关键修复：改用 attachment + application/octet-stream，
    避免 iOS（尤其 PWA「添加到主屏幕」独立模式）弹出关不掉的
    “添加事件或日历”系统对话框。
    - iOS Safari 会将其作为文件下载到「文件」App，用户可手动打开 .ics 添加到日历
    - 桌面 / Android 浏览器直接下载，行为正常
    """
    ics_content = generate_ics()
    # generate_ics() 已使用 CRLF，此处做双保险：标准化 LF → CRLF
    ics_crlf = ics_content.replace('\r\n', '\n').replace('\n', '\r\n')
    ics_bytes = ics_crlf.encode('utf-8')

    resp = Response(
        ics_bytes,
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': 'attachment; filename="AXIS_Calendar.ics"',
            'Content-Length': str(len(ics_bytes)),
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
    )
    return resp


# ===================== 设置 =====================
@app.route('/settings')
def settings():
    uid = get_user_id()
    db = get_db()
    # 统计各表数据量
    from utils import EXPORT_TABLES
    stats = {}
    for table in EXPORT_TABLES:
        try:
            count = db.execute(f"SELECT COUNT(*) as c FROM {table} WHERE user_id = ?", (uid,)).fetchone()['c']
            stats[table] = count
        except Exception:
            stats[table] = 0
    total = sum(stats.values())
    db.close()

    # 获取备份历史
    backups = get_backup_history(uid)

    # 获取用户设置
    user_settings = get_user_settings(uid)

    # 自动备份检查（每天首次访问时触发）
    auto_backup(uid)

    return render_template('settings.html',
        active_page='settings',
        stats=stats,
        total_records=total,
        table_list=EXPORT_TABLES,
        backups=backups,
        user_settings=user_settings)


@app.route('/settings/save', methods=['POST'])
@login_required
def settings_save():
    """保存 AXIS 核心设置"""
    uid = get_user_id()
    data = {
        'city': request.form.get('city', 'Beijing'),
        'city_name': request.form.get('city_name', '北京'),
        'life_direction': request.form.get('life_direction', ''),
        'current_stage_goal': request.form.get('current_stage_goal', ''),
        'work_hours_start': request.form.get('work_hours_start', '09:00'),
        'work_hours_end': request.form.get('work_hours_end', '18:00'),
        'daily_loop_enabled': 1 if request.form.get('daily_loop_enabled') else 0,
    }
    save_user_settings(uid, data)
    return redirect(url_for('settings'))


@app.route('/settings/profile', methods=['POST'])
@login_required
def settings_profile():
    """更新账号邮箱与姓名"""
    uid = get_user_id()
    new_name = request.form.get('name', '').strip()
    new_email = request.form.get('email', '').strip()
    if not new_email:
        return redirect(url_for('settings', msg='error|邮箱不能为空'))
    db = get_db()
    # 邮箱唯一性检查（排除自己）
    clash = db.execute(
        "SELECT id FROM users WHERE email = ? AND id != ?", (new_email, uid)
    ).fetchone()
    if clash:
        db.close()
        return redirect(url_for('settings', msg='error|该邮箱已被其他账号使用'))
    db.execute(
        "UPDATE users SET name = ?, email = ? WHERE id = ?",
        (new_name, new_email, uid),
    )
    db.commit()
    db.close()
    return redirect(url_for('settings', msg='success|账号信息已更新'))


@app.route('/export')
def export_data():
    """导出全量JSON备份"""
    uid = get_user_id()
    data = export_all_data(uid)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"personal_os_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/import', methods=['POST'])
def import_data():
    """导入JSON恢复数据"""
    uid = get_user_id()
    if 'backup_file' not in request.files:
        return redirect(url_for('settings'))

    file = request.files['backup_file']
    if file.filename == '':
        return redirect(url_for('settings'))

    try:
        content = file.read().decode('utf-8')
        json_data = json.loads(content)
        mode = request.form.get('mode', 'replace')
        imported = import_all_data(json_data, mode=mode, user_id=uid)

        total = sum(imported.values())
        return redirect(url_for('settings', msg=f'success|导入完成，共恢复 {total} 条记录'))
    except json.JSONDecodeError:
        return redirect(url_for('settings', msg='error|JSON文件格式错误'))
    except Exception as e:
        return redirect(url_for('settings', msg=f'error|导入失败: {str(e)}'))


@app.route('/export/csv')
def export_csv():
    """导出CSV格式（zip包）"""
    uid = get_user_id()
    buf = export_csv_data(uid)
    filename = f"personal_os_csv_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        buf.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/export/markdown')
def export_markdown():
    """导出Markdown格式（zip包）"""
    uid = get_user_id()
    buf = export_markdown_data(uid)
    filename = f"personal_os_markdown_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        buf.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ===================== 自动备份 =====================
@app.route('/backups')
def backups_view():
    uid = get_user_id()
    history = get_backup_history(uid)
    return render_template('backups.html',
        active_page='settings',
        backups=history)


@app.route('/backups/trigger', methods=['POST'])
def backup_trigger():
    """手动触发备份"""
    uid = get_user_id()
    result = auto_backup(uid)
    status = 'success' if result['status'] == 'success' else 'info'
    return redirect(url_for('settings', msg=f'{status}|{result.get("message", "备份成功")}'))


@app.route('/backups/<int:bid>/download')
def backup_download(bid):
    """下载备份文件"""
    uid = get_user_id()
    db = get_db()
    backup = db.execute(
        "SELECT * FROM backups WHERE id = ? AND user_id = ?", (bid, uid)
    ).fetchone()
    db.close()

    if not backup or not backup['file_path'] or not os.path.exists(backup['file_path']):
        return redirect(url_for('settings', msg='error|备份文件不存在'))

    return send_file(backup['file_path'], as_attachment=True,
                     download_name=os.path.basename(backup['file_path']))


# ===================== 今晚计划 =====================
@app.route('/evening-plan')
def evening_plan():
    uid = get_user_id()
    db = get_db()
    today = today_str()
    # 查看日期：默认今天，可切换
    view_date = request.args.get('date', today)
    from_context = request.args.get('from', '')  # worklog 等来源引导

    # 自定义分类
    plan_categories = get_categories(uid, 'evening_plan')

    today_plans = db.execute(
        "SELECT * FROM evening_plans WHERE plan_date = ? AND user_id = ? ORDER BY sort_order ASC, created_at ASC",
        (view_date, uid)
    ).fetchall()

    # 未完成的今晚计划数
    pending = db.execute(
        "SELECT COUNT(*) as c FROM evening_plans WHERE plan_date = ? AND status = '待执行' AND user_id = ?",
        (view_date, uid)
    ).fetchone()['c']

    # 昨天的未完成项（可延后到今天）
    yesterday = (datetime.strptime(view_date, '%Y-%m-%d').date() - timedelta(days=1)).isoformat()
    yesterday_pending = db.execute(
        "SELECT * FROM evening_plans WHERE plan_date = ? AND status = '待执行' AND user_id = ?",
        (yesterday, uid)
    ).fetchall()

    db.close()

    return render_template('evening_plan.html',
        active_page='evening_plan',
        plans=today_plans,
        plan_categories=plan_categories,
        view_date=view_date,
        today=today,
        pending=pending,
        yesterday_pending=yesterday_pending,
        yesterday_date=yesterday,
        from_context=from_context)


@app.route('/evening-plan/add', methods=['POST'])
def evening_plan_add():
    uid = get_user_id()
    db = get_db()
    plan_date = request.form.get('plan_date', today_str())
    cats = get_categories(uid, 'evening_plan')
    category = request.form.get('category') or (cats[0] if cats else '未分类')
    max_so = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM evening_plans WHERE user_id = ? AND plan_date = ?",
        (uid, plan_date)
    ).fetchone()[0]
    db.execute(
        "INSERT INTO evening_plans (user_id, plan_date, name, category, estimated_time, priority, status, sort_order) VALUES (?, ?, ?, ?, ?, ?, '待执行', ?)",
        (uid, plan_date,
         request.form['name'],
         category,
         request.form.get('estimated_time') or None,
         request.form.get('priority', '中'),
         max_so + 1)
    )
    db.commit()
    db.close()
    return redirect(url_for('evening_plan', date=plan_date))


@app.route('/evening-plan/<int:pid>/complete', methods=['POST'])
def evening_plan_complete(pid):
    uid = get_user_id()
    db = get_db()
    db.execute(
        "UPDATE evening_plans SET status='已完成', completed_at=? WHERE id=? AND user_id=?",
        (datetime.now().isoformat(), pid, uid)
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('evening_plan'))


@app.route('/evening-plan/<int:pid>/defer', methods=['POST'])
def evening_plan_defer(pid):
    """延后到明天，自动生成第二天待办候选"""
    uid = get_user_id()
    db = get_db()
    plan = db.execute("SELECT * FROM evening_plans WHERE id = ? AND user_id = ?", (pid, uid)).fetchone()
    if plan:
        tomorrow = (datetime.strptime(plan['plan_date'], '%Y-%m-%d').date() + timedelta(days=1)).isoformat()
        # 标记当前为已延后
        db.execute(
            "UPDATE evening_plans SET status='已延后', deferred_to=? WHERE id=? AND user_id=?",
            (tomorrow, pid, uid)
        )
        # 在第二天创建待办候选
        db.execute(
            "INSERT INTO evening_plans (user_id, plan_date, name, category, estimated_time, priority, status) VALUES (?, ?, ?, ?, ?, ?, '待执行')",
            (uid, tomorrow, plan['name'], plan['category'], plan['estimated_time'], plan['priority'])
        )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('evening_plan'))


@app.route('/evening-plan/<int:pid>/reschedule', methods=['POST'])
def evening_plan_reschedule(pid):
    """重新安排到指定日期"""
    uid = get_user_id()
    db = get_db()
    new_date = request.form.get('new_date')
    plan = db.execute("SELECT * FROM evening_plans WHERE id = ? AND user_id = ?", (pid, uid)).fetchone()
    if plan and new_date:
        db.execute(
            "UPDATE evening_plans SET status='已延后', deferred_to=? WHERE id=? AND user_id=?",
            (new_date, pid, uid)
        )
        db.execute(
            "INSERT INTO evening_plans (user_id, plan_date, name, category, estimated_time, priority, status) VALUES (?, ?, ?, ?, ?, ?, '待执行')",
            (uid, new_date, plan['name'], plan['category'], plan['estimated_time'], plan['priority'])
        )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('evening_plan'))


@app.route('/evening-plan/<int:pid>/abandon', methods=['POST'])
def evening_plan_abandon(pid):
    """放弃"""
    uid = get_user_id()
    db = get_db()
    db.execute("UPDATE evening_plans SET status='已放弃' WHERE id=? AND user_id=?", (pid, uid))
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('evening_plan'))


@app.route('/evening-plan/<int:pid>/delete', methods=['POST'])
def evening_plan_delete(pid):
    uid = get_user_id()
    db = get_db()
    db.execute("DELETE FROM evening_plans WHERE id = ? AND user_id = ?", (pid, uid))
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('evening_plan'))


@app.route('/evening-plan/quick', methods=['POST'])
def evening_plan_quick():
    """从工作日志引导快速添加今晚计划"""
    uid = get_user_id()
    db = get_db()
    plan_date = request.form.get('plan_date', today_str())
    cats = get_categories(uid, 'evening_plan')
    default_cat = cats[0] if cats else '未分类'
    names = request.form.getlist('names')
    for name in names:
        name = name.strip()
        if name:
            db.execute(
                "INSERT INTO evening_plans (user_id, plan_date, name, category, priority, status) VALUES (?, ?, ?, ?, ?, '待执行')",
                (uid, plan_date, name, default_cat, '中')
            )
    db.commit()
    db.close()
    return redirect(url_for('evening_plan', date=plan_date))


# ===================== Splash / PWA =====================
@app.route('/splash')
def splash():
    """启动页"""
    return render_template('splash.html')


@app.route('/ping')
def ping():
    """轻量 ping 端点（保活用，返回最小响应，无需登录）"""
    return 'ok', 200


@app.route('/manifest.json')
def manifest():
    """PWA manifest"""
    return send_file('static/manifest.json', mimetype='application/manifest+json')


@app.route('/sw.js')
def sw():
    """Service Worker"""
    return send_file('static/sw.js', mimetype='application/javascript')


if __name__ == '__main__':
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(debug=debug, host=host, port=port)
