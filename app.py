import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime, date
import time
import gspread
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# 设置访问 Google Sheets 的权限范围
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# 使用服务账号密钥文件进行身份验证
creds = ServiceAccountCredentials.from_json_keyfile_name(
    './streamlit-study-479613-be8df28c38f9.json', scope
)

# 使用 gspread 授权
client = gspread.authorize(creds)

# 打开指定的 Google Sheets 文件
spreadsheet = client.open('study_data')

# 获取第一个工作表
worksheet = spreadsheet.sheet1

# 示例：读取数据并显示
data = worksheet.get_all_records()  # 获取所有记录
st.write(data)
# ==========================================
# 0. 兼容性设置 (自动处理新旧版本刷新命令)
# ==========================================
def rerun_app():
    """自动判断使用哪种刷新命令"""
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

# ==========================================
# 1. 数据库初始化
# ==========================================
def init_db():
    # check_same_thread=False 允许在 Streamlit Cloud 的多线程环境中运行
    conn = sqlite3.connect('study_system.db', check_same_thread=False)
    c = conn.cursor()
    
    # 用户表：包含身份 role (admin/employee)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT,
                  role TEXT DEFAULT 'employee', 
                  learning_goal TEXT DEFAULT '每日学习2小时',
                  created_at TIMESTAMP)''')
    
    # 每日记录表
    c.execute('''CREATE TABLE IF NOT EXISTS daily_records
                 (record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  record_date DATE,
                  duration_minutes INTEGER DEFAULT 0,
                  is_checked_in BOOLEAN DEFAULT 0,
                  last_update_time TIMESTAMP)''')
    
    # 共享帖子表
    c.execute('''CREATE TABLE IF NOT EXISTS shared_posts
                 (post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  author_name TEXT,
                  post_type TEXT,
                  title TEXT,
                  content TEXT,
                  timestamp DATETIME)''')
    conn.commit()
    return conn

conn = init_db()

# ==========================================
# 2. 工具函数
# ==========================================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def get_today_record(user_id):
    today = date.today()
    c = conn.cursor()
    c.execute("SELECT duration_minutes, is_checked_in FROM daily_records WHERE user_id=? AND record_date=?", (user_id, today))
    data = c.fetchone()
    if not data:
        c.execute("INSERT INTO daily_records (user_id, record_date, duration_minutes, is_checked_in, last_update_time) VALUES (?, ?, 0, 0, ?)", 
                  (user_id, today, datetime.now()))
        conn.commit()
        return 0, False
    return data[0], bool(data[1])

def update_learning_time(user_id, minutes_to_add):
    today = date.today()
    current_min, _ = get_today_record(user_id)
    new_total = current_min + minutes_to_add
    is_checked_in = 1 if new_total >= 120 else 0
    c = conn.cursor()
    c.execute("""UPDATE daily_records 
                 SET duration_minutes=?, is_checked_in=?, last_update_time=? 
                 WHERE user_id=? AND record_date=?""", 
              (new_total, is_checked_in, datetime.now(), user_id, today))
    conn.commit()
    return is_checked_in

# ==========================================
# 3. 界面逻辑
# ==========================================
st.set_page_config(page_title="Co-Study 协作平台", page_icon="🎓", layout="wide")

# 初始化 Session State
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'role' not in st.session_state:
    st.session_state['role'] = 'employee'
if 'timer_running' not in st.session_state:
    st.session_state['timer_running'] = False
if 'start_time' not in st.session_state:
    st.session_state['start_time'] = None

# ------------------------------------------
# 登录与注册页面
# ------------------------------------------
if not st.session_state['logged_in']:
    st.title("🎓 Co-Study 协作学习平台")
    st.markdown("#### 个人自律 · 团队共进")
    
    tab1, tab2 = st.tabs(["🔐 登录账号", "📝 注册新号"])
    
    with tab1:
        username = st.text_input("用户名")
        password = st.text_input("密码", type='password')
        if st.button("立即登录"):
            c = conn.cursor()
            c.execute('SELECT user_id, password_hash, role FROM users WHERE username=?', (username,))
            data = c.fetchall()
            if data and check_hashes(password, data[0][1]):
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['user_id'] = data[0][0]
                st.session_state['role'] = data[0][2]
                st.success(f"登录成功！欢迎回来，{username}")
                time.sleep(1)
                rerun_app()
            else:
                st.error("用户名或密码错误")

    with tab2:
        new_user = st.text_input("设置用户名", key="reg_user")
        new_pass = st.text_input("设置密码", type='password', key="reg_pass")
        
        # 管理员注册逻辑
        is_admin = st.checkbox("我是管理员？")
        admin_key = ""
        if is_admin:
            admin_key = st.text_input("请输入管理员密钥", type="password")
        
        if st.button("注册账号"):
            role = 'employee'
            # ⬇️ 这里的 admin666 是管理员注册密钥，你可以随意修改
            if is_admin:
                if admin_key == "不告诉你": 
                    role = 'admin'
                else:
                    st.error("管理员密钥错误！无法注册为管理员。")
                    st.stop()
            
            try:
                c = conn.cursor()
                c.execute('INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,?)', 
                          (new_user, make_hashes(new_pass), role, datetime.now()))
                conn.commit()
                st.success(f"注册成功！您的身份是：{'👨‍💼 管理员' if role=='admin' else '👨‍💻 普通员工'}")
                st.info("请切换到“登录账号”标签页进行登录。")
            except sqlite3.IntegrityError:
                st.warning("该用户名已被使用，请换一个。")

# ------------------------------------------
# 登录后的主界面
# ------------------------------------------
else:
    user_id = st.session_state['user_id']
    username = st.session_state['username']
    role = st.session_state['role']
    
    # 侧边栏导航
    st.sidebar.title(f"身份: {'👨‍💼 管理员' if role=='admin' else '👨‍💻 员工'}")
    
    if role == 'admin':
        menu = ["全员数据看板", "成员管理", "社区内容审核"]
    else:
        menu = ["个人仪表盘", "资源广场", "个人设置"]
        
    choice = st.sidebar.radio("导航菜单", menu)
    
    st.sidebar.divider()
    if st.sidebar.button("退出登录"):
        st.session_state['logged_in'] = False
        rerun_app()

    # ==========================
    # A. 管理员功能模块
    # ==========================
    if role == 'admin':
        if choice == "全员数据看板":
            st.header("📊 全员学习概况")
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT SUM(duration_minutes) FROM daily_records WHERE record_date=?", (date.today(),))
            total_time = c.fetchone()[0] or 0
            
            k1, k2, k3 = st.columns(3)
            k1.metric("总用户数", total_users)
            k2.metric("今日全员总学时", f"{total_time} 分钟")
            k3.metric("系统状态", "运行中")
            
            st.divider()
            st.subheader("📋 今日打卡明细")
            query = """
                SELECT u.username, d.duration_minutes, d.is_checked_in 
                FROM users u 
                LEFT JOIN daily_records d ON u.user_id = d.user_id AND d.record_date = ?
                WHERE u.role = 'employee'
            """
            df = pd.read_sql_query(query, conn, params=(date.today(),))
            df.columns = ["用户名", "今日时长", "达标状态"]
            df['达标状态'] = df['达标状态'].apply(lambda x: '✅ 已达标' if x==1 else '🚧 进行中')
            df['今日时长'] = df['今日时长'].fillna(0).astype(int)
            
            st.dataframe(df, use_container_width=True)

        elif choice == "成员管理":
            st.header("👥 成员列表")
            users = pd.read_sql_query("SELECT user_id, username, role, created_at FROM users", conn)
            st.dataframe(users)

        elif choice == "社区内容审核":
            st.header("🛡️ 社区风控中心")
            c = conn.cursor()
            c.execute("SELECT post_id, author_name, title, content, timestamp FROM shared_posts ORDER BY timestamp DESC")
            posts = c.fetchall()
            
            if not posts:
                st.info("社区暂无内容。")
            
            for p in posts:
                with st.expander(f"{p[1]} 发布: {p[2]} ({p[4]})"):
                    st.write(p[3])
                    if st.button("🗑️ 删除此贴", key=f"del_{p[0]}"):
                        c.execute("DELETE FROM shared_posts WHERE post_id=?", (p[0],))
                        conn.commit()
                        st.warning("帖子已删除！")
                        time.sleep(0.5)
                        rerun_app()

    # ==========================
    # B. 普通员工功能模块
    # ==========================
    else:
        if choice == "个人仪表盘":
            c = conn.cursor()
            c.execute("SELECT learning_goal FROM users WHERE user_id=?", (user_id,))
            res = c.fetchone()
            current_goal = res[0] if res else "未设置"
            duration, is_checked = get_today_record(user_id)
            target = 120 
            
            st.header(f"👋 你好, {username}")
            st.caption(f"🚩 当前Flag: {current_goal}")
            
            # 进度展示
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("📅 今日学习进度")
                progress_val = min(duration / target, 1.0)
                st.progress(progress_val)
                if is_checked:
                    st.success(f"🎉 恭喜！今日已达成 2 小时目标！(累计 {duration} 分钟)")
                    if duration == 120: # 刚达标时放个气球
                        st.balloons()
                else:
                    st.info(f"💪 加油！距离目标还差 {target - duration} 分钟")

            with col2:
                st.metric("今日状态", "✅ 完成" if is_checked else "⏳ 未完成")

            st.divider()

            # 计时与录入
            st.subheader("⏱️ 学习计时")
            t1, t2 = st.tabs(["专注计时器", "手动补录"])
            
            with t1:
                if not st.session_state['timer_running']:
                    if st.button("▶️ 开始专注"):
                        st.session_state['timer_running'] = True
                        st.session_state['start_time'] = datetime.now()
                        rerun_app()
                else:
                    st.warning(f"正在计时中... (开始于 {st.session_state['start_time'].strftime('%H:%M:%S')})")
                    if st.button("⏹️ 结束并保存"):
                        end_time = datetime.now()
                        start_time = st.session_state['start_time']
                        minutes = int((end_time - start_time).total_seconds() / 60)
                        
                        if minutes < 1:
                            st.warning("时间太短(少于1分钟)，本次不记录。")
                        else:
                            update_learning_time(user_id, minutes)
                            st.success(f"已保存！增加 {minutes} 分钟时长。")
                        
                        st.session_state['timer_running'] = False
                        st.session_state['start_time'] = None
                        time.sleep(1)
                        rerun_app()

            with t2:
                with st.form("manual_add"):
                    add_min = st.number_input("请输入学习分钟数", 1, 300, 30)
                    if st.form_submit_button("确认补录"):
                        update_learning_time(user_id, add_min)
                        st.success(f"补录成功！增加 {add_min} 分钟。")
                        time.sleep(1)
                        rerun_app()

        elif choice == "资源广场":
            st.title("🌍 团队资源广场")
            tab_view, tab_post = st.tabs(["👀 浏览动态", "✍️ 发布内容"])
            
            with tab_post:
                st.write("分享你的学习心得或资源：")
                with st.form("share"):
                    p_type = st.selectbox("标签", ["学习心得", "资源分享", "求助提问"])
                    title = st.text_input("标题")
                    content = st.text_area("详细内容")
                    if st.form_submit_button("发布到广场"):
                        c = conn.cursor()
                        c.execute("INSERT INTO shared_posts (user_id, author_name, post_type, title, content, timestamp) VALUES (?,?,?,?,?,?)",
                                  (user_id, username, p_type, title, content, datetime.now()))
                        conn.commit()
                        st.success("发布成功！大家都能看到了。")
            
            with tab_view:
                c = conn.cursor()
                c.execute("SELECT author_name, post_type, title, content, timestamp FROM shared_posts ORDER BY timestamp DESC")
                posts = c.fetchall()
                if not posts:
                    st.info("这里空空如也，快来抢沙发！")
                for p in posts:
                    with st.expander(f"[{p[1]}] {p[2]}  -- {p[0]} ({p[4]})"):
                        st.markdown(p[3])

        elif choice == "个人设置":
            st.title("⚙️ 个人设置")
            c = conn.cursor()
            c.execute("SELECT learning_goal FROM users WHERE user_id=?", (user_id,))
            current_goal = c.fetchone()[0]
            
            new_goal = st.text_input("修改学习目标 (Flag)", value=current_goal)
            if st.button("保存修改"):
                c.execute("UPDATE users SET learning_goal=? WHERE user_id=?", (new_goal, user_id))
                conn.commit()
                st.success("目标已更新！")
                time.sleep(0.5)
                rerun_app()