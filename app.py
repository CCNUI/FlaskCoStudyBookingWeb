# /app.py (v3 - 支持管理员修改时间段)

import os
import redis
import json
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy

# --- 应用配置 ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-very-secret-key-for-development')

# --- 默认常量 ---
DEFAULT_TIME_SLOTS = [
    "06:00-06:40", "06:40-07:20", "07:20-08:00", "08:00-08:40",
    "08:40-09:20", "09:20-10:00", "10:00-10:40", "10:40-11:20",
    "11:20-12:00", "12:00-12:40", "12:40-13:20", "13:20-14:00",
    "14:00-14:40", "14:40-15:20", "15:20-16:00", "16:00-16:40",
    "16:40-17:20", "17:20-18:00", "18:00-18:40", "18:40-19:20",
    "19:20-20:00", "20:00-20:40", "20:40-21:20", "21:20-22:00"
]
TIME_SLOTS_KEY = "config:time_slots"  # 用于Redis的Key

# --- 条件数据库配置 ---
kv_url = os.environ.get('KV_URL')
db_is_redis = bool(kv_url)
db = None

# SQLite 模型定义
if not db_is_redis:
    basedir = os.path.abspath(os.path.dirname(__file__))
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'local_dev.sqlite3')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    sql_alchemy_db = SQLAlchemy(app)


    class Reservation(sql_alchemy_db.Model):
        id = sql_alchemy_db.Column(sql_alchemy_db.String, primary_key=True)
        user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100), nullable=False)


    class SpecialDate(sql_alchemy_db.Model):
        date_str = sql_alchemy_db.Column(sql_alchemy_db.String(20), primary_key=True)


    class Log(sql_alchemy_db.Model):
        id = sql_alchemy_db.Column(sql_alchemy_db.Integer, primary_key=True)
        # ... 其他列
        action = sql_alchemy_db.Column(sql_alchemy_db.String(20));
        date = sql_alchemy_db.Column(sql_alchemy_db.String(20));
        time_slot = sql_alchemy_db.Column(sql_alchemy_db.String(20));
        old_user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100));
        new_user_name = sql_alchemy_db.Column(sql_alchemy_db.String(100));
        timestamp = sql_alchemy_db.Column(sql_alchemy_db.String(30))


    class TimeSlot(sql_alchemy_db.Model):
        id = sql_alchemy_db.Column(sql_alchemy_db.Integer, primary_key=True)
        slot_value = sql_alchemy_db.Column(sql_alchemy_db.String(50), unique=True, nullable=False)
        order = sql_alchemy_db.Column(sql_alchemy_db.Integer)

# Redis 连接
if db_is_redis:
    print("INFO: Application is running in REDIS mode.")
    try:
        db = redis.from_url(kv_url, decode_responses=True)
        if not db.exists(TIME_SLOTS_KEY):
            db.rpush(TIME_SLOTS_KEY, *DEFAULT_TIME_SLOTS)
    except Exception as e:
        print(f"ERROR: Could not connect to Redis database: {e}");
        db = None
else:
    print("INFO: Application is running in SQLITE mode.")
    db = sql_alchemy_db


# --- 自定义Flask CLI命令 ---
@app.cli.command("init-db")
def init_db_command():
    if db_is_redis:
        print("INFO: Redis mode. No DB initialization needed.")
        # For Redis, we could add logic to reset keys if needed
        if not db.exists(TIME_SLOTS_KEY):
            db.rpush(TIME_SLOTS_KEY, *DEFAULT_TIME_SLOTS)
            print("SUCCESS: Default time slots have been set in Redis.")
        return
    with app.app_context():
        db.create_all()
        if not TimeSlot.query.first():
            for i, slot in enumerate(DEFAULT_TIME_SLOTS):
                db.session.add(TimeSlot(slot_value=slot, order=i))
            db.session.commit()
    print("SUCCESS: SQLite database and tables initialized with default time slots.")


# --- 辅助函数 & 装饰器 ---
def get_time_slots():
    """从数据库获取当前的时间段列表"""
    if db_is_redis:
        return db.lrange(TIME_SLOTS_KEY, 0, -1)
    else:
        slots = TimeSlot.query.order_by(TimeSlot.order).all()
        return [s.slot_value for s in slots]


def check_db_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ... (代码无变化)
        db_handle = db if db_is_redis else db.session
        if db_handle is None: return "数据库连接失败，请检查服务器配置或环境变量。", 503
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # ... (代码无变化)
        if not session.get('is_admin'): return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


def log_action(action, date, time_slot, old_user, new_user):
    # ... (代码无变化)
    log_entry_data = {"action": action, "date": date, "time_slot": time_slot, "old_user_name": old_user or "无",
                      "new_user_name": new_user or "无", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if db_is_redis:
        log_entry_data["id"] = int(datetime.now().timestamp() * 1000); db.lpush("logs", json.dumps(log_entry_data))
    else:
        new_log = Log(**log_entry_data); db.session.add(new_log); db.session.commit()


# --- 路由定义 ---
@app.route('/')
def welcome(): return render_template('welcome.html')


@app.route('/schedule')
@check_db_connection
def schedule():
    # ... (大部分代码无变化)
    start_date_str = request.args.get('start_date')
    today = date.today()
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today
    current_monday = start_date - timedelta(days=start_date.weekday())
    week_dates = [(current_monday + timedelta(days=i)) for i in range(7)]
    reservations = {}
    special_dates = set()
    time_slots = get_time_slots()  # *** 修改点：从数据库动态获取 ***

    # ... (数据库查询逻辑无变化, 只是使用的time_slots是动态的)
    if db_is_redis:
        special_dates = db.smembers('special_dates') or set()
        with db.pipeline() as pipe:
            for d in week_dates:
                for ts in time_slots: pipe.get(f"reservation:{d.isoformat()}:{ts}")
            results = pipe.execute()
        i = 0
        for d in week_dates:
            for ts in time_slots:
                if results[i]: reservations[f"{d.isoformat()}:{ts}"] = results[i]
                i += 1
    else:
        res_results = Reservation.query.all();
        special_dates = {sd.date_str for sd in SpecialDate.query.all()}
        for res in res_results: reservations[res.id] = res.user_name

    return render_template(
        'index.html',
        week_dates=week_dates, time_slots=time_slots, reservations=reservations,
        # ... (其他参数无变化)
        special_dates=special_dates, special_date_name="斋日", date_range_start=week_dates[0],
        date_range_end=week_dates[-1], prev_week_start_date=(current_monday - timedelta(weeks=1)).isoformat(),
        next_week_start_date=(current_monday + timedelta(weeks=1)).isoformat(), today_start_date=today.isoformat()
    )


@app.route('/submit_reservation', methods=['POST'])
@check_db_connection
def submit_reservation():
    data = request.get_json()
    res_date_str = data['date']

    # *** 修改点：增加时间约束 ***
    try:
        res_date_obj = date.fromisoformat(res_date_str)
        # 获取本周的周一日期
        today_monday = date.today() - timedelta(days=date.today().weekday())
        if res_date_obj < today_monday:
            return jsonify({"status": "error", "message": "无法修改或预约过去的时间段！"}), 403
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "日期格式无效"}), 400

    # ... (后续逻辑无变化)
    time_slot = data['time_slot'];
    new_name = data['name'].strip();
    key = f"reservation:{res_date_str}:{time_slot}";
    old_name = None;
    action = "none";
    message = "未知错误"
    if db_is_redis:
        old_name = db.get(key)
        if not new_name:
            if old_name: db.delete(key); action, message = "delete", "预约已删除"
        else:
            db.set(key, new_name);
            action = "update" if old_name else "create";
            message = f"预约已更新为: {new_name}" if old_name else "预约成功！"
    else:
        old_res = Reservation.query.get(key);
        old_name = old_res.user_name if old_res else None
        if not new_name:
            if old_res: db.session.delete(old_res); action, message = "delete", "预约已删除"
        else:
            if old_res:
                old_res.user_name = new_name; action = "update"
            else:
                new_res = Reservation(id=key, user_name=new_name); db.session.add(new_res); action = "create"
            message = f"预约已更新为: {new_name}" if old_name else "预约成功！"
        db.session.commit()
    if action not in ["none", "error"]:
        log_action(action, res_date_str, time_slot, old_name, new_name); return jsonify(
            {"status": "success", "message": message, "action": action, "new_user": new_name})
    else:
        return jsonify({"status": "info", "message": "该时段无预约，无需操作", "action": "none"})


@app.route('/logs')
@check_db_connection
def logs():
    # ... (代码无变化)
    log_entries = []
    if db_is_redis:
        log_entries = [json.loads(log) for log in db.lrange('logs', 0, -1)]
    else:
        log_entries = [l.__dict__ for l in Log.query.order_by(Log.id.desc()).all()]
    return render_template('logs.html', logs=log_entries)


@app.route('/admin', methods=['GET', 'POST'])
@check_db_connection
@admin_required
def admin():
    # *** 修改点：增加对时间段的增删逻辑 ***
    if request.method == 'POST':
        # --- 特殊日期管理 ---
        date_to_add = request.form.get('add_date')
        date_to_delete = request.form.get('delete_date')
        # --- 时间段管理 ---
        timeslot_to_add = request.form.get('add_timeslot_value')
        timeslot_to_delete = request.form.get('delete_timeslot_value')

        if db_is_redis:
            if date_to_add: db.sadd('special_dates', date_to_add)
            if date_to_delete: db.srem('special_dates', date_to_delete)
            if timeslot_to_add: db.rpush(TIME_SLOTS_KEY, timeslot_to_add)
            if timeslot_to_delete: db.lrem(TIME_SLOTS_KEY, 1, timeslot_to_delete)
        else:  # SQLite
            if date_to_add and not SpecialDate.query.get(date_to_add): db.session.add(SpecialDate(date_str=date_to_add))
            if date_to_delete:
                date_obj = SpecialDate.query.get(date_to_delete)
                if date_obj: db.session.delete(date_obj)

            if timeslot_to_add and not TimeSlot.query.filter_by(slot_value=timeslot_to_add).first():
                max_order = db.session.query(db.func.max(TimeSlot.order)).scalar() or 0
                db.session.add(TimeSlot(slot_value=timeslot_to_add, order=max_order + 1))

            if timeslot_to_delete:
                slot_obj = TimeSlot.query.filter_by(slot_value=timeslot_to_delete).first()
                if slot_obj: db.session.delete(slot_obj)

            db.session.commit()
        return redirect(url_for('admin'))

    # --- GET请求的渲染逻辑 ---
    special_dates, time_slots = set(), []
    if db_is_redis:
        special_dates = sorted(list(db.smembers('special_dates') or set()))
        time_slots = db.lrange(TIME_SLOTS_KEY, 0, -1)
    else:
        special_dates = sorted([d.date_str for d in SpecialDate.query.all()])
        time_slots = [s.slot_value for s in TimeSlot.query.order_by(TimeSlot.order).all()]

    return render_template('admin.html', special_dates=special_dates, time_slots=time_slots, special_date_name="斋日")


# --- admin 登录登出路由 (无变化) ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # ... (代码无变化)
    admin_password = os.environ.get('ADMIN_PASSWORD');
    if not admin_password: return "管理员密码未在环境变量中设置。", 500
    if session.get('is_admin'): return redirect(url_for('admin'))
    if request.method == 'POST':
        if request.form.get('password') == admin_password:
            session['is_admin'] = True; return redirect(url_for('admin'))
        else:
            return render_template('admin.html', error="密码错误", login_required=True)
    return render_template('admin.html', login_required=True)


@app.route('/admin/logout')
def admin_logout():
    # ... (代码无变化)
    session.pop('is_admin', None);
    return redirect(url_for('admin_login'))