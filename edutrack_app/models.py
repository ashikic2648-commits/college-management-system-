from datetime import date, datetime
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from . import db, login_manager


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    head = db.Column(db.String(120))


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    department = db.relationship("Department", backref="courses")


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    roll_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    gender = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    admission_year = db.Column(db.Integer, nullable=False)
    address = db.Column(db.Text)
    photo_filename = db.Column(db.String(100))
    status = db.Column(db.String(20), default="Active")
    department = db.relationship("Department")
    course = db.relationship("Course")
    user = db.relationship("User")


class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    employee_id = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    designation = db.Column(db.String(100))
    status = db.Column(db.String(20), default="Active")
    department = db.relationship("Department")
    user = db.relationship("User")


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"))
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"))
    semester = db.Column(db.Integer)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"))
    department = db.relationship("Department")
    course = db.relationship("Course")
    faculty = db.relationship("Faculty")


class AcademicYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    student = db.relationship("Student")
    subject = db.relationship("Subject")
    __table_args__ = (db.UniqueConstraint("student_id", "subject_id", "date", name="uq_attendance"),)


class Mark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    examination = db.Column(db.String(50), nullable=False)
    obtained_marks = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False, default=100)
    student = db.relationship("Student")
    subject = db.relationship("Subject")
    __table_args__ = (db.UniqueConstraint("student_id", "subject_id", "examination", name="uq_mark"),)

    @property
    def percentage(self):
        return round(self.obtained_marks / self.max_marks * 100, 2) if self.max_marks else 0

    @property
    def grade(self):
        p = self.percentage
        if p >= 90: return "A+"
        if p >= 80: return "A"
        if p >= 70: return "B"
        if p >= 60: return "C"
        if p >= 50: return "D"
        return "F"


class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    room = db.Column(db.String(30))
    department = db.relationship("Department")
    course = db.relationship("Course")
    subject = db.relationship("Subject")
    faculty = db.relationship("Faculty")


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"))
    due_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.relationship("Subject")
    faculty = db.relationship("Faculty")


class AssignmentSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    grade = db.Column(db.Float)
    feedback = db.Column(db.Text)
    assignment = db.relationship("Assignment", backref="submissions")
    student = db.relationship("Student", backref="assignment_submissions")
    __table_args__ = (
        db.UniqueConstraint("assignment_id", "student_id", name="uq_assignment_student_submission"),
    )


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, default="General")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    read_at = db.Column(db.DateTime)
    user = db.relationship("User", backref="notifications")


class LoginEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    attempted_email = db.Column(db.String(120), nullable=False, index=True)
    role = db.Column(db.String(20))
    succeeded = db.Column(db.Boolean, nullable=False, default=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user = db.relationship("User")


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), default="General")
    important = db.Column(db.Boolean, default=False)
    publication_date = db.Column(db.Date, default=date.today)
    expires_at = db.Column(db.Date)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"))
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.relationship("Subject")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")


def audit(user, action, description):
    db.session.add(AuditLog(user_id=user.id if user else None, action=action, description=description))


def seed_demo_data():
    if User.query.count():
        return

    users = [
        ("Administrator", "admin@edutrack.com", "admin", "Administrator"),
        ("Dr. Sarah Wilson", "faculty@edutrack.com", "faculty", "Faculty"),
        ("Alex Student", "student@edutrack.com", "student", "Student"),
        ("Management User", "management@edutrack.com", "management", "Management"),
    ]
    created_users = {}
    for name, email, role, display_role in users:
        user = User(name=name, email=email, role=role)
        user.set_password("EduTrack123!")
        db.session.add(user)
        created_users[role] = user
    db.session.flush()

    departments = [
        Department(name="Computer Science", code="CSE", head="Dr. Sarah Wilson"),
        Department(name="Business Administration", code="BBA", head="Prof. Michael Chen"),
        Department(name="Electrical Engineering", code="EEE", head="Dr. Laura Adams"),
    ]
    db.session.add_all(departments)
    db.session.flush()

    courses = [
        Course(name="Bachelor of Computer Applications", code="BCA", department_id=departments[0].id),
        Course(name="Bachelor of Business Administration", code="BBA", department_id=departments[1].id),
        Course(name="Bachelor of Technology", code="BTECH", department_id=departments[2].id),
    ]
    db.session.add_all(courses)
    db.session.flush()

    faculty = []
    for i in range(1, 3):
        f = Faculty(
            user_id=created_users["faculty"].id if i == 1 else None,
            employee_id=f"FAC{i:03}",
            full_name=["Dr. Sarah Wilson", "Prof. Michael Chen"][i - 1],
            email=f"faculty{i}@edutrack.com",
            phone=f"98765000{i}",
            department_id=departments[i - 1].id,
            designation="Assistant Professor",
        )
        db.session.add(f)
        faculty.append(f)
    db.session.flush()

    students = []
    for i in range(1, 21):
        department_index = (i - 1) % 3
        dept = departments[department_index]
        course = courses[department_index]
        course_position = (i - 1) // 3
        semester = (3 if course_position % 2 == 0 else 5) if department_index == 0 else (
            1 if department_index == 1 else 2
        )
        student_user = None
        if i == 1:
            student_user = created_users["student"]
        s = Student(
            user_id=student_user.id if student_user else None,
            roll_number=f"ET{i:04}",
            full_name=f"Student {i}",
            email=f"student{i}@edutrack.com",
            phone=f"912340{i:04}",
            gender="Female" if i % 2 == 0 else "Male",
            date_of_birth=date(2004, (i % 12) + 1, (i % 28) + 1),
            department_id=dept.id,
            course_id=course.id,
            semester=semester,
            admission_year=2024,
            address=f"{i} College Avenue",
        )
        db.session.add(s)
        students.append(s)
    db.session.flush()

    subjects = [
        Subject(name="Data Structures", code="CSE201", department_id=departments[0].id, course_id=courses[0].id, semester=3, faculty_id=faculty[0].id),
        Subject(name="Database Systems", code="CSE301", department_id=departments[0].id, course_id=courses[0].id, semester=5, faculty_id=faculty[0].id),
        Subject(name="Business Management", code="BBA101", department_id=departments[1].id, course_id=courses[1].id, semester=1, faculty_id=faculty[1].id),
        Subject(name="Digital Electronics", code="EEE202", department_id=departments[2].id, course_id=courses[2].id, semester=2, faculty_id=faculty[1].id),
    ]
    db.session.add_all(subjects)
    db.session.flush()

    today = date.today()
    for student in students:
        subject_options = [
            item for item in subjects
            if item.course_id == student.course_id and item.semester == student.semester
        ]
        subject = subject_options[(student.id - 1) % len(subject_options)] if subject_options else next(
            item for item in subjects if item.course_id == student.course_id
        )
        for offset in range(12):
            attendance_date = date.fromordinal(today.toordinal() - offset)
            db.session.add(Attendance(student_id=student.id, subject_id=subject.id, date=attendance_date,
                                      status="Present" if (student.id + offset) % 5 else "Absent"))
        db.session.add(Mark(student_id=student.id, subject_id=subject.id, examination="Internal 1",
                            obtained_marks=50 + ((student.id * 7) % 45), max_marks=100))

    for i, subject in enumerate(subjects):
        db.session.add(Timetable(department_id=subject.department_id, course_id=subject.course_id,
                                 subject_id=subject.id, faculty_id=subject.faculty_id, semester=subject.semester,
                                 day=["Monday", "Tuesday", "Wednesday", "Thursday"][i],
                                 start_time=f"{9 + i}:00", end_time=f"{10 + i}:00", room=f"R-{101 + i}"))

    db.session.add_all([
        Assignment(title="Database Mini Project", description="Submit a normalized database design.", subject_id=subjects[1].id, faculty_id=faculty[0].id, due_date=date.fromordinal(today.toordinal() + 7)),
        Assignment(title="Data Structures Lab", description="Complete linked-list exercises.", subject_id=subjects[0].id, faculty_id=faculty[0].id, due_date=date.fromordinal(today.toordinal() + 3)),
        Assignment(title="Management Case Study", description="Analyze the assigned case study.", subject_id=subjects[2].id, faculty_id=faculty[1].id, due_date=date.fromordinal(today.toordinal() + 10)),
    ])
    db.session.add_all([
        Announcement(title="Semester Examination Schedule", content="The examination schedule has been published. Please review it in the timetable section.", category="Examination", important=True),
        Announcement(title="Campus Careers Fair", content="The annual careers fair is scheduled for next month.", category="Event", important=False),
        Announcement(title="Library Maintenance", content="The digital library will undergo maintenance on Saturday.", category="General", important=False),
    ])
    db.session.commit()
