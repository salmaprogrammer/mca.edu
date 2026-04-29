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
    st.info("المساعد يمكنه إضافة وحذف الطلاب")
    render_add_student_form("add_student_assistant")
    render_delete_student_section("delete_student_assistant")

    df_students = get_students_df()
    if df_students.empty:
        st.info("لا توجد بيانات طلاب حالياً للمتابعة.")
        return
    render_session_tracking(df_students, "assistant_session", "Assistant")

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
    st.title("📝 متابعة المستوى")
    try:
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة. لا يمكن عرض البيانات.")
            return
        
        # البحث في شيت الطلاب برقم التليفون
        df_students = pd.DataFrame(get_sheet_records("Students"))
        if df_students.empty:
            st.warning("لا توجد بيانات طلاب حالياً.")
            return

        if "Phone" not in df_students.columns or "Parent_Phone" not in df_students.columns:
            st.error("شيت الطلاب لا يحتوي على أعمدة Phone و Parent_Phone بالشكل الصحيح.")
            return

        # تحويل العمود لنصوص للبحث
        df_students['Phone'] = df_students['Phone'].astype(str)
        df_students['Parent_Phone'] = df_students['Parent_Phone'].astype(str)

        input_phone = normalize_phone(user_phone)
        df_students['Phone_norm'] = df_students['Phone'].apply(normalize_phone)
        df_students['Parent_Phone_norm'] = df_students['Parent_Phone'].apply(normalize_phone)

        student_info = df_students[
            (df_students['Phone_norm'] == input_phone)
            | (df_students['Parent_Phone_norm'] == input_phone)
        ]
        
        if not student_info.empty:
            s_name = student_info.iloc[0]['Name']
            st.header(f"الطالب: {s_name}")
            if "Remaining_Sessions" in student_info.columns:
                st.metric("الحصص المتبقية في الراوند", student_info.iloc[0]['Remaining_Sessions'])
            else:
                st.metric("الحصص المتبقية في الراوند", "-")
            
            # عرض درجاته من شيت Attendance
            df_att = pd.DataFrame(get_sheet_records("Attendance"))
            personal_att = df_att[df_att['Student_Name'] == s_name]
            if not personal_att.empty:
                st.table(personal_att)
            else:
                st.info("لا توجد سجلات حضور لهذا الطالب حالياً.")
        else:
            st.warning("عذراً، لم نجد بيانات مرتبطة بهذا الرقم.")
    except Exception as e:
        st.error(f"خطأ في تحميل البيانات: {str(e)}")

# --- التحكم في الدخول (Login) ---
def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🚪 تسجيل الدخول - MCA Academy")
        user = st.text_input("اسم المستخدم / رقم التليفون")
        pwd = st.text_input("كلمة المرور", type="password")
        
        if st.button("دخول"):
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
        if st.sidebar.button("تسجيل الخروج"):
            st.session_state.authenticated = False
            st.rerun()
            
        if role == "Admin": admin_page()
        elif role == "Assistant": assistant_page()
        elif role == "Teacher": teacher_page()
        elif role == "Parent": parent_student_page(st.session_state.user_phone)

if __name__ == "__main__":
    main()