import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

# --- إعدادات الصفحة ---
st.set_page_config(page_title="MCA Academy System", layout="wide", initial_sidebar_state="expanded")

# --- الاتصال بـ Google Sheets عبر Secrets ---
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

# محاولة الاتصال وفتح الملف
SPREADSHEET_ID = "1d0XZZ3ph8bcB2zvz3zKvhcCV3a43w-rlbwsBCG-f0Do"
try:
    gc = init_connection()
    # تأكد أنك أنشأت ملف بهذا الاسم وشاركته مع الايميل البرمجي
    sh = gc.open_by_key(SPREADSHEET_ID)
    ensure_sheets_initialized(sh)
    st.sidebar.success("✅ متصل بقاعدة البيانات")
    db_connected = True
except Exception as e:
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

# --- واجهات المستخدم ---

def admin_page():
    st.title("👨‍💼 لوحة تحكم الأدمن")
    tab1, tab2 = st.tabs(["إدارة المستخدمين", "التقارير العامة"])
    with tab1:
        st.info("هنا يمكنك إضافة مدرسين جدد أو مساعدين (قيد التطوير)")

def assistant_page():
    st.title("👩‍💻 لوحة تحكم المساعد (Assistant)")
    
    with st.expander("➕ إضافة طالب جديد"):
        with st.form("add_student"):
            name = st.text_input("اسم الطالب")
            phone = st.text_input("رقم تليفون الطالب")
            p_phone = st.text_input("رقم ولي الأمر")
            round_choice = st.selectbox("اختار الـ Round", list(ROUNDS_CONFIG.keys()))
            teacher = st.text_input("اسم المدرس")
            price_status = st.selectbox("حالة الدفع", ["مدفوع", "غير مدفوع"])
            
            if st.form_submit_button("تسجيل الطالب"):
                if not db_connected or sh is None:
                    st.error("قاعدة البيانات غير متصلة. لا يمكن تسجيل الطالب.")
                else:
                    try:
                        wks = sh.worksheet("Students")
                        wks.append_row([name, phone, p_phone, round_choice, ROUNDS_CONFIG[round_choice]['total'], teacher, price_status, str(datetime.now().date())])
                        st.success(f"تم تسجيل {name} بنجاح!")
                    except Exception as e:
                        st.error(f"خطأ في تسجيل الطالب: {str(e)}")

def teacher_page():
    st.title("👨‍🏫 لوحة تحكم المدرس")
    try:
        if not db_connected or sh is None:
            st.warning("قاعدة البيانات غير متصلة. لا يمكن استرجاع بيانات الطلاب.")
            return
        
        wks = sh.worksheet("Students")
        df = pd.DataFrame(wks.get_all_records())
        
        if df.empty:
            st.info("لا توجد طلاب مسجلين حالياً. يرجى إضافة طلاب من خلال قائمة المساعد.")
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
        df_students = pd.DataFrame(sh.worksheet("Students").get_all_records())
        # تحويل العمود لنصوص للبحث
        df_students['Phone'] = df_students['Phone'].astype(str)
        df_students['Parent_Phone'] = df_students['Parent_Phone'].astype(str)
        
        student_info = df_students[(df_students['Phone'] == user_phone) | (df_students['Parent_Phone'] == user_phone)]
        
        if not student_info.empty:
            s_name = student_info.iloc[0]['Name']
            st.header(f"الطالب: {s_name}")
            st.metric("الحصص المتبقية في الراوند", student_info.iloc[0]['Sessions'])
            
            # عرض درجاته من شيت Attendance
            df_att = pd.DataFrame(sh.worksheet("Attendance").get_all_records())
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
            if user == "admin" and pwd == "mca2026": # بيانات الأدمن
                st.session_state.role = "Admin"
                st.session_state.authenticated = True
                st.rerun()
            elif user == "assistant" and pwd == "mca_asst": # بيانات المساعد
                st.session_state.role = "Assistant"
                st.session_state.authenticated = True
                st.rerun()
            elif user == "teacher" and pwd == "mca_teacher": # بيانات المدرس
                st.session_state.role = "Teacher"
                st.session_state.authenticated = True
                st.rerun()
            else:
                # محاولة دخول كولي أمر (الرقم هو اليوزر والباسورد)
                if user == pwd and len(user) >= 10:
                    st.session_state.role = "Parent"
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