import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import re

USERS_HEADERS = ["Username", "Password", "Role", "Full_Name", "Phone", "Created_At", "Sheet_Name"]


def is_quota_error(err):
    msg = str(err)
    return "429" in msg or "Quota exceeded" in msg

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
        sheet.worksheet("Students")
    except:
        # Create Students sheet if it doesn't exist
        ws = sheet.add_worksheet(title="Students", rows=1, cols=8)
        ws.append_row(["Name", "Phone", "Parent_Phone", "Round", "Sessions", "Teacher", "Payment_Status", "Date_Registered"])
    
    try:
        # Try to get Attendance sheet
        sheet.worksheet("Attendance")
    except:
        # Create Attendance sheet if it doesn't exist
        ws = sheet.add_worksheet(title="Attendance", rows=1, cols=5)
        ws.append_row(["Student_Name", "Date", "Status", "Grade", "Homework"])

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
    url = f"https://wa.me/{phone}?text={msg.replace(' ', '%20')}"
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

# --- واجهات المستخدم ---

def render_add_student_form(form_key, default_teacher=""):
    with st.expander("➕ إضافة طالب جديد"):
        with st.form(form_key):
            name = st.text_input("اسم الطالب")
            phone = st.text_input("رقم تليفون الطالب")
            p_phone = st.text_input("رقم ولي الأمر")
            round_choice = st.selectbox("اختار الـ Round", list(ROUNDS_CONFIG.keys()))
            teacher = st.text_input("اسم المدرس", value=default_teacher)
            price_status = st.selectbox("حالة الدفع", ["مدفوع", "غير مدفوع"])

            if st.form_submit_button("تسجيل الطالب"):
                if not name.strip() or not phone.strip() or not p_phone.strip() or not teacher.strip():
                    st.error("يرجى إدخال جميع البيانات المطلوبة.")
                elif not db_connected or sh is None:
                    st.error("قاعدة البيانات غير متصلة. لا يمكن تسجيل الطالب.")
                else:
                    try:
                        wks = sh.worksheet("Students")
                        wks.append_row([
                            name.strip(),
                            phone.strip(),
                            p_phone.strip(),
                            round_choice,
                            ROUNDS_CONFIG[round_choice]['total'],
                            teacher.strip(),
                            price_status,
                            str(datetime.now().date())
                        ])
                        st.cache_data.clear()
                        st.success(f"تم تسجيل {name.strip()} بنجاح!")
                    except Exception as e:
                        st.error(f"خطأ في تسجيل الطالب: {str(e)}")

def admin_page():
    st.title("👨‍💼 لوحة تحكم الأدمن")
    tab1, tab2, tab3 = st.tabs(["إدارة المستخدمين", "إضافة مدرس/مساعد", "التقارير العامة"])
    with tab1:
        st.info("يمكنك الآن إضافة طلاب جدد من لوحة الأدمن")
        render_add_student_form("add_student_admin")

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
    render_add_student_form("add_student_assistant")

def teacher_page():
    st.title("👨‍🏫 لوحة تحكم المدرس")
    teacher_name = st.session_state.get("display_name", st.session_state.get("username", "teacher"))
    render_add_student_form("add_student_teacher", default_teacher=teacher_name)

    try:
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة. لا يمكن استرجاع بيانات الطلاب.")
            return
        
        df = pd.DataFrame(get_sheet_records("Students"))
        
        if df.empty:
            st.info("لا توجد طلاب مسجلين حالياً. يمكنك إضافة طالب جديد من الأعلى.")
            return
        
        student_list = df['Name'].tolist()
        selected_student = st.selectbox("اختر الطالب لتسجيل الغياب والدرجات", student_list)
        
        col1, col2 = st.columns(2)
        with col1:
            status = st.radio("الحالة", ["حاضر", "غائب"])
            grade = st.number_input("الدرجة (من 100)", 0, 100)
        with col2:
            homework = st.text_area("الواجب المطلوب")
            hw_status = st.selectbox("هل سلم الواجب السابق؟", ["نعم", "لا"])
            
        if st.button("حفظ وإرسال لولي الأمر"):
            # تسجيل في شيت Attendance
            att_wks = sh.worksheet("Attendance")
            att_wks.append_row([selected_student, str(datetime.now()), status, grade, homework])
            st.cache_data.clear()
            
            # تجهيز رابط واتساب
            student_row = df[df['Name'] == selected_student].iloc[0]
            msg = f"تقرير حصة اليوم للطالب: {selected_student}\nالحالة: {status}\nالدرجة: {grade}\nالواجب: {homework}"
            
            st.success("تم الحفظ!")
            st.markdown(f"[📲 اضغط هنا لإرسال التقرير لولي الأمر عبر واتساب]({send_wa(str(student_row['Parent_Phone']), msg)})")
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
            st.metric("الحصص المتبقية في الراوند", student_info.iloc[0]['Sessions'])
            
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