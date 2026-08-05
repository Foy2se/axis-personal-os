"""认证模块 - Personal OS V3.0"""
from functools import wraps
from flask import session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash
from models import get_db


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def create_session(user_id, remember=False):
    """创建登录会话"""
    session['user_id'] = user_id
    session.permanent = remember


def destroy_session():
    """销毁登录会话"""
    session.pop('user_id', None)


def get_current_user():
    """获取当前登录用户，未登录返回 None"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return user


def login_required(f):
    """登录验证装饰器（已禁用，自动登录默认用户）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def get_user_id():
    """快捷获取当前用户ID"""
    return session.get('user_id', 1)
