# /app.py (完整修正版，支持Redis和SQLite双模式)

import os
import redis
import json
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy

# --- 应用配置 ---
app = Flask(__name__)
# 用于session加密，请务必在生产环境中替换为一个安全的密钥
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-very-secret-key-for-development')

# --- 条件数据库配置 ---
# 检查是否配置了KV_URL，以此决定使用Redis还是SQLite
kv_url = os.environ.get('KV_URL')
db_is_redis = bool(kv_url)
db = None  # 数据库操作句柄

# SQLite 模型定义 (仅在SQLite模式下使用)
if not db_is_redis:
    basedir = os.path.abspath(os.path.dirname(__file__))
    # 确保 instance 文件夹存在，用于存放数据库文件
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'local_dev.sqlite3')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    sql_alchemy_db = SQLAlchemy(app)


    class Reservation(sql_alchemy_db.Model):
        # 主键格式: "YYYY-MM-DD:HH:MM-HH:MM"
        id = sql_alchemy_db.Column(sql_alchemy_db.String, primary_key=True)
        user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100), nullable=False)


    class SpecialDate(sql_alchemy_db.Model):
        date_str = sql_alchemy_db.Column(sql_alchemy_db.String(20), primary_key=True)


    class Log(sql_alchemy_db.Model):
        id = sql_alchemy_db.Column(sql_alchemy_db.Integer, primary_key=True)
        action = sql_alchemy_db.Column(sql_alchemy_db.String(20))
        date = sql_alchemy_db.Column(sql_alchemy_db.String(20))
        time_slot = sql_alchemy_db.Column(sql_alchemy_db.String(20))
        old_user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100))
        new_user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100))
        timestamp = sql_alchemy_db.Column(sql_alchemy_db.String(30))

# 连接到 Redis (仅在Redis模式下使用)
if db_is_redis:
    print("INFO: Application is running in REDIS mode.")
    try:
        db = redis.from_url(kv_url, decode_responses=True)
        db.ping()  # 测试连接
    except Exception as e:
        print(f"ERROR: Could not connect to Redis database: {e}")
        db = None
else:
    print("INFO: Application is running in SQLITE mode.")
    db = sql_alchemy_db


# --- 自定义Flask CLI命令 ---
@app.cli.command("init-db")
def init_db_command():
    """为SQLite模式创建数据库表。"""
    if db_is_redis:
        print("INFO: Redis mode is active. No database initialization needed.")
        return

    with app.app_context():
        db.create_all()
    print("SUCCESS: SQLite database and tables have been successfully initialized.")


# --- 时间段常量 ---
TIME_SLOTS = [
    "06:00-06:40", "06:40-07:20", "07:20-08:00", "08:00-08:40",
    "08:40-09:20", "09:20-10:00", "10:00-10:40", "10:40-11:20",
    "11:20-12:00", "12:00-12:40", "12:40-13:20", "13:20-14:00",
    "14:00-14:40", "14:40-15:20", "15:20-16:00", "16:00-16:40",
    "16:40-17:20", "17:20-18:00", "18:00-18:40", "18:40-19:20",
    "19:20-20:00", "20:00-20:40", "20:40-21:20", "21:20-22:00"
]


# --- 辅助函数 & 装饰器 ---
def check_db_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db_handle = db if db_is_redis else db.session
        if db_handle is None:
            return "数据库连接失败，请检查服务器配置或环境变量。", 503
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


def log_action(action, date, time_slot, old_user, new_user):
    """记录操作日志"""
    log_entry_data = {
        "action": action, "date": date, "time_slot": time_slot,
        "old_user_name": old_user or "无", "new_user_name": new_user or "无",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if db_is_redis:
        log_entry_data["id"] = int(datetime.now().timestamp() * 1000)
        db.lpush("logs", json.dumps(log_entry_data))
    else:
        new_log = Log(**log_entry_data)
        db.session.add(new_log)
        db.session.commit()


# --- 路由定义 ---
@app.route('/')
def welcome():
    return render_template('welcome.html')


@app.route('/schedule')
@check_db_connection
def schedule():
    start_date_str = request.args.get('start_date')
    today = date.today()
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today

    current_monday = start_date - timedelta(days=start_date.weekday())
    week_dates = [(current_monday + timedelta(days=i)) for i in range(7)]

    reservations = {}
    special_dates = set()

    if db_is_redis:
        # --- REDIS LOGIC ---
        special_dates = db.smembers('special_dates') or set()
        with db.pipeline() as pipe:
            for d in week_dates:
                for ts in TIME_SLOTS:
                    pipe.get(f"reservation:{d.isoformat()}:{ts}")
            results = pipe.execute()
        i = 0
        for d in week_dates:
            for ts in TIME_SLOTS:
                if results[i]:
                    reservations[f"{d.isoformat()}:{ts}"] = results[i]
                i += 1
    else:
        # --- SQLITE LOGIC ---
        res_results = Reservation.query.all()
        for res in res_results:
            reservations[res.id] = res.user_name

        sd_results = SpecialDate.query.all()
        special_dates = {sd.date_str for sd in sd_results}

    return render_template(
        'index.html',
        week_dates=week_dates, time_slots=TIME_SLOTS, reservations=reservations,
        special_dates=special_dates, special_date_name="斋日",
        date_range_start=week_dates[0], date_range_end=week_dates[-1],
        prev_week_start_date=(current_monday - timedelta(weeks=1)).isoformat(),
        next_week_start_date=(current_monday + timedelta(weeks=1)).isoformat(),
        today_start_date=today.isoformat()
    )


@app.route('/submit_reservation', methods=['POST'])
@check_db_connection
def submit_reservation():
    data = request.get_json()
    res_date = data['date']
    time_slot = data['time_slot']
    new_name = data['name'].strip()
    key = f"reservation:{res_date}:{time_slot}"

    old_name = None
    action = "none"
    message = "未知错误"

    if db_is_redis:
        # --- REDIS LOGIC ---
        old_name = db.get(key)
        if not new_name:
            if old_name:
                db.delete(key)
                action, message = "delete", "预约已删除"
        else:
            db.set(key, new_name)
            action = "update" if old_name else "create"
            message = f"预约已更新为: {new_name}" if old_name else "预约成功！"
    else:
        # --- SQLITE LOGIC ---
        old_res = Reservation.query.get(key)
        old_name = old_res.user_name if old_res else None
        if not new_name:
            if old_res:
                db.session.delete(old_res)
                action, message = "delete", "预约已删除"
        else:
            if old_res:
                old_res.user_name = new_name
                action = "update"
            else:
                new_res = Reservation(id=key, user_name=new_name)
                db.session.add(new_res)
                action = "create"
            message = f"预约已更新为: {new_name}" if old_name else "预约成功！"
        db.session.commit()

    if action not in ["none", "error"]:
        log_action(action, res_date, time_slot, old_name, new_name)
        return jsonify({"status": "success", "message": message, "action": action, "new_user": new_name})
    else:
        return jsonify({"status": "info", "message": "该时段无预约，无需操作", "action": "none"})


@app.route('/logs')
@check_db_connection
def logs():
    log_entries = []
    if db_is_redis:
        log_strings = db.lrange('logs', 0, -1)
        log_entries = [json.loads(log) for log in log_strings]
    else:
        logs_from_db = Log.query.order_by(Log.id.desc()).all()
        log_entries = [l.__dict__ for l in logs_from_db]

    return render_template('logs.html', logs=log_entries)


@app.route('/admin', methods=['GET', 'POST'])
@check_db_connection
@admin_required
def admin():
    if request.method == 'POST':
        date_to_add = request.form.get('add_date')
        date_to_delete = request.form.get('delete_date')
        if db_is_redis:
            if date_to_add: db.sadd('special_dates', date_to_add)
            if date_to_delete: db.srem('special_dates', date_to_delete)
        else:
            if date_to_add and not SpecialDate.query.get(date_to_add):
                db.session.add(SpecialDate(date_str=date_to_add))
            if date_to_delete:
                date_obj = SpecialDate.query.get(date_to_delete)
                if date_obj: db.session.delete(date_obj)
            db.session.commit()
        return redirect(url_for('admin'))

    special_dates = set()
    if db_is_redis:
        special_dates = sorted(list(db.smembers('special_dates') or set()))
    else:
        special_dates = sorted([d.date_str for d in SpecialDate.query.all()])

    return render_template('admin.html', special_dates=special_dates, special_date_name="斋日")


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if not admin_password:
        return "管理员密码未在环境变量中设置。", 500

    if session.get('is_admin'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        if request.form.get('password') == admin_password:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        else:
            return render_template('admin.html', error="密码错误", login_required=True)

    return render_template('admin.html', login_required=True)


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))