from datetime import date
from datetime import datetime, timedelta
from io import BytesIO
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file, abort, current_app, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from openpyxl import Workbook
from . import db
from .models import (
    User, Student, Faculty, Department, Course, Subject, Attendance, Mark,
    Timetable, Assignment, Announcement, AuditLog, AssignmentSubmission, audit,
)
from .models import LoginEvent
from .models import Notification
from .services import academic_risk_rows, notify_active_users, notify_cohort, notify_user


admin_bp = Blueprint("admin", __name__)


def admin_required():
    return current_user.is_authenticated and current_user.role == "admin"


def management_allowed():
    return current_user.is_authenticated and current_user.role in ("admin", "management")


@admin_bp.route("/")
@login_required
def dashboard():
    if current_user.role == "student":
        return redirect(url_for("student.profile"))
    if current_user.role == "management":
        return redirect(url_for("management.dashboard"))
    if current_user.role == "faculty":
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first()
        subjects = Subject.query.filter_by(faculty_id=faculty_member.id).all() if faculty_member else []
        cohorts = {(item.department_id, item.course_id, item.semester) for item in subjects}
        students = [
            student for student in Student.query.filter(Student.user_id.isnot(None)).all()
            if (student.department_id, student.course_id, student.semester) in cohorts
        ]
        student_ids = [student.id for student in students]
        attendance = Attendance.query.filter(Attendance.student_id.in_(student_ids)).all() if student_ids else []
        present = sum(record.status == "Present" for record in attendance)
        marks = Mark.query.filter(Mark.student_id.in_(student_ids)).all() if student_ids else []
        average_marks = round(sum(mark.percentage for mark in marks) / len(marks), 1) if marks else 0
        today_entries = Timetable.query.filter_by(
            faculty_id=faculty_member.id, day=date.today().strftime("%A")
        ).order_by(Timetable.start_time).all() if faculty_member else []
        assignments = Assignment.query.filter(
            (Assignment.faculty_id == faculty_member.id) | (Subject.faculty_id == faculty_member.id)
        ).join(Subject).order_by(Assignment.due_date).limit(5).all() if faculty_member else []
        activities = AuditLog.query.filter_by(user_id=current_user.id).order_by(
            AuditLog.timestamp.desc()
        ).limit(5).all()
        return render_template(
            "faculty_dashboard.html", subjects=subjects, students=students,
            attendance_percentage=round(present / len(attendance) * 100, 1) if attendance else 0,
            average_marks=average_marks, today_entries=today_entries,
            assignments=assignments, activities=activities,
        )
    student_count = Student.query.filter(Student.user_id.isnot(None)).count()
    faculty_count = Faculty.query.count()
    department_count = Department.query.count()
    course_count = Course.query.count()
    attendance_rows = Attendance.query.join(Student).filter(Student.user_id.isnot(None)).all()
    present_count = sum(1 for row in attendance_rows if row.status == "Present")
    avg_attendance = round(present_count / len(attendance_rows) * 100, 1) if attendance_rows else 0
    marks = Mark.query.join(Student).filter(Student.user_id.isnot(None)).all()
    avg_marks = round(sum(row.percentage for row in marks) / len(marks), 1) if marks else 0
    today_attendance = sum(1 for row in attendance_rows if row.date == date.today())
    announcements = Announcement.query.order_by(Announcement.publication_date.desc()).limit(5).all()
    assignments = Assignment.query.order_by(Assignment.due_date.asc()).limit(5).all()
    activities = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
    risk_rows = academic_risk_rows()
    return render_template("dashboard.html",
        student_count=student_count, faculty_count=faculty_count,
        department_count=department_count, course_count=course_count,
        avg_attendance=avg_attendance, avg_marks=avg_marks,
        today_attendance=today_attendance, announcements=announcements,
        assignments=assignments, activities=activities,
        high_risk_count=sum(row["risk"] == "High Risk" for row in risk_rows),
    )


@admin_bp.route("/departments", methods=["GET", "POST"])
@login_required
def departments():
    if not management_allowed():
        flash("You do not have permission to manage departments.", "danger")
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        name = request.form["name"].strip()
        code = request.form["code"].strip().upper()
        if Department.query.filter((Department.name == name) | (Department.code == code)).first():
            flash("Department name or code already exists.", "danger")
        else:
            db.session.add(Department(name=name, code=code, head=request.form.get("head")))
            audit(current_user, "Department Created", f"Created department {name}")
            db.session.commit()
            flash("Department added.", "success")
        return redirect(url_for("admin.departments"))
    return render_template("departments.html", items=Department.query.order_by(Department.name).all())


@admin_bp.route("/departments/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_department(item_id):
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.departments"))
    item = db.session.get(Department, item_id)
    if item:
        db.session.delete(item)
        audit(current_user, "Department Deleted", f"Deleted department {item.name}")
        db.session.commit()
        flash("Department deleted.", "success")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/courses", methods=["GET", "POST"])
@login_required
def courses():
    if not management_allowed():
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        db.session.add(Course(name=request.form["name"].strip(), code=request.form["code"].strip().upper(),
                              department_id=request.form["department_id"]))
        audit(current_user, "Course Created", f"Created course {request.form['name']}")
        db.session.commit()
        flash("Course added.", "success")
        return redirect(url_for("admin.courses"))
    return render_template("courses.html", items=Course.query.all(), departments=Department.query.all())


@admin_bp.route("/subjects", methods=["GET", "POST"])
@login_required
def subjects():
    if not management_allowed():
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if not admin_required():
            flash("Administrator access required to assign subjects.", "danger")
            return redirect(url_for("admin.subjects"))
        department_id = request.form.get("department_id", type=int)
        course_id = request.form.get("course_id", type=int)
        faculty_id = request.form.get("faculty_id", type=int)
        code = request.form.get("code", "").strip().upper()
        department = db.session.get(Department, department_id) if department_id else None
        course = db.session.get(Course, course_id) if course_id else None
        faculty_member = db.session.get(Faculty, faculty_id) if faculty_id else None
        if not department or not course or course.department_id != department.id:
            flash("Select a course that belongs to the selected department.", "danger")
            return redirect(url_for("admin.subjects"))
        if faculty_member and faculty_member.department_id != department.id:
            flash("The faculty member must belong to the subject department.", "danger")
            return redirect(url_for("admin.subjects"))
        if Subject.query.filter_by(code=code).first():
            flash("A subject with this code already exists.", "danger")
            return redirect(url_for("admin.subjects"))
        db.session.add(Subject(name=request.form["name"].strip(), code=code,
                               department_id=department.id, course_id=course.id,
                               semester=int(request.form["semester"] or 1), faculty_id=faculty_id))
        audit(current_user, "Subject Created", f"Created subject {request.form['name'].strip()}")
        db.session.commit()
        flash("Subject added.", "success")
        return redirect(url_for("admin.subjects"))
    return render_template("subjects.html", items=Subject.query.all(), departments=Department.query.all(),
                           courses=Course.query.all(), faculties=Faculty.query.all())


@admin_bp.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if not management_allowed() and current_user.role != "faculty":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if not admin_required():
            flash("Administrator access required.", "danger")
            return redirect(url_for("admin.students"))
        roll = request.form["roll_number"].strip()
        department = db.session.get(Department, request.form.get("department_id", type=int))
        course = db.session.get(Course, request.form.get("course_id", type=int))
        if Student.query.filter_by(roll_number=roll).first():
            flash("Duplicate roll number.", "danger")
        elif Student.query.filter_by(email=request.form.get("email", "").strip().lower()).first():
            flash("A student already uses this email address.", "danger")
        elif not department or not course or course.department_id != department.id:
            flash("Select a course that belongs to the selected department.", "danger")
        else:
            dob = date.fromisoformat(request.form["date_of_birth"]) if request.form.get("date_of_birth") else None
            student = Student(
                roll_number=roll, full_name=request.form["full_name"].strip(),
                email=request.form["email"].strip(), phone=request.form.get("phone"),
                gender=request.form.get("gender"), date_of_birth=dob,
                department_id=department.id, course_id=course.id,
                semester=int(request.form["semester"]), admission_year=int(request.form["admission_year"]),
                address=request.form.get("address"), status=request.form.get("status", "Active"),
            )
            db.session.add(student)
            audit(current_user, "Student Created", f"Created student {student.full_name}")
            db.session.commit()
            flash("Student added.", "success")
        return redirect(url_for("admin.students"))
    query = Student.query.filter(Student.user_id.isnot(None))
    search = request.args.get("q", "").strip()
    department_id = request.args.get("department")
    if current_user.role == "faculty":
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first()
        subjects = Subject.query.filter_by(faculty_id=faculty_member.id).all() if faculty_member else []
        cohorts = [
            (Student.department_id == subject.department_id)
            & (Student.course_id == subject.course_id)
            & (Student.semester == subject.semester)
            for subject in subjects
        ]
        query = query.filter(or_(*cohorts)) if cohorts else query.filter(False)
    if search:
        query = query.filter((Student.full_name.ilike(f"%{search}%")) | (Student.roll_number.ilike(f"%{search}%")))
    if department_id:
        query = query.filter_by(department_id=department_id)
    return render_template("students.html", items=query.order_by(Student.full_name).all(),
                           departments=Department.query.all(), courses=Course.query.all())


@admin_bp.route("/students/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_student(item_id):
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.students"))
    item = db.session.get(Student, item_id)
    if item:
        db.session.delete(item)
        audit(current_user, "Student Deleted", f"Deleted student {item.full_name}")
        db.session.commit()
        flash("Student deleted.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/faculty", methods=["GET", "POST"])
@login_required
def faculty():
    if not management_allowed():
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if not admin_required():
            flash("Administrator access required.", "danger")
            return redirect(url_for("admin.faculty"))
        db.session.add(Faculty(employee_id=request.form["employee_id"].strip(),
                               full_name=request.form["full_name"].strip(), email=request.form["email"].strip(),
                               phone=request.form.get("phone"), department_id=request.form["department_id"],
                               designation=request.form.get("designation"), status=request.form.get("status", "Active")))
        audit(current_user, "Faculty Created", f"Created faculty {request.form['full_name']}")
        db.session.commit()
        flash("Faculty added.", "success")
        return redirect(url_for("admin.faculty"))
    search = request.args.get("q", "").strip()
    query = Faculty.query
    if search:
        query = query.filter(Faculty.full_name.ilike(f"%{search}%") | Faculty.employee_id.ilike(f"%{search}%"))
    items = query.order_by(Faculty.full_name).all()
    assigned_subjects = {
        item.id: ", ".join(subject.name for subject in Subject.query.filter_by(faculty_id=item.id).order_by(Subject.name).all())
        for item in items
    }
    return render_template("faculty.html", items=query.order_by(Faculty.full_name).all(),
                           departments=Department.query.all(), assigned_subjects=assigned_subjects)


@admin_bp.route("/faculty/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_faculty(item_id):
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.faculty"))
    item = db.session.get(Faculty, item_id)
    if item:
        db.session.delete(item)
        audit(current_user, "Faculty Deleted", f"Deleted faculty {item.full_name}")
        db.session.commit()
        flash("Faculty deleted.", "success")
    return redirect(url_for("admin.faculty"))


@admin_bp.route("/timetable", methods=["GET", "POST"])
@login_required
def timetable():
    if not management_allowed() and current_user.role not in ("faculty", "student"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if not admin_required():
            flash("Administrator access required.", "danger")
            return redirect(url_for("admin.timetable"))
        conflict = Timetable.query.filter(
            Timetable.day == request.form["day"],
            Timetable.start_time < request.form["end_time"],
            Timetable.end_time > request.form["start_time"],
            ((Timetable.faculty_id == int(request.form["faculty_id"])) |
             ((Timetable.course_id == int(request.form["course_id"])) &
              (Timetable.semester == int(request.form["semester"]))))
        ).first()
        if conflict:
            flash("This timetable slot conflicts with a faculty or class schedule.", "danger")
        else:
            db.session.add(Timetable(
                department_id=request.form["department_id"], course_id=request.form["course_id"],
                subject_id=request.form["subject_id"], faculty_id=request.form["faculty_id"],
                semester=int(request.form["semester"]), day=request.form["day"],
                start_time=request.form["start_time"], end_time=request.form["end_time"],
                room=request.form.get("room")))
            audit(current_user, "Timetable Created", "Created timetable entry")
            db.session.commit()
            flash("Timetable entry added.", "success")
        return redirect(url_for("admin.timetable"))
    entries_query = Timetable.query
    if current_user.role == "student":
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student:
            abort(403)
        entries_query = entries_query.filter_by(
            department_id=student.department_id,
            course_id=student.course_id,
            semester=student.semester,
        )
    return render_template("timetable.html",
        entries=entries_query.order_by(Timetable.day, Timetable.start_time).all(),
        departments=Department.query.all(), courses=Course.query.all(),
        subjects=Subject.query.all(), faculties=Faculty.query.all())


@admin_bp.route("/assignments", methods=["GET", "POST"])
@login_required
def assignments():
    if current_user.role == "faculty":
        return redirect(url_for("faculty.assignments"))
    if not management_allowed() and current_user.role != "student":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if not admin_required():
            return redirect(url_for("admin.dashboard"))
        assignment = Assignment(title=request.form["title"], description=request.form.get("description"),
                                subject_id=request.form["subject_id"], due_date=date.fromisoformat(request.form["due_date"]),
                                faculty_id=request.form.get("faculty_id") or None)
        db.session.add(assignment)
        db.session.flush()
        notify_cohort(assignment.subject, "New assignment", assignment.title, "Assignment")
        audit(current_user, "Assignment Created", f"Created assignment {request.form['title']}")
        db.session.commit()
        flash("Assignment added.", "success")
        return redirect(url_for("admin.assignments"))
    query = Assignment.query
    student = None
    submissions_by_assignment = {}
    if current_user.role == "student":
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student:
            query = query.filter(False)
        else:
            query = query.join(Subject).filter(
                Subject.department_id == student.department_id,
                Subject.course_id == student.course_id,
                Subject.semester == student.semester,
            )
    items = query.order_by(Assignment.due_date).all()
    if student:
        submissions_by_assignment = {
            submission.assignment_id: submission
            for submission in AssignmentSubmission.query.filter_by(student_id=student.id).all()
        }
    return render_template("assignments.html", items=items,
                           subjects=Subject.query.all(), faculties=Faculty.query.all(),
                           submissions_by_assignment=submissions_by_assignment)


@admin_bp.route("/assignments/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_assignment(item_id):
    item = db.session.get(Assignment, item_id)
    if not item:
        flash("Assignment not found.", "danger")
        return redirect(url_for("admin.assignments"))
    if not admin_required():
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
        if not faculty_member or (item.faculty_id != faculty_member.id and item.subject.faculty_id != faculty_member.id):
            flash("You are not allowed to delete this assignment.", "danger")
            return redirect(url_for("faculty.assignments"))
    if item:
        db.session.delete(item)
        audit(current_user, "Assignment Deleted", f"Deleted assignment {item.title}")
        db.session.commit()
        flash("Assignment deleted.", "success")
    return redirect(url_for("admin.assignments"))


@admin_bp.route("/assignments/<int:item_id>/submissions")
@login_required
def assignment_submissions(item_id):
    assignment = db.session.get(Assignment, item_id)
    if not assignment:
        abort(404)
    if not admin_required():
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
        if not faculty_member or (assignment.faculty_id != faculty_member.id and assignment.subject.faculty_id != faculty_member.id):
            abort(403)
    items = AssignmentSubmission.query.filter_by(assignment_id=assignment.id).order_by(
        AssignmentSubmission.submitted_at.desc()
    ).all()
    return render_template("submissions.html", assignment=assignment, items=items)


@admin_bp.route("/submissions/<int:item_id>/grade", methods=["POST"])
@login_required
def grade_submission(item_id):
    submission = db.session.get(AssignmentSubmission, item_id)
    if not submission:
        abort(404)
    assignment = submission.assignment
    if not admin_required():
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
        if not faculty_member or (assignment.faculty_id != faculty_member.id and assignment.subject.faculty_id != faculty_member.id):
            abort(403)
    try:
        grade = float(request.form.get("grade", ""))
    except ValueError:
        flash("Enter a valid grade between 0 and 100.", "danger")
        return redirect(url_for("admin.assignment_submissions", item_id=assignment.id))
    if not 0 <= grade <= 100:
        flash("Grade must be between 0 and 100.", "danger")
        return redirect(url_for("admin.assignment_submissions", item_id=assignment.id))
    submission.grade = grade
    submission.feedback = request.form.get("feedback", "").strip()
    notify_user(
        submission.student.user,
        "Assignment graded",
        f"{assignment.title}: {grade:g}/100. {submission.feedback}".strip(),
        "Assignment",
    )
    audit(current_user, "Assignment Graded", f"Graded {assignment.title} for {submission.student.full_name}")
    db.session.commit()
    flash("Submission grade saved.", "success")
    return redirect(url_for("admin.assignment_submissions", item_id=assignment.id))


@admin_bp.route("/submissions/<int:item_id>/download")
@login_required
def download_submission(item_id):
    submission = db.session.get(AssignmentSubmission, item_id)
    if not submission:
        abort(404)
    if current_user.role == "student":
        student = Student.query.filter_by(user_id=current_user.id).first()
        if not student or submission.student_id != student.id:
            abort(403)
    elif current_user.role == "faculty":
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first()
        assignment = submission.assignment
        if not faculty_member or (assignment.faculty_id != faculty_member.id and assignment.subject.faculty_id != faculty_member.id):
            abort(403)
    elif not admin_required():
        abort(403)
    return send_from_directory(
        os.path.join(current_app.config["UPLOAD_FOLDER"], "assignments"),
        submission.stored_name,
        as_attachment=True,
        download_name=submission.file_name,
    )


@admin_bp.route("/announcements", methods=["GET", "POST"])
@login_required
def announcements():
    if not management_allowed() and current_user.role not in ("student", "faculty"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if current_user.role not in ("admin", "faculty", "management"):
            flash("You are not allowed to publish announcements.", "danger")
            return redirect(url_for("admin.announcements"))
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
        subject_id = request.form.get("subject_id", type=int)
        subject = db.session.get(Subject, subject_id) if subject_id else None
        assigned_subject_ids = {
            item.id for item in Subject.query.filter_by(faculty_id=faculty_member.id).all()
        } if faculty_member else set()
        if current_user.role == "faculty" and (
            not subject or subject.id not in assigned_subject_ids
        ):
            flash("Select one of your assigned subjects.", "danger")
            return redirect(url_for("admin.announcements"))
        if subject_id and not subject:
            flash("Select a valid subject.", "danger")
            return redirect(url_for("admin.announcements"))
        try:
            publication_date = date.fromisoformat(
                request.form.get("publication_date") or date.today().isoformat()
            )
            expires_at = date.fromisoformat(request.form["expires_at"]) if request.form.get("expires_at") else None
        except ValueError:
            flash("Enter valid publication and expiry dates.", "danger")
            return redirect(url_for("admin.announcements"))
        if expires_at and expires_at < publication_date:
            flash("Expiry date cannot be before publication date.", "danger")
            return redirect(url_for("admin.announcements"))
        announcement = Announcement(
            title=request.form["title"].strip(),
            content=request.form["content"].strip(),
            category=request.form.get("category", "General"),
            important=bool(request.form.get("important")),
            publication_date=publication_date,
            expires_at=expires_at,
            subject_id=subject.id if subject else None,
            created_by=current_user.id,
        )
        db.session.add(announcement)
        if subject:
            notify_cohort(subject, f"Announcement: {announcement.title}", announcement.content, "Announcement")
        else:
            notify_active_users(f"Announcement: {announcement.title}", announcement.content, "Announcement")
        audit(current_user, "Announcement Created", f"Created announcement {request.form['title']}")
        db.session.commit()
        flash("Announcement published.", "success")
        return redirect(url_for("admin.announcements"))
    query = Announcement.query.filter(
        Announcement.publication_date <= date.today(),
        or_(Announcement.expires_at.is_(None), Announcement.expires_at >= date.today()),
    )
    subjects = []
    if current_user.role == "student":
        student = Student.query.filter_by(user_id=current_user.id).first()
        if student:
            subject_ids = [
                subject.id for subject in Subject.query.filter_by(
                    department_id=student.department_id, course_id=student.course_id,
                    semester=student.semester,
                ).all()
            ]
            query = query.filter(or_(Announcement.subject_id.is_(None), Announcement.subject_id.in_(subject_ids)))
        else:
            query = query.filter(Announcement.subject_id.is_(None))
    elif current_user.role == "faculty":
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first()
        subjects = Subject.query.filter_by(faculty_id=faculty_member.id).all() if faculty_member else []
        subject_ids = [subject.id for subject in subjects]
        query = query.filter(or_(Announcement.subject_id.is_(None), Announcement.subject_id.in_(subject_ids)))
    else:
        subjects = Subject.query.order_by(Subject.name).all()
    return render_template("announcements.html",
        items=query.order_by(Announcement.publication_date.desc()).all(), subjects=subjects, today=date.today())


@admin_bp.route("/announcements/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_announcement(item_id):
    item = db.session.get(Announcement, item_id)
    if not item:
        flash("Announcement not found.", "danger")
        return redirect(url_for("admin.announcements"))
    if current_user.role not in ("admin", "management"):
        faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
        if not faculty_member or item.subject_id not in {
            subject.id for subject in Subject.query.filter_by(faculty_id=faculty_member.id).all()
        }:
            flash("You are not allowed to delete this announcement.", "danger")
            return redirect(url_for("admin.announcements"))
    if item:
        db.session.delete(item)
        audit(current_user, "Announcement Deleted", f"Deleted announcement {item.title}")
        db.session.commit()
        flash("Announcement deleted.", "success")
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/audit")
@login_required
def audit_logs():
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.dashboard"))
    return render_template("audit.html", items=AuditLog.query.order_by(AuditLog.timestamp.desc()).all())


@admin_bp.route("/login-count")
@login_required
def login_count():
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.dashboard"))
    successful = LoginEvent.query.filter_by(succeeded=True)
    total_attempts = LoginEvent.query.count()
    successful_count = successful.count()
    failed_count = total_attempts - successful_count
    unique_count = db.session.query(func.count(func.distinct(LoginEvent.user_id))).filter(
        LoginEvent.succeeded.is_(True), LoginEvent.user_id.isnot(None)
    ).scalar() or 0
    role_counts = {}
    for role in ("student", "faculty", "admin", "management"):
        role_counts[role] = db.session.query(func.count(func.distinct(LoginEvent.user_id))).filter(
            LoginEvent.succeeded.is_(True), LoginEvent.role == role, LoginEvent.user_id.isnot(None)
        ).scalar() or 0

    start = date.today() - timedelta(days=13)
    daily_rows = db.session.query(
        func.date(LoginEvent.timestamp), func.count(LoginEvent.id)
    ).filter(
        LoginEvent.succeeded.is_(True),
        LoginEvent.timestamp >= datetime.combine(start, datetime.min.time()),
    ).group_by(func.date(LoginEvent.timestamp)).all()
    daily_counts = {day: count for day, count in daily_rows}
    daily_labels = [(start + timedelta(days=offset)).isoformat() for offset in range(14)]
    daily_values = [daily_counts.get(label, 0) for label in daily_labels]

    active_users = db.session.query(
        User,
        func.count(LoginEvent.id).label("login_total"),
        func.max(LoginEvent.timestamp).label("last_login"),
    ).join(LoginEvent, User.id == LoginEvent.user_id).filter(
        LoginEvent.succeeded.is_(True)
    ).group_by(User.id).order_by(func.count(LoginEvent.id).desc()).limit(10).all()
    history = LoginEvent.query.order_by(LoginEvent.timestamp.desc()).limit(50).all()
    return render_template(
        "login_count.html", login_count=unique_count, total_attempts=total_attempts,
        successful_count=successful_count, failed_count=failed_count,
        role_counts=role_counts, daily_labels=daily_labels, daily_values=daily_values,
        active_users=active_users, history=history,
    )


@admin_bp.route("/login-count/export.xlsx")
@login_required
def export_login_analytics():
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.dashboard"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Login History"
    sheet.append(["Timestamp", "Email", "Role", "Successful"])
    events = LoginEvent.query.order_by(LoginEvent.timestamp.desc()).all()
    for event in events:
        sheet.append([
            event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            event.attempted_email,
            event.role or "Unknown",
            "Yes" if event.succeeded else "No",
        ])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output, as_attachment=True, download_name="login_analytics.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@admin_bp.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(100).all()
    return render_template("notifications.html", items=items)


@admin_bp.route("/notifications/<int:item_id>/read", methods=["POST"])
@login_required
def mark_notification_read(item_id):
    item = Notification.query.filter_by(id=item_id, user_id=current_user.id).first()
    if item and item.read_at is None:
        item.read_at = datetime.utcnow()
        db.session.commit()
    return redirect(request.referrer or url_for("admin.notifications"))


@admin_bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@admin_bp.route("/students/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_student(item_id):
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.students"))
    item = db.session.get(Student, item_id)
    if not item:
        flash("Student not found.", "danger")
        return redirect(url_for("admin.students"))
    if request.method == "POST":
        roll = request.form["roll_number"].strip()
        duplicate = Student.query.filter(Student.roll_number == roll, Student.id != item.id).first()
        department = db.session.get(Department, request.form.get("department_id", type=int))
        course = db.session.get(Course, request.form.get("course_id", type=int))
        duplicate_email = Student.query.filter(
            Student.email == request.form.get("email", "").strip().lower(), Student.id != item.id
        ).first()
        if duplicate:
            flash("Duplicate roll number.", "danger")
        elif duplicate_email:
            flash("A student already uses this email address.", "danger")
        elif not department or not course or course.department_id != department.id:
            flash("Select a course that belongs to the selected department.", "danger")
        else:
            item.roll_number = roll
            item.full_name = request.form["full_name"].strip()
            item.email = request.form["email"].strip().lower()
            item.phone = request.form.get("phone")
            item.gender = request.form.get("gender")
            item.department_id = department.id
            item.course_id = course.id
            item.semester = int(request.form["semester"])
            item.admission_year = int(request.form["admission_year"])
            item.address = request.form.get("address")
            item.status = request.form.get("status", "Active")
            if request.form.get("date_of_birth"):
                item.date_of_birth = date.fromisoformat(request.form["date_of_birth"])
            audit(current_user, "Student Updated", f"Updated student {item.full_name}")
            db.session.commit()
            flash("Student updated.", "success")
            return redirect(url_for("admin.students"))
    return render_template("student_edit.html", item=item,
                           departments=Department.query.all(), courses=Course.query.all())


@admin_bp.route("/faculty/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_faculty(item_id):
    if not admin_required():
        flash("Administrator access required.", "danger")
        return redirect(url_for("admin.faculty"))
    item = db.session.get(Faculty, item_id)
    if not item:
        flash("Faculty member not found.", "danger")
        return redirect(url_for("admin.faculty"))
    if request.method == "POST":
        employee_id = request.form["employee_id"].strip()
        email = request.form["email"].strip().lower()
        department = db.session.get(Department, request.form.get("department_id", type=int))
        subject_ids = {int(value) for value in request.form.getlist("subject_ids") if value.isdigit()}
        selected_subjects = Subject.query.filter(
            Subject.id.in_(subject_ids), Subject.department_id == department.id if department else False
        ).all() if department else []
        if not department:
            flash("Select a valid department.", "danger")
            return redirect(url_for("admin.edit_faculty", item_id=item.id))
        if len(selected_subjects) != len(subject_ids):
            flash("Assigned subjects must belong to the selected department.", "danger")
            return redirect(url_for("admin.edit_faculty", item_id=item.id))
        if Faculty.query.filter(Faculty.employee_id == employee_id, Faculty.id != item.id).first():
            flash("Employee ID is already in use.", "danger")
            return redirect(url_for("admin.edit_faculty", item_id=item.id))
        if Faculty.query.filter(Faculty.email == email, Faculty.id != item.id).first():
            flash("Faculty email is already in use.", "danger")
            return redirect(url_for("admin.edit_faculty", item_id=item.id))
        item.employee_id = employee_id
        item.full_name = request.form["full_name"].strip()
        item.email = email
        item.phone = request.form.get("phone")
        item.department_id = department.id
        item.designation = request.form.get("designation")
        item.status = request.form.get("status", "Active")
        selected_subject_ids = {subject.id for subject in selected_subjects}
        for assigned_subject in Subject.query.filter_by(faculty_id=item.id).all():
            if assigned_subject.id not in selected_subject_ids:
                assigned_subject.faculty_id = None
        for subject in selected_subjects:
            subject.faculty_id = item.id
        audit(current_user, "Faculty Updated", f"Updated faculty {item.full_name}")
        db.session.commit()
        flash("Faculty updated.", "success")
        return redirect(url_for("admin.faculty"))
    return render_template("faculty_edit.html", item=item, departments=Department.query.all(),
                           subjects=Subject.query.order_by(Subject.name).all())
