import os
import re
import random
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for, flash,
                   request, jsonify, send_from_directory, abort)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Course, Enrollment, Material, Assignment, Submission, Attendance, Notification, AIChatHistory

from flask_wtf.csrf import CSRFProtect

if os.environ.get('VERCEL'):
    app = Flask(__name__, instance_path='/tmp/instance')
else:
    app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'doc'
    video_exts = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    image_exts = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg'}
    if ext in video_exts:
        return 'video'
    if ext in image_exts:
        return 'image'
    return ext

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024} KB"
    else:
        return f"{size_bytes // (1024*1024):.1f} MB"

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

def check_deadline_notifications(user):
    """Check upcoming assignment deadlines for a student and create notifications."""
    if user.role != 'student':
        return
    enrolled_course_ids = [e.course_id for e in user.enrollments.all()]
    upcoming = Assignment.query.filter(
        Assignment.course_id.in_(enrolled_course_ids),
        Assignment.deadline > datetime.utcnow(),
        Assignment.deadline <= datetime.utcnow() + timedelta(days=3)
    ).all()
    for asgn in upcoming:
        # Avoid duplicate notifications
        exists = Notification.query.filter_by(
            user_id=user.id, title=f"Deadline: {asgn.title}", is_read=False
        ).first()
        if not exists:
            days_left = asgn.days_until_deadline()
            msg = f"Assignment '{asgn.title}' in {asgn.course.title} is due in {days_left} day(s)!"
            notif = Notification(
                user_id=user.id,
                title=f"Deadline: {asgn.title}",
                message=msg,
                notif_type='deadline'
            )
            db.session.add(notif)
    db.session.commit()

def update_student_progress(student_id, course_id):
    """Recalculate student progress for a course."""
    enrollment = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
    if not enrollment:
        return
    course = db.session.get(Course, course_id)
    total_assignments = course.assignments.count()
    if total_assignments == 0:
        enrollment.progress_percent = 0
    else:
        submitted = Submission.query.join(Assignment).filter(
            Assignment.course_id == course_id,
            Submission.student_id == student_id
        ).count()
        enrollment.progress_percent = round((submitted / total_assignments) * 100, 1)
    db.session.commit()

# ─── AI Assistant ─────────────────────────────────────────────────────────────

AI_RESPONSES = {
    r'hello|hi|hey': "Hello! 👋 I'm your LMS AI Assistant. I can help you understand course materials, check your assignments, and guide your learning journey. What would you like to know?",
    r'assignment|homework': "📝 For assignments, go to **My Courses → Course → Assignments**. Submit before the deadline shown in red. You'll get a notification 3 days before it's due!",
    r'progress|grade|mark|result': "📊 You can check your progress in two ways:\n1. **Dashboard** — shows overall progress bars\n2. **My Progress** page — detailed per-course breakdown with grades",
    r'enroll|register|course|subject': "📚 To enroll in a course: go to **Browse Courses**, filter by your department and year, then click **Enroll**. Courses are recommended based on your year and department.",
    r'material|pdf|video|notes|ppt': "📂 Course materials are in **My Courses → [Course Name] → Materials**. You can view PDFs, watch videos, and download presentations directly.",
    r'attendance|absent|present': "🗓️ Your attendance is tracked by your educator per session. If you have concerns, reach out to your course educator through the course page.",
    r'deadline|due|late|overdue': "⏰ Deadlines are shown on the Assignments page in red. You'll get a push notification 3 days before any deadline. Submit early to avoid issues!",
    r'password|login|account|register': "🔐 For login issues, click 'Forgot Password' on the login page. To register, choose your role (Student/Teacher), fill in your details including department and year.",
    r'help|what can you do|features': "I can help you with:\n• 📚 Understanding courses & materials\n• 📝 Assignment submission guidance\n• 📊 Checking your progress\n• 🗓️ Attendance information\n• ⏰ Deadline reminders\n• 🔐 Account help\n\nJust ask me anything!",
    r'thank|thanks': "You're welcome! 😊 Keep up the great work on your studies! Is there anything else I can help you with?",
}

def ai_response(question):
    q = question.lower().strip()
    for pattern, response in AI_RESPONSES.items():
        if re.search(pattern, q):
            return response
    return f"That's a great question about '{question}'! For the most accurate answer, I recommend:\n1. Checking your course materials\n2. Asking your educator through the course page\n3. Browsing the relevant course section\n\nIs there something more specific I can help clarify? 🎓"

# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}_dashboard"))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            check_deadline_notifications(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Invalid email or password. Please try again.', 'error')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')
        department = request.form.get('department', '')
        year = request.form.get('year', None)

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'error')
            return render_template('auth/register.html')

        colors = ['#4f46e5', '#7c3aed', '#0891b2', '#059669', '#d97706', '#dc2626']
        user = User(
            name=name, email=email, role=role,
            department=department,
            year=int(year) if year else None,
            avatar_color=random.choice(colors)
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Welcome notification
        notif = Notification(
            user_id=user.id,
            title="Welcome to LMS! 🎓",
            message=f"Welcome, {name}! Your account has been created successfully. Start exploring your courses.",
            notif_type='info'
        )
        db.session.add(notif)
        db.session.commit()

        login_user(user, remember=True)
        flash(f'Welcome, {name}! Your account has been created.', 'success')
        return redirect(url_for('index'))
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ─── Student Routes ───────────────────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    check_deadline_notifications(current_user)
    enrollments = current_user.enrollments.all()
    enrolled_courses = [db.session.get(Course, e.course_id) for e in enrollments]
    upcoming_assignments = []
    for course in enrolled_courses:
        for asgn in course.assignments.filter(Assignment.deadline > datetime.utcnow()).all():
            sub = Submission.query.filter_by(assignment_id=asgn.id, student_id=current_user.id).first()
            upcoming_assignments.append({'assignment': asgn, 'course': course, 'submitted': sub is not None})
    upcoming_assignments.sort(key=lambda x: x['assignment'].deadline)
    notifications = current_user.notifications.order_by(Notification.created_at.desc()).limit(5).all()
    return render_template('student/dashboard.html',
                           enrollments=enrollments,
                           enrolled_courses=enrolled_courses,
                           upcoming_assignments=upcoming_assignments[:5],
                           notifications=notifications)

@app.route('/student/courses')
@login_required
@role_required('student')
def student_courses():
    dept = request.args.get('dept', '')
    year = request.args.get('year', '')
    q = request.args.get('q', '')
    query = Course.query.filter_by(status='active')
    if dept:
        query = query.filter(Course.department == dept)
    if year and str(year).isdigit():
        query = query.filter(Course.year == int(year))
    if q:
        query = query.filter(Course.title.ilike(f'%{q}%'))
    courses = query.all()
    enrolled_ids = [e.course_id for e in current_user.enrollments.all()]
    departments = db.session.query(Course.department).distinct().all()
    return render_template('student/courses.html', courses=courses,
                           enrolled_ids=enrolled_ids, departments=departments,
                           dept=dept, year=year, q=q)

@app.route('/student/enroll/<int:course_id>', methods=['POST'])
@login_required
@role_required('student')
def enroll_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.is_enrolled(current_user.id):
        flash('Already enrolled.', 'warning')
    else:
        e = Enrollment(student_id=current_user.id, course_id=course_id)
        db.session.add(e)
        db.session.commit()
        notif = Notification(
            user_id=current_user.id, title="Course Enrolled!",
            message=f"You have successfully enrolled in '{course.title}'.",
            notif_type='info'
        )
        db.session.add(notif)
        db.session.commit()
        flash(f'Successfully enrolled in {course.title}!', 'success')
    return redirect(url_for('student_courses'))

@app.route('/student/course/<int:course_id>')
@login_required
@role_required('student')
def student_course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    if not course.is_enrolled(current_user.id):
        flash('You are not enrolled in this course.', 'warning')
        return redirect(url_for('student_courses'))
    materials = course.materials.order_by(Material.uploaded_at.desc()).all()
    assignments = course.assignments.order_by(Assignment.deadline.asc()).all()
    submissions = {s.assignment_id: s for s in Submission.query.filter_by(student_id=current_user.id).all()}
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    return render_template('student/course_detail.html',
                           course=course, materials=materials,
                           assignments=assignments, submissions=submissions,
                           enrollment=enrollment)

@app.route('/student/submit/<int:assignment_id>', methods=['POST'])
@login_required
@role_required('student')
def submit_assignment(assignment_id):
    asgn = Assignment.query.get_or_404(assignment_id)
    existing = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user.id).first()
    if existing:
        flash('You have already submitted this assignment.', 'warning')
        return redirect(url_for('student_course_detail', course_id=asgn.course_id))
    file = request.files.get('file')
    file_path = None
    file_name = None
    if file and file.filename and allowed_file(file.filename):
        fn = secure_filename(f"sub_{current_user.id}_{assignment_id}_{file.filename}")
        path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
        file.save(path)
        file_path = fn
        file_name = file.filename

    sub = Submission(
        assignment_id=assignment_id, student_id=current_user.id,
        file_path=file_path, file_name=file_name
    )
    db.session.add(sub)
    db.session.commit()
    update_student_progress(current_user.id, asgn.course_id)

    # Notify educator
    course = db.session.get(Course, asgn.course_id)
    notif = Notification(
        user_id=course.educator_id, title="New Assignment Submission",
        message=f"{current_user.name} submitted '{asgn.title}' in {course.title}.",
        notif_type='info'
    )
    db.session.add(notif)
    db.session.commit()
    flash('Assignment submitted successfully!', 'success')
    return redirect(url_for('student_course_detail', course_id=asgn.course_id))

@app.route('/student/progress')
@login_required
@role_required('student')
def student_progress():
    enrollments = current_user.enrollments.all()
    progress_data = []
    for e in enrollments:
        course = db.session.get(Course, e.course_id)
        total_asgn = course.assignments.count()
        submitted = Submission.query.join(Assignment).filter(
            Assignment.course_id == course.id,
            Submission.student_id == current_user.id,
            Submission.marks.isnot(None)
        ).count()
        graded_subs = Submission.query.join(Assignment).filter(
            Assignment.course_id == course.id,
            Submission.student_id == current_user.id,
            Submission.marks.isnot(None)
        ).all()
        avg_marks = None
        if graded_subs:
            total_possible = sum(s.assignment.max_marks for s in graded_subs)
            total_got = sum(s.marks for s in graded_subs)
            avg_marks = round((total_got / total_possible) * 100, 1) if total_possible > 0 else 0
        progress_data.append({
            'course': course,
            'enrollment': e,
            'total_assignments': total_asgn,
            'graded_count': submitted,
            'avg_marks': avg_marks
        })
    return render_template('student/progress.html', progress_data=progress_data)

@app.route('/student/assignments')
@login_required
@role_required('student')
def student_assignments():
    enrolled_ids = [e.course_id for e in current_user.enrollments.all()]
    all_assignments = Assignment.query.filter(Assignment.course_id.in_(enrolled_ids)).order_by(Assignment.deadline).all()
    submissions = {s.assignment_id: s for s in Submission.query.filter_by(student_id=current_user.id).all()}
    return render_template('student/assignments.html',
                           all_assignments=all_assignments, submissions=submissions)

# ─── Educator Routes ──────────────────────────────────────────────────────────

@app.route('/educator/dashboard')
@login_required
@role_required('educator')
def educator_dashboard():
    courses = current_user.courses_taught.all()
    total_students = sum(c.enrollment_count() for c in courses)
    total_assignments = sum(c.assignments.count() for c in courses)
    pending_grading = 0
    for c in courses:
        for asgn in c.assignments.all():
            pending_grading += asgn.submissions.filter(Submission.marks.is_(None)).count()
    recent_submissions = Submission.query.join(Assignment).join(Course).filter(
        Course.educator_id == current_user.id
    ).order_by(Submission.submitted_at.desc()).limit(8).all()
    notifications = current_user.notifications.order_by(Notification.created_at.desc()).limit(5).all()
    return render_template('educator/dashboard.html',
                           courses=courses, total_students=total_students,
                           total_assignments=total_assignments,
                           pending_grading=pending_grading,
                           recent_submissions=recent_submissions,
                           notifications=notifications)

@app.route('/educator/courses')
@login_required
@role_required('educator')
def educator_courses():
    courses = current_user.courses_taught.order_by(Course.created_at.desc()).all()
    return render_template('educator/courses.html', courses=courses)

@app.route('/educator/course/new', methods=['GET', 'POST'])
@login_required
@role_required('educator')
def educator_new_course():
    if request.method == 'POST':
        icons = ['ri-code-line', 'ri-book-line', 'ri-flask-line', 'ri-calculator-line',
                 'ri-global-line', 'ri-microscope-line', 'ri-cpu-line', 'ri-bar-chart-line']
        colors = ['#4f46e5', '#7c3aed', '#0891b2', '#059669', '#d97706', '#dc2626', '#ec4899']
        yr_val = request.form.get('year')
        year_int = int(yr_val) if yr_val and str(yr_val).isdigit() else None
        course = Course(
            title=request.form.get('title'),
            description=request.form.get('description'),
            department=request.form.get('department'),
            year=year_int,
            educator_id=current_user.id,
            status=request.form.get('status', 'active'),
            icon=random.choice(icons),
            icon_color=random.choice(colors)
        )
        db.session.add(course)
        db.session.commit()
        flash(f'Course "{course.title}" created successfully!', 'success')
        return redirect(url_for('educator_courses'))
    return render_template('educator/course_editor.html', course=None)

@app.route('/educator/course/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('educator')
def educator_edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.educator_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        course.title = request.form.get('title')
        course.description = request.form.get('description')
        course.department = request.form.get('department')
        yr_val = request.form.get('year')
        course.year = int(yr_val) if yr_val and str(yr_val).isdigit() else None
        course.status = request.form.get('status', 'active')
        db.session.commit()
        flash('Course updated successfully!', 'success')
        return redirect(url_for('educator_courses'))
    return render_template('educator/course_editor.html', course=course)

@app.route('/educator/course/<int:course_id>/delete', methods=['POST'])
@login_required
@role_required('educator')
def educator_delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.educator_id != current_user.id:
        abort(403)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted successfully.', 'success')
    return redirect(url_for('educator_courses'))

@app.route('/educator/course/<int:course_id>/materials', methods=['GET', 'POST'])
@login_required
@role_required('educator')
def educator_materials(course_id):
    course = Course.query.get_or_404(course_id)
    if course.educator_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '')
        file = request.files.get('file')
        if file and file.filename and allowed_file(file.filename):
            fn = secure_filename(f"mat_{course_id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
            file.save(path)
            size = format_file_size(os.path.getsize(path))
            ftype = get_file_type(file.filename)
            mat = Material(
                course_id=course_id, title=title or file.filename,
                file_path=fn, file_name=file.filename,
                file_type=ftype, file_size=size, description=description
            )
            db.session.add(mat)
            db.session.commit()
            # Notify all enrolled students
            for enrollment in course.enrollments.all():
                notif = Notification(
                    user_id=enrollment.student_id,
                    title=f"New Material in {course.title}",
                    message=f"'{title or file.filename}' has been added to {course.title}.",
                    notif_type='info'
                )
                db.session.add(notif)
            db.session.commit()
            flash('Material uploaded successfully!', 'success')
        else:
            flash('Invalid file type or no file selected.', 'error')
        return redirect(url_for('educator_materials', course_id=course_id))
    materials = course.materials.order_by(Material.uploaded_at.desc()).all()
    return render_template('educator/materials.html', course=course, materials=materials)

@app.route('/educator/material/<int:material_id>/delete', methods=['POST'])
@login_required
@role_required('educator')
def delete_material(material_id):
    mat = Material.query.get_or_404(material_id)
    course = db.session.get(Course, mat.course_id)
    if course.educator_id != current_user.id:
        abort(403)
    if mat.file_path:
        fp = os.path.join(app.config['UPLOAD_FOLDER'], mat.file_path)
        if os.path.exists(fp):
            os.remove(fp)
    db.session.delete(mat)
    db.session.commit()
    flash('Material deleted.', 'success')
    return redirect(url_for('educator_materials', course_id=mat.course_id))

@app.route('/educator/course/<int:course_id>/assignments', methods=['GET', 'POST'])
@login_required
@role_required('educator')
def educator_assignments(course_id):
    course = Course.query.get_or_404(course_id)
    if course.educator_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            deadline_str = request.form.get('deadline')
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            asgn = Assignment(
                course_id=course_id,
                title=request.form.get('title'),
                description=request.form.get('description'),
                deadline=deadline,
                max_marks=int(request.form.get('max_marks', 100))
            )
            db.session.add(asgn)
            db.session.commit()
            # Notify enrolled students
            for enrollment in course.enrollments.all():
                notif = Notification(
                    user_id=enrollment.student_id,
                    title=f"New Assignment: {asgn.title}",
                    message=f"New assignment '{asgn.title}' posted in {course.title}. Due: {deadline.strftime('%d %b %Y %H:%M')}",
                    notif_type='warning'
                )
                db.session.add(notif)
            db.session.commit()
            flash('Assignment created and students notified!', 'success')
        elif action == 'grade':
            sub_id = request.form.get('submission_id')
            sub = Submission.query.get_or_404(sub_id)
            sub.marks = float(request.form.get('marks', 0))
            sub.feedback = request.form.get('feedback', '')
            sub.status = 'graded'
            db.session.commit()
            update_student_progress(sub.student_id, course_id)
            # Notify student
            notif = Notification(
                user_id=sub.student_id,
                title="Assignment Graded!",
                message=f"Your submission for '{sub.assignment.title}' has been graded. Marks: {sub.marks}/{sub.assignment.max_marks}",
                notif_type='grade'
            )
            db.session.add(notif)
            db.session.commit()
            flash('Grade submitted and student notified!', 'success')
        return redirect(url_for('educator_assignments', course_id=course_id))

    assignments = course.assignments.order_by(Assignment.deadline.asc()).all()
    assignments_data = []
    for asgn in assignments:
        submissions = asgn.submissions.all()
        assignments_data.append({
            'assignment': asgn,
            'submissions': submissions,
            'submitted_count': len(submissions),
            'graded_count': sum(1 for s in submissions if s.marks is not None)
        })
    enrolled_students = [e.student for e in course.enrollments.all()]
    return render_template('educator/assignments.html', course=course,
                           assignments_data=assignments_data,
                           enrolled_students=enrolled_students)

@app.route('/educator/course/<int:course_id>/attendance', methods=['GET', 'POST'])
@login_required
@role_required('educator')
def educator_attendance(course_id):
    course = Course.query.get_or_404(course_id)
    if course.educator_id != current_user.id:
        abort(403)
    students = [e.student for e in course.enrollments.all()]
    if request.method == 'POST':
        att_date_str = request.form.get('date')
        att_date = datetime.strptime(att_date_str, '%Y-%m-%d').date()
        for student in students:
            status = request.form.get(f'status_{student.id}', 'absent')
            existing = Attendance.query.filter_by(
                course_id=course_id, student_id=student.id, date=att_date
            ).first()
            if existing:
                existing.status = status
            else:
                att = Attendance(
                    course_id=course_id, student_id=student.id,
                    date=att_date, status=status, marked_by=current_user.id
                )
                db.session.add(att)
            if status == 'absent':
                notif = Notification(
                    user_id=student.id,
                    title="Attendance Alert",
                    message=f"You were marked absent in {course.title} on {att_date.strftime('%d %b %Y')}.",
                    notif_type='warning'
                )
                db.session.add(notif)
        db.session.commit()
        flash(f'Attendance marked for {att_date.strftime("%d %b %Y")}!', 'success')
        return redirect(url_for('educator_attendance', course_id=course_id))

    # Attendance summary per student
    summary = []
    for student in students:
        total = Attendance.query.filter_by(course_id=course_id, student_id=student.id).count()
        present = Attendance.query.filter_by(course_id=course_id, student_id=student.id, status='present').count()
        pct = round((present / total) * 100, 1) if total > 0 else 0
        summary.append({'student': student, 'total': total, 'present': present, 'percent': pct})

    # Recent attendance records
    recent_dates = db.session.query(Attendance.date).filter_by(course_id=course_id)\
        .distinct().order_by(Attendance.date.desc()).limit(7).all()
    recent_dates = [r.date for r in recent_dates]

    return render_template('educator/attendance.html', course=course,
                           students=students, summary=summary,
                           recent_dates=recent_dates, today=date.today())

@app.route('/educator/student/<int:student_id>')
@login_required
@role_required('educator')
def educator_student_profile(student_id):
    student = User.query.get_or_404(student_id)
    # Only show students in educator's courses
    educator_course_ids = [c.id for c in current_user.courses_taught.all()]
    enrolled_in_my_courses = Enrollment.query.filter(
        Enrollment.student_id == student_id,
        Enrollment.course_id.in_(educator_course_ids)
    ).all()
    if not enrolled_in_my_courses:
        abort(403)
    student_data = []
    for e in enrolled_in_my_courses:
        course = db.session.get(Course, e.course_id)
        submissions = Submission.query.join(Assignment).filter(
            Assignment.course_id == course.id,
            Submission.student_id == student_id
        ).all()
        att_total = Attendance.query.filter_by(course_id=course.id, student_id=student_id).count()
        att_present = Attendance.query.filter_by(course_id=course.id, student_id=student_id, status='present').count()
        att_pct = round((att_present / att_total) * 100, 1) if att_total > 0 else 0
        student_data.append({
            'course': course,
            'enrollment': e,
            'submissions': submissions,
            'att_percent': att_pct,
            'att_total': att_total
        })
    return render_template('educator/student_profile.html',
                           student=student, student_data=student_data)

# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    total_students = User.query.filter_by(role='student').count()
    total_educators = User.query.filter_by(role='educator').count()
    total_courses = Course.query.count()
    total_assignments = Assignment.query.count()
    total_submissions = Submission.query.count()
    courses = Course.query.order_by(Course.created_at.desc()).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_submissions = Submission.query.order_by(Submission.submitted_at.desc()).limit(8).all()
    # Chart data
    course_labels = [c.title[:20] for c in courses[:6]]
    course_enrollments = [c.enrollment_count() for c in courses[:6]]
    return render_template('admin/dashboard.html',
                           total_students=total_students, total_educators=total_educators,
                           total_courses=total_courses, total_assignments=total_assignments,
                           total_submissions=total_submissions,
                           courses=courses, recent_users=recent_users,
                           recent_submissions=recent_submissions,
                           course_labels=course_labels,
                           course_enrollments=course_enrollments)

# ─── Shared Routes ────────────────────────────────────────────────────────────

@app.route('/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        abort(403)
    notif.is_read = True
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    current_user.notifications.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/notifications/data')
@login_required
def notifications_data():
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).limit(10).all()
    return jsonify({
        'count': current_user.unread_notifications_count(),
        'notifications': [{
            'id': n.id, 'title': n.title, 'message': n.message,
            'type': n.notif_type, 'is_read': n.is_read,
            'created_at': n.created_at.strftime('%d %b, %H:%M')
        } for n in notifs]
    })

@app.route('/ai/chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.get_json()
    question = data.get('message', '').strip()
    if not question:
        return jsonify({'response': 'Please ask a question!'})
    answer = ai_response(question)
    history = AIChatHistory(user_id=current_user.id, question=question, answer=answer)
    db.session.add(history)
    db.session.commit()
    return jsonify({'response': answer})

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

# ─── CLI Commands ─────────────────────────────────────────────────────────────

@app.cli.command('seed')
def seed_db():
    """Seed the database with demo data."""
    db.create_all()

    # Educators
    educators_data = [
        ('Dr. Sarah Johnson', 'sarah@lms.com', 'Computer Science', '#4f46e5'),
        ('Prof. Raj Kumar', 'raj@lms.com', 'Electronics', '#0891b2'),
    ]
    educators = []
    for name, email, dept, color in educators_data:
        if not User.query.filter_by(email=email).first():
            e = User(name=name, email=email, role='educator', department=dept, avatar_color=color)
            e.set_password('educator123')
            db.session.add(e)
            db.session.flush()
            educators.append(e)
        else:
            educators.append(User.query.filter_by(email=email).first())

    # Students
    students_data = [
        ('Alice Chen', 'alice@lms.com', 'Computer Science', 2, '#7c3aed'),
        ('Bob Smith', 'bob@lms.com', 'Computer Science', 2, '#059669'),
        ('Carol Davis', 'carol@lms.com', 'Electronics', 3, '#d97706'),
    ]
    students = []
    for name, email, dept, yr, color in students_data:
        if not User.query.filter_by(email=email).first():
            s = User(name=name, email=email, role='student', department=dept, year=yr, avatar_color=color)
            s.set_password('student123')
            db.session.add(s)
            db.session.flush()
            students.append(s)
        else:
            students.append(User.query.filter_by(email=email).first())

    db.session.commit()

    # Courses
    icons_colors = [
        ('ri-code-line', '#4f46e5'), ('ri-cpu-line', '#0891b2'),
        ('ri-database-line', '#059669'), ('ri-wifi-line', '#7c3aed')
    ]
    courses_data = [
        ('Web Development', 'Learn HTML, CSS, JavaScript and modern web frameworks', 'Computer Science', 2, educators[0]),
        ('Data Structures & Algorithms', 'Core CS algorithms and data structures for problem solving', 'Computer Science', 2, educators[0]),
        ('Database Systems', 'Relational databases, SQL, and database design principles', 'Computer Science', 3, educators[0]),
        ('Digital Electronics', 'Logic gates, circuits, and digital system design', 'Electronics', 3, educators[1]),
    ]
    courses = []
    for i, (title, desc, dept, yr, edu) in enumerate(courses_data):
        if not Course.query.filter_by(title=title).first():
            icon, color = icons_colors[i]
            c = Course(title=title, description=desc, department=dept, year=yr,
                       educator_id=edu.id, status='active', icon=icon, icon_color=color)
            db.session.add(c)
            db.session.flush()
            courses.append(c)
        else:
            courses.append(Course.query.filter_by(title=title).first())

    db.session.commit()

    # Enrollments
    for s in students:
        for c in courses:
            if c.department == s.department and not c.is_enrolled(s.id):
                e = Enrollment(student_id=s.id, course_id=c.id, progress_percent=random.randint(20, 80))
                db.session.add(e)

    db.session.commit()

    # Assignments
    for c in courses:
        if c.assignments.count() == 0:
            for i in range(2):
                deadline = datetime.utcnow() + timedelta(days=random.randint(1, 14))
                asgn = Assignment(
                    course_id=c.id,
                    title=f"{c.title} - Assignment {i+1}",
                    description=f"Complete the given tasks for {c.title} assignment {i+1}. Submit your work as a PDF or document.",
                    deadline=deadline, max_marks=100
                )
                db.session.add(asgn)
    db.session.commit()

    print("[OK] Database seeded successfully!")
    print("   Teacher:  sarah@lms.com / educator123")
    print("   Student:  alice@lms.com / student123")

# ─── App Entry ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
