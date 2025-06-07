# /app.py (v5 - 稳定修复版)

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
DEFAULT_TIME_SLOTS = ["06:40-07:20", "06:50-07:20"]
TIME_SLOTS_KEY = "config:time_slots"

# --- 条件数据库配置 ---
kv_url = os.environ.get('KV_URL');
db_is_redis = bool(kv_url);
db = None
if not db_is_redis:
    basedir = os.path.abspath(os.path.dirname(__file__));
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'local_dev.sqlite3')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    sql_alchemy_db = SQLAlchemy(app)


    class Reservation(sql_alchemy_db.Model): id = sql_alchemy_db.Column(sql_alchemy_db.String,
                                                                        primary_key=True); user_name = sql_alchemy_db.Column(
        sql_alchemy_db.String(100), nullable=False)


    class SpecialDate(sql_alchemy_db.Model): date_str = sql_alchemy_db.Column(sql_alchemy_db.String(20),
                                                                              primary_key=True)


    class Log(sql_alchemy_db.Model): id = sql_alchemy_db.Column(sql_alchemy_db.Integer,
                                                                primary_key=True); action = sql_alchemy_db.Column(
        sql_alchemy_db.String(20)); date = sql_alchemy_db.Column(
        sql_alchemy_db.String(20)); time_slot = sql_alchemy_db.Column(
        sql_alchemy_db.String(20)); old_user_name = sql_alchemy_db.Column(
        sql_alchemy_db.String(100)); new_user_name = sql_alchemy_db.Column(
        sql_alchemy_db.String(100)); timestamp = sql_alchemy_db.Column(sql_alchemy_db.String(30))


    class TimeSlot(sql_alchemy_db.Model): id = sql_alchemy_db.Column(sql_alchemy_db.Integer,
                                                                     primary_key=True); slot_value = sql_alchemy_db.Column(
        sql_alchemy_db.String(50), unique=True, nullable=False); order = sql_alchemy_db.Column(sql_alchemy_db.Integer)
if db_is_redis:
    print("INFO: Application is running in REDIS mode.")
    try:
        db = redis.from_url(kv_url, decode_responses=True)
        if not db.exists(TIME_SLOTS_KEY): db.rpush(TIME_SLOTS_KEY, *DEFAULT_TIME_SLOTS)
    except Exception as e:
        print(f"ERROR: Could not connect to Redis database: {e}"); db = None
else:
    print("INFO: Application is running in SQLITE mode."); db = sql_alchemy_db


# --- 自定义Flask CLI命令 ---
@app.cli.command("init-db")
def init_db_command():
    if db_is_redis:
        print("INFO: Redis mode. No DB initialization needed.")
        db.delete(TIME_SLOTS_KEY)  #
        db.rpush(TIME_SLOTS_KEY, *DEFAULT_TIME_SLOTS)
        print("SUCCESS: Default time slots have been reset in Redis.")
        return
    with app.app_context():
        db.create_all()
        if not TimeSlot.query.first():
            for i, slot in enumerate(DEFAULT_TIME_SLOTS): db.session.add(TimeSlot(slot_value=slot, order=i))
            db.session.commit()
    print("SUCCESS: SQLite database and tables initialized with default time slots.")


# --- 辅助函数 & 装饰器 ---
def get_time_slots():
    if db_is_redis:
        return db.lrange(TIME_SLOTS_KEY, 0, -1)
    else:
        return [s.slot_value for s in TimeSlot.query.order_by(TimeSlot.order).all()]


def check_db_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db_handle = db if db_is_redis else db.session
        if db_handle is None: return "数据库连接失败，请检查服务器配置或环境变量。", 503
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'): return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


def log_action(action, date, time_slot, old_user, new_user):
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
    start_date_str = request.args.get('start_date')
    today = date.today()
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today
    current_monday = start_date - timedelta(days=start_date.weekday())
    week_dates = [(current_monday + timedelta(days=i)) for i in range(7)]
    reservations = {};
    special_dates = set();
    time_slots = get_time_slots()
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
    return render_template('index.html', week_dates=week_dates, time_slots=time_slots, reservations=reservations,
                           special_dates=special_dates, special_date_name="斋日", date_range_start=week_dates[0],
                           date_range_end=week_dates[-1],
                           prev_week_start_date=(current_monday - timedelta(weeks=1)).isoformat(),
                           next_week_start_date=(current_monday + timedelta(weeks=1)).isoformat(),
                           today_start_date=today.isoformat())


@app.route('/submit_reservation', methods=['POST'])
@check_db_connection
def submit_reservation():
    data = request.get_json()
    if not all(k in data for k in ['date', 'time_slot', 'name']):
        return jsonify({"status": "error", "message": "请求数据不完整"}), 400

    res_date_str = data['date']
    try:
        res_date_obj = date.fromisoformat(res_date_str)
        today_monday = date.today() - timedelta(days=date.today().weekday())
        if res_date_obj < today_monday: return jsonify(
            {"status": "error", "message": "无法修改或预约过去的时间段！"}), 403
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "日期格式无效"}), 400

    time_slot = data['time_slot'];
    new_name = data['name'].strip();
    key = f"reservation:{res_date_str}:{time_slot}";
    old_name = None;
    action = "none"

    if db_is_redis:
        old_name = db.get(key)
        if not new_name:
            if old_name: db.delete(key); action = "delete"
        else:
            db.set(key, new_name); action = "update" if old_name else "create"
    else:
        old_res = Reservation.query.get(key);
        old_name = old_res.user_name if old_res else None
        if not new_name:
            if old_res: db.session.delete(old_res); action = "delete"
        else:
            if old_res:
                old_res.user_name = new_name; action = "update"
            else:
                new_res = Reservation(id=key, user_name=new_name); db.session.add(new_res); action = "create"
        db.session.commit()

    if action == "create":
        message = "预约成功！"
    elif action == "update":
        message = f"预约已更新为: {new_name}"
    elif action == "delete":
        message = "预约已删除"
    else:
        return jsonify({"status": "info", "message": "该时段无预约，无需操作", "action": "none"})

    log_action(action, res_date_str, time_slot, old_name, new_name)
    return jsonify({"status": "success", "message": message, "action": action, "new_user": new_name})


@app.route('/logs')
@check_db_connection
def logs():
    if db_is_redis:
        log_entries = [json.loads(log) for log in db.lrange('logs', 0, -1)]
    else:
        log_entries = [l.__dict__ for l in Log.query.order_by(Log.id.desc()).all()]
    return render_template('logs.html', logs=log_entries)


@app.route('/admin', methods=['GET', 'POST'])
@check_db_connection
@admin_required
def admin():
    if request.method == 'POST':
        # 使用 if/elif/else 结构确保一次只处理一个表单提交
        if 'add_date' in request.form:
            date_to_add = request.form.get('add_date')
            if db_is_redis:
                db.sadd('special_dates', date_to_add)
            elif not SpecialDate.query.get(date_to_add):
                db.session.add(SpecialDate(date_str=date_to_add)); db.session.commit()
        elif 'delete_date' in request.form:
            date_to_delete = request.form.get('delete_date')
            if db_is_redis:
                db.srem('special_dates', date_to_delete)
            else:
                date_obj = SpecialDate.query.get(date_to_delete)
                if date_obj: db.session.delete(date_obj); db.session.commit()
        elif 'add_timeslot_value' in request.form:
            timeslot_to_add = request.form.get('add_timeslot_value')
            if db_is_redis:
                db.rpush(TIME_SLOTS_KEY, timeslot_to_add)
            elif timeslot_to_add and not TimeSlot.query.filter_by(slot_value=timeslot_to_add).first():
                max_order = db.session.query(db.func.max(TimeSlot.order)).scalar() or 0
                db.session.add(TimeSlot(slot_value=timeslot_to_add, order=max_order + 1));
                db.session.commit()
        elif 'delete_timeslot_value' in request.form:
            timeslot_to_delete = request.form.get('delete_timeslot_value')
            if db_is_redis:
                db.lrem(TIME_SLOTS_KEY, 1, timeslot_to_delete)
            else:
                slot_obj = TimeSlot.query.filter_by(slot_value=timeslot_to_delete).first()
                if slot_obj: db.session.delete(slot_obj); db.session.commit()
        elif 'edit_timeslot_original' in request.form:
            original_value = request.form.get('edit_timeslot_original')
            new_value = request.form.get('edit_timeslot_new')
            if original_value and new_value:
                if db_is_redis:
                    db.lset(TIME_SLOTS_KEY, db.lrange(TIME_SLOTS_KEY, 0, -1).index(original_value), new_value)
                else:
                    slot_obj = TimeSlot.query.filter_by(slot_value=original_value).first()
                    if slot_obj: slot_obj.slot_value = new_value; db.session.commit()
        return redirect(url_for('admin'))

    slot_to_edit = request.args.get('edit_slot')
    special_dates = sorted(list(db.smembers('special_dates') or set())) if db_is_redis else sorted(
        [d.date_str for d in SpecialDate.query.all()])
    time_slots = get_time_slots()
    return render_template('admin.html', special_dates=special_dates, time_slots=time_slots, special_date_name="斋日",
                           slot_to_edit=slot_to_edit)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
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
    session.pop('is_admin', None);
    return redirect(url_for('admin_login'))