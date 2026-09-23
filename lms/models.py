from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # student / educator / admin
    department = db.Column(db.String(100))
    year = db.Column(db.Integer)  # for students: 1-4
    avatar_color = db.Column(db.String(20), default='#4f46e5')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active_account = db.Column(db.Boolean, default=True)

    # Relationships
    courses_taught = db.relationship('Course', backref='educator', lazy='dynamic', foreign_keys='Course.educator_id')
    enrollments = db.relationship('Enrollment', backref='student', lazy='dynamic', foreign_keys='Enrollment.student_id')
    submissions = db.relationship('Submission', backref='student', lazy='dynamic', foreign_keys='Submission.student_id')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    attendances = db.relationship('Attendance', backref='student', lazy='dynamic', foreign_keys='Attendance.student_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_initials(self):
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return parts[0][0].upper() + parts[-1][0].upper()
        return self.name[:2].upper()

    def unread_notifications_count(self):
        return self.notifications.filter_by(is_read=False).count()


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    department = db.Column(db.String(100))
    year = db.Column(db.Integer)
    educator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active / draft / archived
    icon = db.Column(db.String(50), default='ri-book-line')
    icon_color = db.Column(db.String(20), default='#4f46e5')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    enrollments = db.relationship('Enrollment', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    materials = db.relationship('Material', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='course', lazy='dynamic', cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', backref='course', lazy='dynamic', cascade='all, delete-orphan')

    def enrollment_count(self):
        return self.enrollments.count()

    def is_enrolled(self, student_id):
        return self.enrollments.filter_by(student_id=student_id).first() is not None


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress_percent = db.Column(db.Float, default=0.0)
    __table_args__ = (db.UniqueConstraint('student_id', 'course_id'),)


class Material(db.Model):
    __tablename__ = 'materials'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    file_type = db.Column(db.String(20))  # pdf / ppt / video / image / doc
    file_size = db.Column(db.String(20))
    description = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_icon(self):
        icons = {
            'pdf': ('ri-file-pdf-line', '#ef4444'),
            'ppt': ('ri-file-ppt-line', '#f97316'),
            'pptx': ('ri-file-ppt-line', '#f97316'),
            'video': ('ri-video-line', '#8b5cf6'),
            'mp4': ('ri-video-line', '#8b5cf6'),
            'image': ('ri-image-line', '#10b981'),
            'png': ('ri-image-line', '#10b981'),
            'jpg': ('ri-image-line', '#10b981'),
            'doc': ('ri-file-word-line', '#3b82f6'),
            'docx': ('ri-file-word-line', '#3b82f6'),
        }
        key = self.file_type.lower() if self.file_type else 'doc'
        return icons.get(key, ('ri-file-line', '#6b7280'))


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    max_marks = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    submissions = db.relationship('Submission', backref='assignment', lazy='dynamic', cascade='all, delete-orphan')

    def days_until_deadline(self):
        delta = self.deadline - datetime.utcnow()
        return delta.days

    def is_overdue(self):
        return datetime.utcnow() > self.deadline

    def submission_count(self):
        return self.submissions.count()


class Submission(db.Model):
    __tablename__ = 'submissions'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    file_path = db.Column(db.String(500))
    file_name = db.Column(db.String(200))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    marks = db.Column(db.Float)
    feedback = db.Column(db.Text)
    status = db.Column(db.String(20), default='submitted')  # submitted / graded
    __table_args__ = (db.UniqueConstraint('assignment_id', 'student_id'),)


class Attendance(db.Model):
    __tablename__ = 'attendances'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # present / absent / late
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    __table_args__ = (db.UniqueConstraint('course_id', 'student_id', 'date'),)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    notif_type = db.Column(db.String(30), default='info')  # info / warning / deadline / grade
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AIChatHistory(db.Model):
    __tablename__ = 'ai_chat_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
