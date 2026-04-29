import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import re
from urllib.parse import quote

USERS_HEADERS = ["Username", "Password", "Role", "Full_Name", "Phone", "Created_At", "Sheet_Name"]
STUDENTS_HEADERS = [
    "Name", "Phone", "Parent_Phone", "Round", "Start_date", "Total_Sessions",
    "Completed_Sessions", "Remaining_Sessions", "Teacher", "Payment_Status", "Date_Registered",
    "Last_Status", "Last_Homework_Status", "Last_Exam_Grade", "Last_Session_Date", "Absent_Count"
]
ATTENDANCE_HEADERS = [
    "Student_Name", "Session_Date", "Status", "Homework", "Homework_Status",
    "Exam_Grade", "Notes", "Recorded_By", "Recorded_Role"
]


def is_quota_error(err):
    msg = str(err)
    return "429" in msg or "Quota exceeded" in msg


def parse_date_safe(value):
    if isinstance(value, datetime):
        return value.date()

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except:
            continue
    return None


def calculate_sessions(round_choice, start_date_value):
    total = int(ROUNDS_CONFIG.get(round_choice, {}).get("total", 0))
    per_week = int(ROUNDS_CONFIG.get(round_choice, {}).get("per_week", 1))

    start_date = parse_date_safe(start_date_value)
    if start_date is None:
        return total, 0, total

    today = datetime.now().date()
    if start_date > today:
        return total, 0, total

    elapsed_days = (today - start_date).days
    elapsed_weeks = (elapsed_days // 7) + 1
    completed = min(total, max(0, elapsed_weeks * per_week))
    remaining = max(0, total - completed)
    return total, completed, remaining

# --- إعدادات الصفحة ---
st.set_page_config(page_title="MCA Academy System", layout="wide", initial_sidebar_state="expanded")

# ── Global Design Theme (AcademySystem-inspired) ──────────────────────────────
st.markdown("""
<style>
/* ── Google Font: Inter ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Root tokens ── */
:root {
  --primary:      #2C7BE5;
  --primary-dark: #1a68d1;
  --bg:           #F5F6FA;
  --card-bg:      #FFFFFF;
  --sidebar-bg:   #FFFFFF;
  --text:         #12263F;
  --text-muted:   #95AAC9;
  --border:       #E3EBF6;
  --shadow:       0 4px 16px rgba(18,38,63,0.07);
  --radius:       8px;
}

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"], .main {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  background-color: var(--bg) !important;
  color: var(--text) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--sidebar-bg) !important;
  border-right: 1px solid var(--border) !important;
  box-shadow: 2px 0 8px rgba(18,38,63,0.05) !important;
}
[data-testid="stSidebar"] * {
  font-family: 'Inter', sans-serif !important;
  color: var(--text) !important;
}
[data-testid="stSidebar"] .stSuccess p {
  color: #00b050 !important;
}

/* ── Main header bar ── */
[data-testid="stHeader"] {
  background: var(--card-bg) !important;
  border-bottom: 1px solid var(--border) !important;
}

/* ── Page titles ── */
h1 {
  font-size: 1.75rem !important;
  font-weight: 700 !important;
  color: var(--text) !important;
  margin-bottom: 0.25rem !important;
  letter-spacing: -0.3px !important;
}
h2 {
  font-size: 1.35rem !important;
  font-weight: 600 !important;
  color: var(--text) !important;
}
h3 {
  font-size: 1.1rem !important;
  font-weight: 600 !important;
  color: var(--text) !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  padding: 1rem 1.25rem !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="stMetricLabel"] p {
  font-size: 0.78rem !important;
  font-weight: 500 !important;
  color: var(--text-muted) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.5px !important;
}
[data-testid="stMetricValue"] {
  font-size: 1.6rem !important;
  font-weight: 700 !important;
  color: var(--text) !important;
}

/* ── Buttons ── */
.stButton > button {
  background: var(--primary) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 6px !important;
  font-weight: 500 !important;
  font-size: 0.875rem !important;
  padding: 0.45rem 1.1rem !important;
  letter-spacing: 0.2px !important;
  transition: background 0.15s ease, box-shadow 0.15s ease !important;
  box-shadow: 0 1px 4px rgba(44,123,229,0.3) !important;
}
.stButton > button:hover {
  background: var(--primary-dark) !important;
  box-shadow: 0 3px 10px rgba(44,123,229,0.4) !important;
}
.stButton > button:active {
  background: #155ab8 !important;
}

/* ── Form submit buttons ── */
[data-testid="stFormSubmitButton"] > button {
  background: var(--primary) !important;
  color: #fff !important;
  border-radius: 6px !important;
  border: none !important;
  font-weight: 500 !important;
}
[data-testid="stFormSubmitButton"] > button:hover {
  background: var(--primary-dark) !important;
}

/* ── Text inputs / textareas / selects ── */
input[type="text"], input[type="password"], input[type="number"],
textarea, [data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
  color: var(--text) !important;
  font-size: 0.875rem !important;
  font-family: 'Inter', sans-serif !important;
  transition: border-color 0.15s ease !important;
}
input[type="text"]:focus, input[type="password"]:focus,
textarea:focus {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(44,123,229,0.12) !important;
  outline: none !important;
}

/* ── Select boxes ── */
[data-testid="stSelectbox"] > div > div {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
  font-size: 0.875rem !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 2px solid var(--border) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] button[role="tab"] {
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  color: var(--text-muted) !important;
  padding: 0.6rem 1.2rem !important;
  border: none !important;
  background: transparent !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -2px !important;
  transition: color 0.15s ease, border-color 0.15s ease !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color: var(--primary) !important;
  border-bottom: 2px solid var(--primary) !important;
  font-weight: 600 !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
  color: var(--text) !important;
}

/* ── Dataframes / tables ── */
[data-testid="stDataFrame"] {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow) !important;
  overflow: hidden !important;
}
[data-testid="stDataFrame"] th {
  background: #F8FAFD !important;
  color: var(--text-muted) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.5px !important;
  border-bottom: 2px solid var(--border) !important;
  padding: 10px 12px !important;
}
[data-testid="stDataFrame"] td {
  font-size: 0.875rem !important;
  color: var(--text) !important;
  padding: 9px 12px !important;
  border-bottom: 1px solid #F0F4F8 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow) !important;
  margin-bottom: 0.75rem !important;
}
[data-testid="stExpander"] summary {
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  color: var(--text) !important;
  padding: 0.75rem 1rem !important;
}

/* ── Alert boxes ── */
[data-testid="stAlert"] {
  border-radius: var(--radius) !important;
  border: none !important;
  font-size: 0.875rem !important;
}
.stInfo [data-testid="stAlert"] {
  background: #EBF5FB !important;
  border-left: 4px solid var(--primary) !important;
}
.stSuccess [data-testid="stAlert"] {
  background: #EAFAF1 !important;
  border-left: 4px solid #27AE60 !important;
}
.stWarning [data-testid="stAlert"] {
  background: #FEF9E7 !important;
  border-left: 4px solid #F39C12 !important;
}
.stError [data-testid="stAlert"] {
  background: #FDEDEC !important;
  border-left: 4px solid #E74C3C !important;
}

/* ── Info / Success / Warning shorthand ── */
div[data-testid="stAlert"] > div {
  font-family: 'Inter', sans-serif !important;
}

/* ── Divider ── */
hr {
  border: none !important;
  border-top: 1px solid var(--border) !important;
  margin: 1.25rem 0 !important;
}

/* ── Spinner / loading ── */
[data-testid="stSpinner"] {
  color: var(--primary) !important;
}

/* ── Radio buttons ── */
[data-testid="stRadio"] label {
  font-size: 0.875rem !important;
  color: var(--text) !important;
}

/* ── Checkbox ── */
[data-testid="stCheckbox"] label {
  font-size: 0.875rem !important;
  color: var(--text) !important;
}

/* ── Number input ── */
[data-testid="stNumberInput"] input {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}

/* ── Date input ── */
[data-testid="stDateInput"] input {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}

/* ── Forms ── */
[data-testid="stForm"] {
  background: var(--card-bg) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  padding: 1.25rem !important;
  box-shadow: var(--shadow) !important;
}

/* ── Main content padding ── */
.block-container {
  padding-top: 2rem !important;
  padding-bottom: 2rem !important;
  max-width: 1200px !important;
}

/* ── Sidebar logout button ── */
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  color: #E74C3C !important;
  border: 1px solid #E74C3C !important;
  box-shadow: none !important;
  font-size: 0.82rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: #FDEDEC !important;
  box-shadow: none !important;
}

/* ── mca-cal calendar (parent page) ── */
.mca-cal {
  border-collapse: collapse;
  width: 100%;
  font-family: 'Inter', sans-serif;
  direction: rtl;
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow);
}
.mca-cal th {
  background: var(--primary) !important;
  color: #fff !important;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.4px !important;
  padding: 10px 6px !important;
  border: 1px solid var(--primary-dark) !important;
}
.mca-cal td {
  border: 1px solid #E3EBF6 !important;
  min-width: 44px !important;
  height: 58px !important;
  vertical-align: top !important;
  padding: 7px 6px !important;
}
</style>
""", unsafe_allow_html=True)

# --- الاتصال بـ Google Sheets عبر Secrets ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # سيتم قراءة البيانات من سكرت استريم ليت للحماية
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
    except:
        # fallback to loading from JSON file if secrets not available
        import json
        with open("mca.json") as f:
            creds_dict = json.load(f)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def ensure_sheets_initialized(sheet):
    """Ensure all required worksheets exist with proper headers"""
    try:
        # Try to get Students sheet
        ws = sheet.worksheet("Students")
        current_headers = [str(h).strip() for h in ws.row_values(1)]
        headers_invalid = (
            len(current_headers) < len(STUDENTS_HEADERS)
            or any(h == "" for h in current_headers[:len(STUDENTS_HEADERS)])
            or len(set(current_headers[:len(STUDENTS_HEADERS)])) != len(current_headers[:len(STUDENTS_HEADERS)])
        )
        if headers_invalid:
            ws.update(f"A1:P1", [STUDENTS_HEADERS])
    except:
        # Create Students sheet if it doesn't exist
        ws = sheet.add_worksheet(title="Students", rows=1, cols=len(STUDENTS_HEADERS))
        ws.append_row(STUDENTS_HEADERS)
    
    try:
        # Try to get Attendance sheet
        ws = sheet.worksheet("Attendance")
        current_headers = [str(h).strip() for h in ws.row_values(1)]
        headers_invalid = (
            len(current_headers) < len(ATTENDANCE_HEADERS)
            or any(h == "" for h in current_headers[:len(ATTENDANCE_HEADERS)])
            or len(set(current_headers[:len(ATTENDANCE_HEADERS)])) != len(current_headers[:len(ATTENDANCE_HEADERS)])
        )
        if headers_invalid:
            ws.update("A1:I1", [ATTENDANCE_HEADERS])
    except:
        # Create Attendance sheet if it doesn't exist
        ws = sheet.add_worksheet(title="Attendance", rows=1, cols=len(ATTENDANCE_HEADERS))
        ws.append_row(ATTENDANCE_HEADERS)

    try:
        # Try to get Users sheet
        ws = sheet.worksheet("Users")
        current_headers = [str(h).strip() for h in ws.row_values(1)]
        headers_invalid = (
            len(current_headers) < len(USERS_HEADERS)
            or any(h == "" for h in current_headers[:len(USERS_HEADERS)])
            or len(set(current_headers[:len(USERS_HEADERS)])) != len(current_headers[:len(USERS_HEADERS)])
        )
        if headers_invalid:
            ws.update("A1:G1", [USERS_HEADERS])
    except:
        # Create Users sheet if it doesn't exist
        ws = sheet.add_worksheet(title="Users", rows=1, cols=7)
        ws.append_row(USERS_HEADERS)


def make_safe_sheet_title(prefix, username):
    """Google Sheets title rules: remove forbidden chars and cap length."""
    safe_username = re.sub(r"[\[\]\*\?/\\:]", "_", username.strip())
    title = f"{prefix}_{safe_username}"
    return title[:100]


def create_role_sheet_if_missing(role, username):
    if not db_connected or sh is None:
        return ""

    prefix = "Teacher" if role == "Teacher" else "Assistant"
    sheet_title = make_safe_sheet_title(prefix, username)

    try:
        sh.worksheet(sheet_title)
    except:
        ws = sh.add_worksheet(title=sheet_title, rows=1, cols=6)
        ws.append_row(["Timestamp", "Action", "Student_Name", "Details", "Created_By", "Status"])

    return sheet_title


@st.cache_data(ttl=45, show_spinner=False)
def get_sheet_records(sheet_name):
    """Cache worksheet reads briefly to reduce Google Sheets quota usage."""
    if not db_connected or sh is None:
        return []
    wks = sh.worksheet(sheet_name)
    return wks.get_all_records()


def get_managed_users_df():
    if not db_connected or sh is None:
        return pd.DataFrame()

    users_wks = sh.worksheet("Users")

    # Prefer safe explicit headers in case worksheet header row is malformed.
    try:
        records = get_sheet_records("Users")
        if not records:
            records = users_wks.get_all_records(expected_headers=USERS_HEADERS)
    except:
        records = []

    # If still empty, try normal read as fallback.
    if not records:
        try:
            records = users_wks.get_all_records()
        except:
            records = []

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Normalize column names to avoid issues from spaces/case variations.
    df.columns = [str(c).strip() for c in df.columns]

    # Ensure expected columns always exist.
    for col in USERS_HEADERS:
        if col not in df.columns:
            df[col] = ""

    # Normalize values used for matching/display.
    df["Username"] = df["Username"].astype(str).str.strip().str.lower()
    df["Password"] = df["Password"].astype(str).str.strip()
    df["Role"] = df["Role"].astype(str).str.strip().str.lower()
    df["Full_Name"] = df["Full_Name"].astype(str).str.strip()
    df["Phone"] = df["Phone"].astype(str).str.strip()
    df["Sheet_Name"] = df["Sheet_Name"].astype(str).str.strip()

    return df


def authenticate_staff_user(username, password):
    """Authenticate assistant/teacher accounts stored in Users sheet."""
    if not db_connected or sh is None:
        return None

    try:
        username = username.strip().lower()
        password = password.strip()

        df_users = get_managed_users_df()
        if df_users.empty:
            return None

        if "Username" not in df_users.columns or "Password" not in df_users.columns or "Role" not in df_users.columns:
            return None

        matched = df_users[
            (
                (df_users["Username"].astype(str).str.strip().str.lower() == username)
                | (df_users["Full_Name"].astype(str).str.strip().str.lower() == username)
            )
            & (df_users["Password"].astype(str).str.strip() == password)
        ]
        if matched.empty:
            return None

        role_raw = str(matched.iloc[0]["Role"]).strip().lower()
        role_map = {"assistant": "Assistant", "teacher": "Teacher"}
        role = role_map.get(role_raw, "")
        if role == "":
            return None

        canonical_username = str(matched.iloc[0].get("Username", "")).strip().lower()
        full_name = str(matched.iloc[0].get("Full_Name", "")).strip()
        return {
            "role": role,
            "username": canonical_username or username,
            "display_name": full_name or canonical_username or username
        }
    except:
        return None

# محاولة الاتصال وفتح الملف
SPREADSHEET_ID = "1d0XZZ3ph8bcB2zvz3zKvhcCV3a43w-rlbwsBCG-f0Do"
try:
    gc = init_connection()
    # تأكد أنك أنشأت ملف بهذا الاسم وشاركته مع الايميل البرمجي
    sh = gc.open_by_key(SPREADSHEET_ID)
    if "sheets_initialized" not in st.session_state:
        st.session_state.sheets_initialized = False

    if not st.session_state.sheets_initialized:
        ensure_sheets_initialized(sh)
        st.session_state.sheets_initialized = True

    st.sidebar.success("✅ متصل بقاعدة البيانات")
    db_connected = True
except Exception as e:
    if is_quota_error(e):
        st.sidebar.warning("⚠️ تم تجاوز حد القراءة المؤقت في Google Sheets. انتظر دقيقة ثم أعد المحاولة.")
    else:
        st.sidebar.error(f"❌ فشل الاتصال بقاعدة البيانات: {str(e)}")
    db_connected = False
    # Don't stop - allow app to continue without database
    sh = None

# --- تعريف منطق الـ Rounds ---
ROUNDS_CONFIG = {
    "Round 1": {"total": 4, "per_week": 1},
    "Round 2": {"total": 8, "per_week": 2},
    "Round 3 (SAT)": {"total": 5, "per_week": 1},
    "Round 4 (SAT)": {"total": 10, "per_week": 2},
}

# --- دالة إرسال واتساب ---
def send_wa(phone, msg):
    # تنظيف الرقم (تأكد يبدأ بـ 20 لمصر)
    if not phone.startswith('20'): phone = '20' + phone
    # Encode full text so Arabic and special characters render correctly.
    url = f"https://wa.me/{phone}?text={quote(str(msg), safe='')}"
    return url


def normalize_phone(phone):
    """Normalize phone to digits-only local format for reliable matching."""
    p = re.sub(r"\D", "", str(phone or "")).strip()
    if p.startswith("00"):
        p = p[2:]
    if p.startswith("20"):
        p = p[2:]
    if p.startswith("0"):
        p = p[1:]
    return p


def get_teacher_directory():
    """Return teacher accounts for assignment in student creation."""
    if not db_connected or sh is None:
        return []

    df_users = get_managed_users_df()
    if df_users.empty:
        return []

    teachers = df_users[df_users["Role"] == "teacher"].copy()
    if teachers.empty:
        return []

    directory = []
    for _, row in teachers.iterrows():
        username = str(row.get("Username", "")).strip().lower()
        full_name = str(row.get("Full_Name", "")).strip()
        if not username:
            continue
        label = f"{full_name} ({username})" if full_name and full_name.lower() != username else username
        directory.append({"label": label, "username": username, "full_name": full_name or username})

    return directory


def get_student_name_options(df_students):
    """Build clean student-name-only options for UI dropdowns."""
    if df_students.empty or "Name" not in df_students.columns:
        return []

    names = (
        df_students["Name"]
        .astype(str)
        .str.strip()
    )
    names = names[names != ""]
    return sorted(names.unique().tolist())


def get_students_df():
    if not db_connected or sh is None:
        return pd.DataFrame()

    df = pd.DataFrame(get_sheet_records("Students"))
    if df.empty:
        return df

    for col in STUDENTS_HEADERS:
        if col not in df.columns:
            df[col] = ""

    df["Name"] = df["Name"].astype(str).str.strip()
    df["Teacher"] = df["Teacher"].astype(str).str.strip().str.lower()
    df["Round"] = df["Round"].astype(str).str.strip()
    df["Start_date"] = df["Start_date"].astype(str).str.strip()

    # Keep sessions counters aligned with Round + Start_date even for old rows.
    totals = []
    completed = []
    remaining = []
    for _, row in df.iterrows():
        t, c, r = calculate_sessions(row.get("Round", ""), row.get("Start_date", ""))
        totals.append(t)
        completed.append(c)
        remaining.append(r)

    df["Total_Sessions"] = totals
    df["Completed_Sessions"] = completed
    df["Remaining_Sessions"] = remaining

    return df


def render_session_tracking(df_students, key_prefix, role_label):
    st.subheader("متابعة السيشن")

    student_list = get_student_name_options(df_students)
    if not student_list:
        st.info("لا توجد أسماء طلاب صالحة للمتابعة.")
        return

    selected_student = st.selectbox("اختر الطالب", student_list, key=f"{key_prefix}_student")

    col1, col2 = st.columns(2)
    with col1:
        status = st.radio("الحالة", ["حاضر", "غائب"], key=f"{key_prefix}_status")
        homework_status = st.selectbox("حالة الواجب", ["سلم", "لم يسلم"], key=f"{key_prefix}_hw_status")
    with col2:
        homework = st.text_area("الواجب", key=f"{key_prefix}_homework")
        exam_grade = st.number_input("درجة الامتحان (0-100)", min_value=0, max_value=100, step=1, key=f"{key_prefix}_exam_grade")

    notes = st.text_area("ملاحظات", key=f"{key_prefix}_notes")

    if st.button("حفظ بيانات السيشن", key=f"{key_prefix}_save"):
        try:
            att_wks = sh.worksheet("Attendance")
            att_wks.append_row([
                selected_student,
                str(datetime.now()),
                status,
                homework.strip(),
                homework_status,
                int(exam_grade),
                notes.strip(),
                st.session_state.get("username", ""),
                role_label
            ])

            # Update latest student status summary columns in Students sheet.
            students_wks = sh.worksheet("Students")
            all_values = students_wks.get_all_values()
            if all_values:
                headers = [str(h).strip() for h in all_values[0]]
                name_idx = headers.index("Name") if "Name" in headers else -1
                if name_idx >= 0:
                    for row_idx, row in enumerate(all_values[1:], start=2):
                        row_name = row[name_idx].strip() if name_idx < len(row) else ""
                        if row_name == selected_student:
                            col_map = {h: i + 1 for i, h in enumerate(headers)}
                            absent_idx = col_map.get("Absent_Count")
                            prev_absent = 0
                            if absent_idx and absent_idx - 1 < len(row):
                                prev_text = str(row[absent_idx - 1]).strip()
                                prev_absent = int(prev_text) if prev_text.isdigit() else 0

                            updates = {
                                "Last_Status": status,
                                "Last_Homework_Status": homework_status,
                                "Last_Exam_Grade": str(int(exam_grade)),
                                "Last_Session_Date": str(datetime.now().date()),
                                "Absent_Count": str(prev_absent + (1 if status == "غائب" else 0))
                            }

                            for col_name, val in updates.items():
                                col_idx = col_map.get(col_name)
                                if col_idx:
                                    students_wks.update_cell(row_idx, col_idx, val)
                            break

            st.cache_data.clear()
            st.success("تم حفظ بيانات السيشن بنجاح")
        except Exception as e:
            st.error(f"خطأ أثناء حفظ بيانات السيشن: {str(e)}")

# --- واجهات المستخدم ---

def render_add_student_form(form_key):
    with st.expander("➕ إضافة طالب جديد"):
        with st.form(form_key):
            name = st.text_input("اسم الطالب")
            phone = st.text_input("رقم تليفون الطالب")
            p_phone = st.text_input("رقم ولي الأمر")
            round_choice = st.selectbox("اختار الـ Round", list(ROUNDS_CONFIG.keys()))
            start_date = st.date_input("Start_date (تاريخ البداية)", value=datetime.now().date())

            teacher_directory = get_teacher_directory()
            if teacher_directory:
                teacher_labels = [t["label"] for t in teacher_directory]
                selected_teacher_label = st.selectbox("اسم المدرس", teacher_labels)
                selected_teacher = next((t for t in teacher_directory if t["label"] == selected_teacher_label), teacher_directory[0])
                teacher_username = selected_teacher["username"]
            else:
                st.warning("لا يوجد مدرسون مضافون بعد. أضف مدرسًا من لوحة الأدمن أولًا.")
                teacher_username = ""

            price_status = st.selectbox("حالة الدفع", ["مدفوع", "غير مدفوع"])

            if st.form_submit_button("تسجيل الطالب"):
                if not name.strip() or not phone.strip() or not p_phone.strip() or not teacher_username.strip():
                    st.error("يرجى إدخال جميع البيانات المطلوبة.")
                elif not db_connected or sh is None:
                    st.error("قاعدة البيانات غير متصلة. لا يمكن تسجيل الطالب.")
                else:
                    try:
                        total_sessions, completed_sessions, remaining_sessions = calculate_sessions(round_choice, start_date)
                        wks = sh.worksheet("Students")
                        wks.append_row([
                            name.strip(),
                            phone.strip(),
                            p_phone.strip(),
                            round_choice,
                            str(start_date),
                            total_sessions,
                            completed_sessions,
                            remaining_sessions,
                            teacher_username,
                            price_status,
                            str(datetime.now().date()),
                            "",
                            "",
                            "",
                            "",
                            0
                        ])
                        st.cache_data.clear()
                        st.success(f"تم تسجيل {name.strip()} بنجاح!")
                    except Exception as e:
                        st.error(f"خطأ في تسجيل الطالب: {str(e)}")


def render_delete_student_section(section_key):
    with st.expander("🗑️ حذف طالب"):
        if not db_connected or sh is None:
            st.error("قاعدة البيانات غير متصلة. لا يمكن حذف الطالب.")
            return

        df_students = get_students_df()
        if df_students.empty or "Name" not in df_students.columns:
            st.info("لا توجد بيانات طلاب متاحة للحذف.")
            return

        student_names = get_student_name_options(df_students)
        if not student_names:
            st.info("لا توجد أسماء طلاب صالحة متاحة للحذف.")
            return

        selected_name = st.selectbox("اختر الطالب للحذف", student_names, key=f"{section_key}_student")
        confirm_delete = st.checkbox("تأكيد الحذف", key=f"{section_key}_confirm")

        if st.button("حذف الطالب", key=f"{section_key}_delete"):
            if not confirm_delete:
                st.warning("يرجى تأكيد الحذف أولًا.")
                return

            try:
                wks = sh.worksheet("Students")
                values = wks.get_all_values()
                if not values:
                    st.warning("شيت الطلاب فارغ.")
                    return

                headers = [str(h).strip() for h in values[0]]
                if "Name" not in headers:
                    st.error("لم يتم العثور على عمود Name في شيت Students.")
                    return

                name_idx = headers.index("Name")
                deleted = False
                for row_idx, row in enumerate(values[1:], start=2):
                    cell_val = row[name_idx].strip() if name_idx < len(row) else ""
                    if cell_val == selected_name:
                        wks.delete_rows(row_idx)
                        deleted = True
                        break

                if deleted:
                    st.cache_data.clear()
                    st.success(f"تم حذف الطالب: {selected_name}")
                    st.rerun()
                else:
                    st.warning("لم يتم العثور على الطالب للحذف.")
            except Exception as e:
                st.error(f"خطأ أثناء حذف الطالب: {str(e)}")

def admin_page():
    st.title("👨‍💼 لوحة تحكم الأدمن")
    tab1, tab2, tab3 = st.tabs(["إدارة الطلاب", "إضافة مدرس/مساعد", "التقارير العامة"])
    with tab1:
        st.info("الأدمن يمكنه إضافة وحذف الطلاب")
        render_add_student_form("add_student_admin")
        render_delete_student_section("delete_student_admin")

        if db_connected and sh is not None:
            try:
                df_users = get_managed_users_df()
                if not df_users.empty:
                    staff_df = df_users[df_users["Role"].astype(str).str.lower().isin(["teacher", "assistant"])]
                    if not staff_df.empty:
                        staff_df = staff_df.copy()
                        staff_df["Role"] = staff_df["Role"].str.lower().map({"teacher": "Teacher", "assistant": "Assistant"}).fillna(staff_df["Role"])
                        st.subheader("الحسابات الحالية")
                        st.dataframe(staff_df[["Username", "Role", "Full_Name", "Phone", "Sheet_Name"]], use_container_width=True)
                    else:
                        st.info("لا توجد حسابات مدرسين/مساعدين حتى الآن.")
                else:
                    st.info("شيت Users فارغ حاليًا.")
            except Exception as e:
                st.error(f"خطأ في تحميل المستخدمين: {str(e)}")

    with tab2:
        st.info("إنشاء حسابات المدرسين والمساعدين مع إنشاء شيت خاص لكل حساب")

        with st.form("add_staff_user"):
            role_choice = st.selectbox("نوع الحساب", ["Teacher", "Assistant"])
            full_name = st.text_input("الاسم الكامل")
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            phone = st.text_input("رقم الهاتف")

            if st.form_submit_button("إنشاء الحساب"):
                if not db_connected or sh is None:
                    st.error("قاعدة البيانات غير متصلة. لا يمكن إنشاء الحساب.")
                elif not full_name.strip() or not username.strip() or not password.strip():
                    st.error("يرجى إدخال الاسم واسم المستخدم وكلمة المرور.")
                else:
                    try:
                        username_clean = username.strip().lower()
                        password_clean = password.strip()

                        users_wks = sh.worksheet("Users")
                        df_users = get_managed_users_df()

                        if not df_users.empty and "Username" in df_users.columns:
                            username_exists = (df_users["Username"] == username_clean).any()
                        else:
                            username_exists = False

                        if username_exists:
                            st.error("اسم المستخدم موجود بالفعل. اختر اسم مستخدم آخر.")
                        else:
                            sheet_name = create_role_sheet_if_missing(role_choice, username_clean)
                            users_wks.append_row([
                                username_clean,
                                password_clean,
                                role_choice,
                                full_name.strip(),
                                phone.strip(),
                                str(datetime.now()),
                                sheet_name
                            ])
                            st.cache_data.clear()
                            st.success(f"تم إنشاء حساب {role_choice} بنجاح وإنشاء الشيت: {sheet_name}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"خطأ في إنشاء الحساب: {str(e)}")

    with tab3:
        st.info("التقارير العامة (قيد التطوير)")

def assistant_page():
    st.title("👩‍💻 لوحة تحكم المساعد (Assistant)")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 قائمة الطلاب", "➕ إدارة الطلاب", "📅 متابعة السيشن", "📊 سجل الحضور", "🗓️ التقويم"])

    with tab1:
        st.subheader("قائمة جميع الطلاب")
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة.")
        else:
            df_all = get_students_df()
            if df_all.empty:
                st.info("لا يوجد طلاب مسجلون حالياً.")
            else:
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("إجمالي الطلاب", len(df_all))
                if "Payment_Status" in df_all.columns:
                    pay_col = df_all["Payment_Status"].astype(str).str.strip()
                    paid_count = int((pay_col == "مدفوع").sum())
                    unpaid_count = int((pay_col == "غير مدفوع").sum())
                else:
                    paid_count = "-"
                    unpaid_count = "-"
                col2.metric("طلاب مدفوعون", paid_count)
                col3.metric("طلاب غير مدفوعين", unpaid_count)

                ordered_cols = ["Name", "Phone", "Teacher", "Round", "Total_Sessions", "Completed_Sessions", "Remaining_Sessions", "Payment_Status", "Last_Session_Date"]
                display_cols = [c for c in ordered_cols if c in df_all.columns]
                df_display = df_all[display_cols].reset_index(drop=True)
                df_display.index = df_display.index + 1
                df_display.index.name = "#"
                st.dataframe(df_display, use_container_width=True)

    with tab2:
        st.info("المساعد يمكنه إضافة وحذف الطلاب")
        render_add_student_form("add_student_assistant")
        render_delete_student_section("delete_student_assistant")

    with tab3:
        df_students = get_students_df()
        if df_students.empty:
            st.info("لا توجد بيانات طلاب حالياً للمتابعة.")
        else:
            render_session_tracking(df_students, "assistant_session", "Assistant")

    with tab4:
        st.subheader("سجل الحضور والغياب")
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة.")
        else:
            try:
                df_att = pd.DataFrame(get_sheet_records("Attendance"))
                if df_att.empty:
                    st.info("لا يوجد سجل حضور حتى الآن.")
                else:
                    student_names_att = sorted(df_att["Student_Name"].astype(str).str.strip().unique().tolist()) if "Student_Name" in df_att.columns else []
                    filter_name = st.selectbox("تصفية بالطالب", ["الكل"] + student_names_att, key="asst_att_filter")
                    df_att_view = df_att.copy()
                    if filter_name != "الكل":
                        df_att_view = df_att_view[df_att_view["Student_Name"].astype(str).str.strip() == filter_name]
                    df_att_view = df_att_view.reset_index(drop=True)
                    df_att_view.index = df_att_view.index + 1
                    df_att_view.index.name = "#"
                    st.dataframe(df_att_view, use_container_width=True)
            except Exception as e:
                st.error(f"خطأ في تحميل سجل الحضور: {str(e)}")

    with tab5:
        st.subheader("🗓️ تقويم الحصص")
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة.")
        else:
            try:
                month_names = ["","يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
                cal_c1, cal_c2 = st.columns(2)
                with cal_c1:
                    sel_month = st.selectbox("الشهر", list(range(1, 13)), index=datetime.now().month - 1,
                                             format_func=lambda m: month_names[m], key="asst_cal_month")
                with cal_c2:
                    sel_year = st.number_input("السنة", min_value=2020, max_value=2030,
                                               value=datetime.now().year, key="asst_cal_year")
                df_att_cal = pd.DataFrame(get_sheet_records("Attendance"))
                df_stu_cal = get_students_df()
                if not df_att_cal.empty and "Session_Date" in df_att_cal.columns:
                    df_att_cal["Session_Date"] = pd.to_datetime(df_att_cal["Session_Date"], errors="coerce")
                    df_month = df_att_cal[
                        (df_att_cal["Session_Date"].dt.month == sel_month) &
                        (df_att_cal["Session_Date"].dt.year == sel_year)
                    ].copy()
                    if df_month.empty:
                        st.info("لا توجد حصص مسجلة في هذا الشهر.")
                    else:
                        df_month["التاريخ"] = df_month["Session_Date"].dt.strftime("%Y-%m-%d")
                        df_month["اليوم"] = df_month["Session_Date"].dt.strftime("%A")
                        show_cols = ["التاريخ", "اليوم"] + [c for c in ["Student_Name", "Status", "Exam_Grade", "Recorded_By"] if c in df_month.columns]
                        st.dataframe(df_month[show_cols].sort_values("التاريخ").reset_index(drop=True), use_container_width=True)
                        st.markdown("**ملخص الحضور يومياً:**")
                        summary = df_month.groupby("التاريخ")["Student_Name"].count().reset_index()
                        summary.columns = ["التاريخ", "عدد الحصص"]
                        st.dataframe(summary, use_container_width=True)
                else:
                    st.info("لا يوجد سجل حضور حتى الآن.")
                if not df_stu_cal.empty and "Start_date" in df_stu_cal.columns:
                    st.markdown("---")
                    st.markdown("**📌 طلاب بدأت حصصهم هذا الشهر:**")
                    df_stu_cal["Start_date_dt"] = pd.to_datetime(df_stu_cal["Start_date"], errors="coerce")
                    upcoming = df_stu_cal[
                        (df_stu_cal["Start_date_dt"].dt.month == sel_month) &
                        (df_stu_cal["Start_date_dt"].dt.year == sel_year)
                    ]
                    if not upcoming.empty:
                        up_cols = [c for c in ["Name", "Teacher", "Round", "Start_date", "Remaining_Sessions"] if c in upcoming.columns]
                        st.dataframe(upcoming[up_cols].reset_index(drop=True), use_container_width=True)
                    else:
                        st.info("لا يوجد طلاب بدأت حصصهم في هذا الشهر.")
            except Exception as e:
                st.error(f"خطأ في تحميل التقويم: {str(e)}")
def teacher_page():
    st.title("👨‍🏫 لوحة تحكم المدرس")
    st.info("يمكنك متابعة وتقييم الطلاب المضافين لك فقط")

    try:
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة. لا يمكن استرجاع بيانات الطلاب.")
            return

        df = get_students_df()
        
        if df.empty:
            st.info("لا توجد طلاب مسجلين حالياً.")
            return

        if "Teacher" not in df.columns:
            st.warning("شيت الطلاب لا يحتوي على عمود Teacher بشكل صحيح.")
            return

        current_username = str(st.session_state.get("username", "")).strip().lower()
        current_display = str(st.session_state.get("display_name", "")).strip().lower()
        df["Teacher_norm"] = df["Teacher"].astype(str).str.strip().str.lower()

        teacher_students = df[
            (df["Teacher_norm"] == current_username)
            | (df["Teacher_norm"] == current_display)
        ].copy()

        if teacher_students.empty:
            st.info("لا يوجد طلاب مضافون لك حالياً.")
            return

        render_session_tracking(teacher_students, "teacher_session", "Teacher")
    except Exception as e:
        st.error(f"خطأ في تحميل بيانات الطلاب: {str(e)}")

def parent_student_page(user_phone):
    st.title("\U0001f4dd \u0645\u062a\u0627\u0628\u0639\u0629 \u0627\u0644\u0645\u0633\u062a\u0648\u0649")
    try:
        if not db_connected or sh is None:
            st.warning("\u0642\u0627\u0639\u062f\u0629 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u063a\u064a\u0631 \u0645\u062a\u0635\u0644\u0629. \u0644\u0627 \u064a\u0645\u0643\u0646 \u0639\u0631\u0636 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a.")
            return

        df_students = pd.DataFrame(get_sheet_records("Students"))
        if df_students.empty:
            st.warning("\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0637\u0644\u0627\u0628 \u062d\u0627\u0644\u064a\u0627\u064b.")
            return

        if "Phone" not in df_students.columns or "Parent_Phone" not in df_students.columns:
            st.error("\u0634\u064a\u062a \u0627\u0644\u0637\u0644\u0627\u0628 \u0644\u0627 \u064a\u062d\u062a\u0648\u064a \u0639\u0644\u0649 \u0623\u0639\u0645\u062f\u0629 Phone \u0648 Parent_Phone \u0628\u0627\u0644\u0634\u0643\u0644 \u0627\u0644\u0635\u062d\u064a\u062d.")
            return

        df_students["Phone"] = df_students["Phone"].astype(str)
        df_students["Parent_Phone"] = df_students["Parent_Phone"].astype(str)

        input_phone = normalize_phone(user_phone)
        df_students["Phone_norm"] = df_students["Phone"].apply(normalize_phone)
        df_students["Parent_Phone_norm"] = df_students["Parent_Phone"].apply(normalize_phone)

        student_info = df_students[
            (df_students["Phone_norm"] == input_phone)
            | (df_students["Parent_Phone_norm"] == input_phone)
        ]

        if not student_info.empty:
            import calendar as _cal

            student_row = student_info.iloc[0]
            s_name = str(student_row.get("Name", "")).strip()

            df_att = pd.DataFrame(get_sheet_records("Attendance"))
            if not df_att.empty and "Student_Name" in df_att.columns:
                personal_att = df_att[
                    df_att["Student_Name"].astype(str).str.strip().str.lower() == s_name.lower()
                ].copy()
            else:
                personal_att = pd.DataFrame()

            if not personal_att.empty and "Session_Date" in personal_att.columns:
                personal_att["Session_Date"] = pd.to_datetime(personal_att["Session_Date"], errors="coerce")
                personal_att = personal_att.dropna(subset=["Session_Date"])

            st.markdown(f"## \U0001f393 {s_name}")
            st.divider()

            # ── 1. CALENDAR (shown first) ────────────────────────────────
            st.markdown("### \U0001f5d3\ufe0f \u0627\u0644\u062a\u0642\u0648\u064a\u0645 \u0627\u0644\u0634\u0647\u0631\u064a")
            month_names_list = ["","\u064a\u0646\u0627\u064a\u0631","\u0641\u0628\u0631\u0627\u064a\u0631","\u0645\u0627\u0631\u0633","\u0623\u0628\u0631\u064a\u0644","\u0645\u0627\u064a\u0648","\u064a\u0648\u0646\u064a\u0648","\u064a\u0648\u0644\u064a\u0648","\u0623\u063a\u0633\u0637\u0633","\u0633\u0628\u062a\u0645\u0628\u0631","\u0623\u0643\u062a\u0648\u0628\u0631","\u0646\u0648\u0641\u0645\u0628\u0631","\u062f\u064a\u0633\u0645\u0628\u0631"]
            cc1, cc2 = st.columns([2, 1])
            with cc1:
                sel_month = st.selectbox(
                    "\u0627\u0644\u0634\u0647\u0631", list(range(1, 13)),
                    index=datetime.now().month - 1,
                    format_func=lambda m: month_names_list[m],
                    key="parent_cal_month"
                )
            with cc2:
                sel_year = st.number_input("\u0627\u0644\u0633\u0646\u0629", min_value=2020, max_value=2035,
                                           value=datetime.now().year, key="parent_cal_year")

            if not personal_att.empty:
                month_df = personal_att[
                    (personal_att["Session_Date"].dt.month == sel_month) &
                    (personal_att["Session_Date"].dt.year == sel_year)
                ].copy()
                sessions_by_day = (month_df.groupby(month_df["Session_Date"].dt.day)["Session_Date"]
                                   .count().to_dict() if not month_df.empty else {})
                status_by_day = {}
                if not month_df.empty and "Status" in month_df.columns:
                    for d_num, grp in month_df.groupby(month_df["Session_Date"].dt.day):
                        status_by_day[int(d_num)] = str(grp.sort_values("Session_Date").iloc[-1].get("Status", "")).strip()
            else:
                month_df = pd.DataFrame()
                sessions_by_day = {}
                status_by_day = {}

            day_ar = ["\u0627\u0644\u0633\u0628\u062a","\u0627\u0644\u0623\u062d\u062f","\u0627\u0644\u0627\u062b\u0646\u064a\u0646","\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621","\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621","\u0627\u0644\u062e\u0645\u064a\u0633","\u0627\u0644\u062c\u0645\u0639\u0629"]
            header_cells = "".join(
                '<th style="background:#1e3a5f;color:#fff;text-align:center;padding:10px 4px;font-size:13px;border:2px solid #2c5282;">' + d + '</th>'
                for d in day_ar
            )
            month_grid = _cal.Calendar(firstweekday=5).monthdayscalendar(int(sel_year), int(sel_month))
            today = datetime.now().date()
            rows_html = ""
            for week in month_grid:
                cells = ""
                for day_num in week:
                    if day_num == 0:
                        cells += '<td style="background:#f0f0f0;border:1px solid #ccc;min-width:42px;height:60px;"></td>'
                        continue
                    day_status = status_by_day.get(day_num, "")
                    day_count = int(sessions_by_day.get(day_num, 0))
                    is_today = (day_num == today.day and sel_month == today.month and sel_year == today.year)
                    if day_status == "\u062d\u0627\u0636\u0631":
                        bg, fc, bdr = "#d4edda", "#155724", "2px solid #28a745"
                        icon = "\u2705"
                    elif day_status == "\u063a\u0627\u0626\u0628":
                        bg, fc, bdr = "#f8d7da", "#721c24", "2px solid #dc3545"
                        icon = "\u274c"
                    elif is_today:
                        bg, fc, bdr = "#cce5ff", "#004085", "3px solid #0056b3"
                        icon = ""
                    else:
                        bg, fc, bdr = "#ffffff", "#333333", "1px solid #dee2e6"
                        icon = ""
                    session_line = (
                        '<br><span style="font-size:11px;">' + icon + ' ' + str(day_count) + ' \u062d\u0635\u0629</span>'
                        if day_count > 0
                        else ('<br><span style="font-size:11px;">' + icon + '</span>' if icon else "")
                    )
                    cells += (
                        '<td style="background:' + bg + ';border:' + bdr + ';text-align:center;'
                        'padding:8px 4px;vertical-align:top;min-width:42px;height:60px;color:' + fc + ';">'
                        '<strong style="font-size:15px;">' + str(day_num) + '</strong>' + session_line + '</td>'
                    )
                rows_html += "<tr>" + cells + "</tr>"

            calendar_html = (
                '<style>.mca-cal{border-collapse:collapse;width:100%;font-family:Arial,sans-serif;direction:rtl;}</style>'
                '<table class="mca-cal"><thead><tr>' + header_cells + '</tr></thead>'
                '<tbody>' + rows_html + '</tbody></table>'
                '<p style="font-size:12px;margin-top:8px;color:#555;">'
                '\u2705 \u062d\u0627\u0636\u0631 &nbsp; \u274c \u063a\u0627\u0626\u0628 &nbsp;'
                '<span style="background:#cce5ff;padding:2px 6px;border-radius:3px;border:1px solid #004085;">\u0627\u0644\u064a\u0648\u0645</span></p>'
            )
            st.markdown(calendar_html, unsafe_allow_html=True)

            if not month_df.empty:
                with st.expander("\u062a\u0641\u0627\u0635\u064a\u0644 \u062d\u0635\u0635 \u0627\u0644\u0634\u0647\u0631"):
                    det = month_df.copy()
                    det["\u0627\u0644\u062a\u0627\u0631\u064a\u062e"] = det["Session_Date"].dt.strftime("%Y-%m-%d")
                    det_cols = [c for c in ["\u0627\u0644\u062a\u0627\u0631\u064a\u062e","Status","Homework_Status","Exam_Grade"] if c in det.columns]
                    det = det[det_cols].rename(columns={"Status":"\u0627\u0644\u062d\u0627\u0644\u0629","Homework_Status":"\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0627\u062c\u0628","Exam_Grade":"\u062f\u0631\u062c\u0629 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631"})
                    st.dataframe(det.sort_values("\u0627\u0644\u062a\u0627\u0631\u064a\u062e").reset_index(drop=True), use_container_width=True)
            else:
                st.info("\u0644\u0627 \u062a\u0648\u062c\u062f \u062d\u0635\u0635 \u0645\u0633\u062c\u0644\u0629 \u0641\u064a \u0647\u0630\u0627 \u0627\u0644\u0634\u0647\u0631.")

            st.divider()

            # ── 2. KPI Cards ─────────────────────────────────────────────
            total_sessions     = student_row.get("Total_Sessions", "-")     if "Total_Sessions"     in student_row else "-"
            completed_sessions = student_row.get("Completed_Sessions", "-") if "Completed_Sessions" in student_row else "-"
            remaining_sessions = student_row.get("Remaining_Sessions", "-") if "Remaining_Sessions" in student_row else "-"
            teacher_name       = student_row.get("Teacher", "-")            if "Teacher"            in student_row else "-"
            payment_status     = student_row.get("Payment_Status", "-")     if "Payment_Status"     in student_row else "-"
            round_name         = student_row.get("Round", "-")              if "Round"              in student_row else "-"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u062d\u0635\u0635", total_sessions)
            c2.metric("\u0627\u0644\u062d\u0635\u0635 \u0627\u0644\u0645\u0646\u0641\u0630\u0629", completed_sessions)
            c3.metric("\u0627\u0644\u062d\u0635\u0635 \u0627\u0644\u0645\u062a\u0628\u0642\u064a\u0629", remaining_sessions)
            c4.metric("\u062d\u0627\u0644\u0629 \u0627\u0644\u062f\u0641\u0639", payment_status)
            c5, c6 = st.columns(2)
            c5.info(f"\U0001f468\u200d\U0001f3eb \u0627\u0644\u0645\u062f\u0631\u0633: **{teacher_name}**")
            c6.info(f"\U0001f3af \u0627\u0644\u0631\u0627\u0648\u0646\u062f: **{round_name}**")

            st.divider()

            # ── 3. Summary + History Tabs ─────────────────────────────────
            tab1, tab2 = st.tabs(["\U0001f4cc \u0627\u0644\u0645\u0644\u062e\u0635", "\U0001f4da \u0633\u062c\u0644 \u0627\u0644\u062d\u0635\u0635"])

            with tab1:
                if personal_att.empty:
                    st.info("\u0644\u0627 \u062a\u0648\u062c\u062f \u0633\u062c\u0644\u0627\u062a \u062d\u0636\u0648\u0631 \u0644\u0647\u0630\u0627 \u0627\u0644\u0637\u0627\u0644\u0628 \u062d\u0627\u0644\u064a\u0627\u064b.")
                else:
                    if "Status" in personal_att.columns:
                        present_count = int((personal_att["Status"].astype(str).str.strip() == "\u062d\u0627\u0636\u0631").sum())
                        absent_count  = int((personal_att["Status"].astype(str).str.strip() == "\u063a\u0627\u0626\u0628").sum())
                    else:
                        present_count = absent_count = 0
                    m1, m2, m3 = st.columns(3)
                    m1.metric("\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u062d\u0635\u0635 \u0627\u0644\u0645\u0633\u062c\u0644\u0629", len(personal_att))
                    m2.metric("\u0645\u0631\u0627\u062a \u0627\u0644\u062d\u0636\u0648\u0631 \u2705", present_count)
                    m3.metric("\u0645\u0631\u0627\u062a \u0627\u0644\u063a\u064a\u0627\u0628 \u274c", absent_count)
                    if "Session_Date" in personal_att.columns:
                        latest = personal_att.sort_values("Session_Date", ascending=False).iloc[0]
                        st.markdown("**\u0622\u062e\u0631 \u0645\u062a\u0627\u0628\u0639\u0629:**")
                        l1, l2, l3, l4 = st.columns(4)
                        l1.write(f"\u0627\u0644\u062a\u0627\u0631\u064a\u062e: {str(latest.get('Session_Date', '-'))[:10]}")
                        l2.write(f"\u0627\u0644\u062d\u0627\u0644\u0629: {latest.get('Status', '-')}")
                        l3.write(f"\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0627\u062c\u0628: {latest.get('Homework_Status', '-')}")
                        l4.write(f"\u062f\u0631\u062c\u0629 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631: {latest.get('Exam_Grade', '-')}")

            with tab2:
                if personal_att.empty:
                    st.info("\u0644\u0627 \u062a\u0648\u062c\u062f \u062d\u0635\u0635 \u0644\u0639\u0631\u0636\u0647\u0627.")
                else:
                    pa = personal_att.sort_values("Session_Date", ascending=False).copy()
                    tcols = [c for c in ["Session_Date","Status","Homework","Homework_Status","Exam_Grade","Notes","Recorded_By"] if c in pa.columns]
                    vdf = pa[tcols].copy()
                    vdf.rename(columns={
                        "Session_Date":"\u0627\u0644\u062a\u0627\u0631\u064a\u062e","Status":"\u0627\u0644\u062d\u0627\u0644\u0629",
                        "Homework":"\u0627\u0644\u0648\u0627\u062c\u0628","Homework_Status":"\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0627\u062c\u0628",
                        "Exam_Grade":"\u062f\u0631\u062c\u0629 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631","Notes":"\u0645\u0644\u0627\u062d\u0638\u0627\u062a",
                        "Recorded_By":"\u062a\u0645 \u0627\u0644\u062a\u0633\u062c\u064a\u0644 \u0628\u0648\u0627\u0633\u0637\u0629"
                    }, inplace=True)
                    if "\u0627\u0644\u062a\u0627\u0631\u064a\u062e" in vdf.columns:
                        vdf["\u0627\u0644\u062a\u0627\u0631\u064a\u062e"] = pd.to_datetime(vdf["\u0627\u0644\u062a\u0627\u0631\u064a\u062e"], errors="coerce").dt.strftime("%Y-%m-%d")
                    vdf = vdf.reset_index(drop=True)
                    vdf.index = vdf.index + 1
                    vdf.index.name = "#"
                    st.dataframe(vdf, use_container_width=True)
        else:
            st.warning("\u0639\u0630\u0631\u0627\u064b\u060c \u0644\u0645 \u0646\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0645\u0631\u062a\u0628\u0637\u0629 \u0628\u0647\u0630\u0627 \u0627\u0644\u0631\u0642\u0645.")
    except Exception as e:
        st.error(f"\u062e\u0637\u0623 \u0641\u064a \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a: {str(e)}")

def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        # ── Login page ─────────────────────────────────────────────────────
        st.markdown("""
<style>
/* Center the login card */
.login-wrap {
  display: flex; justify-content: center; align-items: flex-start;
  padding-top: 3rem;
}
.login-card {
  background: #fff;
  border: 1px solid #E3EBF6;
  border-radius: 10px;
  box-shadow: 0 4px 24px rgba(18,38,63,0.09);
  padding: 2.5rem 2.25rem;
  width: 100%;
  max-width: 420px;
  margin: 0 auto;
}
.login-logo {
  font-size: 2rem;
  font-weight: 800;
  color: #2C7BE5;
  text-align: center;
  margin-bottom: 0.25rem;
  letter-spacing: -1px;
}
.login-subtitle {
  text-align: center;
  color: #95AAC9;
  font-size: 0.875rem;
  margin-bottom: 1.75rem;
}
</style>
<div class="login-card">
  <div class="login-logo">🎓 MCA Academy</div>
  <div class="login-subtitle">مرحباً بك — سجّل دخولك للمتابعة</div>
</div>
""", unsafe_allow_html=True)

        col_left, col_center, col_right = st.columns([1, 2, 1])
        with col_center:
            user = st.text_input("اسم المستخدم / رقم التليفون", placeholder="أدخل اسم المستخدم...")
            pwd = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور...")
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if st.columns([1, 2, 1])[1].button("تسجيل الدخول", use_container_width=True):
            user = user.strip()
            pwd = pwd.strip()

            if user == "admin" and pwd == "mca2026": # بيانات الأدمن
                st.session_state.role = "Admin"
                st.session_state.username = user
                st.session_state.authenticated = True
                st.rerun()
            elif user == "assistant" and pwd == "mca_asst": # بيانات المساعد
                st.session_state.role = "Assistant"
                st.session_state.username = user
                st.session_state.display_name = user
                st.session_state.authenticated = True
                st.rerun()
            elif user == "teacher" and pwd == "mca_teacher": # بيانات المدرس
                st.session_state.role = "Teacher"
                st.session_state.username = user
                st.session_state.display_name = user
                st.session_state.authenticated = True
                st.rerun()
            else:
                staff_auth = authenticate_staff_user(user, pwd)
                if staff_auth is not None:
                    st.session_state.role = staff_auth["role"]
                    st.session_state.username = staff_auth["username"]
                    st.session_state.display_name = staff_auth["display_name"]
                    st.session_state.authenticated = True
                    st.rerun()

                # محاولة دخول كولي أمر (الرقم هو اليوزر والباسورد)
                elif user == pwd and len(user) >= 10:
                    st.session_state.role = "Parent"
                    st.session_state.username = user
                    st.session_state.display_name = user
                    st.session_state.user_phone = user
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("خطأ في البيانات")
    else:
        role = st.session_state.role
        display_name = st.session_state.get("display_name", st.session_state.get("username", ""))
        role_icons = {"Admin": "👨‍💼", "Assistant": "👩‍💻", "Teacher": "👨‍🏫", "Parent": "👨‍👧"}
        role_labels = {"Admin": "مدير النظام", "Assistant": "مساعد", "Teacher": "مدرس", "Parent": "ولي أمر"}

        st.sidebar.markdown(f"""
<div style="background:#F5F6FA;border-radius:8px;padding:14px 16px;margin-bottom:12px;border:1px solid #E3EBF6;">
  <div style="font-size:1.35rem;font-weight:700;color:#12263F;">{role_icons.get(role,'🎓')} MCA Academy</div>
  <div style="font-size:0.8rem;color:#95AAC9;margin-top:4px;">{display_name} · {role_labels.get(role, role)}</div>
</div>
""", unsafe_allow_html=True)

        if st.sidebar.button("تسجيل الخروج"):
            st.session_state.authenticated = False
            st.rerun()
            
        if role == "Admin": admin_page()
        elif role == "Assistant": assistant_page()
        elif role == "Teacher": teacher_page()
        elif role == "Parent": parent_student_page(st.session_state.user_phone)

if __name__ == "__main__":
    main()