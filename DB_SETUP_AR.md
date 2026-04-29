# إعداد قاعدة البيانات - الهيكل الأساسي

هذا الملف يشرح هيكل قاعدة البيانات المقترح لنظام الإدارة (Admin/Assistant/Teacher/Student/Parent) مع التركيز على:

- ربط المدرس بطلابه.
- عداد الحصص (إجمالي/مستهلك/متبقي).
- تتبع الحضور والواجب والاختبارات.
- التقويم التفاعلي.
- الفاتورة الرقمية بدون مبلغ.

## 1) الجداول الأساسية

1. users
- كل الحسابات في جدول واحد مع عمود role.
- الأدوار: admin, assistant, teacher, student, parent.

2. student_profiles
- ملف الطالب الدراسي.
- يحتوي على teacher_user_id لربط الطالب بمدرسه.
- يحتوي على total_sessions و consumed_sessions.
- المتبقي يحسب بالمعادلة:
remaining_sessions = total_sessions - consumed_sessions

3. parent_student_links
- يربط ولي الأمر بالطالب (علاقة many-to-many لو لزم).

4. attendance_records
- سجل كل حصة: حاضر/غائب + واجب + درجة + ملاحظات.
- عند تسجيل حاضر، يتم زيادة consumed_sessions تلقائيا.

5. calendar_events
- أحداث التقويم المرتبطة بالمدرس والطالب.

6. invoices
- عند تأكيد الدفع يتم إنشاء فاتورة لولي الأمر تحتوي:
  - اسم الطالب
  - تاريخ الفاتورة
  - عدد الحصص المشحونة
- بدون أي مبلغ مالي.

## 2) المفاتيح الأجنبية (Foreign Keys)

- student_profiles.student_user_id -> users.id
- student_profiles.teacher_user_id -> users.id
- parent_student_links.parent_user_id -> users.id
- parent_student_links.student_user_id -> users.id
- attendance_records.student_user_id -> users.id
- attendance_records.teacher_user_id -> users.id
- calendar_events.teacher_user_id -> users.id
- calendar_events.student_user_id -> users.id
- invoices.student_user_id -> users.id

## 3) لماذا هذا التصميم مناسب

- قابل للتوسع: إضافة خصائص جديدة بدون تكسير الهيكل.
- واضح في الصلاحيات: الدور مخزن مركزيا في users.
- سهل للوحة المدرس: استعلام واحد يجلب طلاب المدرس وحالة العداد.
- سهل للوحة الطالب/ولي الأمر: ربط مباشر ببيانات التتبع والتقويم.

## 4) التنفيذ في المشروع

تمت إضافة Skeleton عملي في:

- academy_skeleton.py

ويحتوي على:

- Role + ROLE_PERMISSIONS
- calculate_remaining_sessions
- SessionCounter
- AcademyDB (init_schema, assign_teacher, teacher_students, add_attendance, set_payment_confirmed, create_calendar_event, get_student_dashboard)
- SCHEMA_SQL

## 5) خطوات تشغيل سريعة

1. إنشاء ملف القاعدة:
   - شغل academy_skeleton.py مرة واحدة لإنشاء academy.db.

2. إضافة مستخدمين:
   - Admin / Assistant / Teacher / Student / Parent في users.

3. ربط الطالب بالمدرس:
   - باستخدام create_student_profile أو assign_teacher.

4. تسجيل الحصص:
   - add_attendance(status='present' أو 'absent').
   - عند present يزيد consumed_sessions تلقائيا.

5. تأكيد الدفع:
   - set_payment_confirmed(student_user_id, charged_sessions).
   - ينشئ فاتورة رقمية بدون مبلغ.

## 6) ملاحظة دمج مع Streamlit الحالي

يمكنك دمج طبقة AcademyDB تدريجيا داخل app.py كالتالي:

- في البداية: استخدمها فقط كمرجع هيكلي (Skeleton).
- لاحقا: استبدل أجزاء القراءة/الكتابة الحالية بعمليات DB منظمة.
- أخيرا: اربط الواجهات (Admin/Teacher/Student/Parent) باستعلامات الجداول الجديدة.
