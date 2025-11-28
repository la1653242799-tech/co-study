import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime, date

# ==========================================
# 0. 数据库初始化 (新增 role 字段)
# ==========================================
def init_db():
    conn = sqlite3.connect('study_system.db', check_same_thread=False)
    c = conn.cursor()
    
    # 用户表：新增 role 字段 (admin 或 employee)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT,
                  role TEXT DEFAULT 'employee', 
                  learning_goal TEXT DEFAULT '每日学习2小时',
                  created_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS daily_records
                 (record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  record_date DATE,
                  duration_minutes INTEGER DEFAULT 0,
                  is_checked_in BOOLEAN DEFAULT 0,
                  last_update_time TIMESTAMP)''')
    
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
# 工具函数
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
# 界面逻辑
# ==========================================
st.set_page_config(page_title="Co-Study 协作学习", page_icon="📚", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'role' not in st.session_state:
    st.session_state['role'] = 'employee' # 默认为员工

# --- 登录与注册 ---
if not st.session_state['logged_in']:
    st.title("🎓 Co-Study 协作学习平台")
    
    tab1, tab2 = st.tabs(["登录", "注册"])
    
    with tab1:
        username = st.text_input("用户名")
        password = st.text_input("密码", type='password')
        if st.button("立即登录"):
            c = conn.cursor()
            # 获取 user_id, password_hash, 和 role
            c.execute('SELECT user_id, password_hash, role FROM users WHERE username=?', (username,))
            data = c.fetchall()
            if data and check_hashes(password, data[0][1]):
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['user_id'] = data[0][0]
                st.session_state['role'] = data[0][2] # 保存身份信息
                st.success(f"登录成功！欢迎回来，{data[0][2]}") 
                st.experimental_rerun()
            else:
                st.error("用户名或密码错误")

    with tab2:
        st.write("注册新账号")
        new_user = st.text_input("设置用户名", key="reg_user")
        new_pass = st.text_input("设置密码", type='password', key="reg_pass")
        
        # 注册身份选择
        is_admin = st.checkbox("注册为管理员？")
        admin_key = ""
        if is_admin:
            admin_key = st.text_input("请输入管理员密钥 (提示: 不告诉你)", type="password")
        
        if st.button("注册账号"):
            role = 'employee'
            if is_admin:
                if admin_key == "不告诉你": # 硬编码的管理员密钥
                    role = 'admin'
                else:
                    st.error("管理员密钥错误！无法注册为管理员。")
                    st.stop()
            
            try:
                c = conn.cursor()
                c.execute('INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,?)', 
                          (new_user, make_hashes(new_pass), role, datetime.now()))
                conn.commit()
                st.success(f"注册成功！身份：{'管理员' if role=='admin' else '普通员工'}")
            except sqlite3.IntegrityError:
                st.warning("该用户名已被使用。")

# --- 登录后逻辑 ---
else:
    user_id = st.session_state['user_id']
    username = st.session_state['username']
    role = st.session_state['role']
    
    # 侧边栏：根据身份显示不同菜单
    st.sidebar.title(f"身份: {'👨‍💼 管理员' if role=='admin' else '👨‍💻 员工'}")
    
    if role == 'admin':
        menu = ["全员数据看板", "成员管理", "公共社区管理"]
    else:
        menu = ["个人仪表盘", "公共共享空间", "个人设置"]
        
    choice = st.sidebar.radio("导航", menu)
    
    if st.sidebar.button("退出登录"):
        st.session_state['logged_in'] = False
        st.experimental_rerun()

    # ==========================================
    # 【管理员界面】 Admin Interface
    # ==========================================
    if role == 'admin':
        if choice == "全员数据看板":
            st.header("📊 全员学习概况")
            
            # 统计数据
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT SUM(duration_minutes) FROM daily_records WHERE record_date=?", (date.today(),))
            total_time = c.fetchone()[0] or 0
            
            k1, k2, k3 = st.columns(3)
            k1.metric("总用户数", total_users)
            k2.metric("今日全员总学时", f"{total_time} 分钟")
            k3.metric("管理员状态", "在线")
            
            st.divider()
            st.subheader("今日打卡情况")
            
            # 连表查询，显示谁打了卡
            query = """
                SELECT u.username, d.duration_minutes, d.is_checked_in 
                FROM users u 
                LEFT JOIN daily_records d ON u.user_id = d.user_id AND d.record_date = ?
                WHERE u.role = 'employee'
            """
            df = pd.read_sql_query(query, conn, params=(date.today(),))
            df['状态'] = df['is_checked_in'].apply(lambda x: '✅ 已达标' if x==1 else '🚧 未达标')
            df['今日时长(分)'] = df['duration_minutes'].fillna(0)
            
            st.dataframe(df[['username', '今日时长(分)', '状态']])

        elif choice == "成员管理":
            st.header("👥 成员列表")
            users = pd.read_sql_query("SELECT user_id, username, role, created_at FROM users", conn)
            st.table(users)
            st.info("提示：管理员账号不可被删除。")

        elif choice == "公共社区管理":
            st.header("🛡️ 社区内容审核")
            c = conn.cursor()
            c.execute("SELECT post_id, author_name, title, content, timestamp FROM shared_posts ORDER BY timestamp DESC")
            posts = c.fetchall()
            
            for p in posts:
                with st.expander(f"{p[1]}: {p[2]}"):
                    st.write(p[3])
                    st.caption(f"发布时间: {p[4]}")
                    if st.button("🗑️ 删除违规帖", key=f"del_{p[0]}"):
                        c.execute("DELETE FROM shared_posts WHERE post_id=?", (p[0],))
                        conn.commit()
                        st.warning("帖子已删除！")
                        st.experimental_rerun()

    # ==========================================
    # 【员工界面】 Employee Interface (保持原样)
    # ==========================================
    else:
        if choice == "个人仪表盘":
            # 获取今日数据
            c = conn.cursor()
            c.execute("SELECT learning_goal FROM users WHERE user_id=?", (user_id,))
            current_goal = c.fetchone()[0]
            duration, is_checked = get_today_record(user_id)
            target = 120 
            
            st.header(f"👋 你好, {username}")
            st.caption(f"当前目标: {current_goal}")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader("📅 今日学习进度")
                progress_val = min(duration / target, 1.0)
                st.progress(progress_val)
                if is_checked:
                    st.markdown(f"### ✅ 已达标！ (累计: {duration} 分钟)")
                    st.balloons()
                else:
                    st.markdown(f"### 🚧 加油中 (累计: {duration} / {target} 分钟)")
                    st.info(f"距离今天的目标还差 {target - duration} 分钟")

            with col2:
                st.metric("今日状态", "已完成" if is_checked else "未完成")

            st.divider()
            st.subheader("⏱️ 记录时间")
            
            # 简化的手动录入
            with st.form("manual_add"):
                add_min = st.number_input("增加学习分钟数", 1, 300, 10)
                if st.form_submit_button("打卡提交"):
                    update_learning_time(user_id, add_min)
                    st.success(f"成功记录 {add_min} 分钟！")
                    st.experimental_rerun()

        elif choice == "公共共享空间":
            st.title("🌍 资源广场")
            tab_view, tab_post = st.tabs(["浏览", "发布"])
            with tab_post:
                with st.form("share"):
                    p_type = st.selectbox("类型", ["心得", "资源", "提问"])
                    title = st.text_input("标题")
                    content = st.text_area("内容")
                    if st.form_submit_button("发布"):
                        c = conn.cursor()
                        c.execute("INSERT INTO shared_posts (user_id, author_name, post_type, title, content, timestamp) VALUES (?,?,?,?,?,?)",
                                  (user_id, username, p_type, title, content, datetime.now()))
                        conn.commit()
                        st.success("发布成功！")
            with tab_view:
                c = conn.cursor()
                c.execute("SELECT author_name, post_type, title, content, timestamp FROM shared_posts ORDER BY timestamp DESC")
                posts = c.fetchall()
                for p in posts:
                    with st.expander(f"[{p[1]}] {p[2]} - {p[0]}"):
                        st.write(p[3])

        elif choice == "个人设置":
            st.title("⚙️ 设置")
            c = conn.cursor()
            c.execute("SELECT learning_goal FROM users WHERE user_id=?", (user_id,))
            current_goal = c.fetchone()[0]
            new_goal = st.text_input("学习目标", value=current_goal)
            if st.button("更新"):
                c.execute("UPDATE users SET learning_goal=? WHERE user_id=?", (new_goal, user_id))
                conn.commit()
                st.success("已更新！")