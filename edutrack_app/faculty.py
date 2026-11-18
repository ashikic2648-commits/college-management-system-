from datetime import date
import math
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from . import db
from .models import Faculty, Subject, Student, Attendance, Mark, Assignment, Timetable, audit
from .models import Notification
from .services import notify_cohort, notify_user


faculty_bp = Blueprint("faculty", __name__, url_prefix="/faculty")


def faculty_allowed():
    return current_user.is_authenticated and current_user.role in ("admin", "faculty")


def available_subjects():
    if current_user.role == "admin":
        return Subject.query.order_by(Subject.name).all()
    faculty = Faculty.query.filter_by(user_id=current_user.id).first()
    if not faculty:
        return []
    return Subject.query.filter_by(faculty_id=faculty.id).order_by(Subject.name).all()


def students_for_subject(subject):
    return Student.query.filter_by(
        department_id=subject.department_id,
        course_id=subject.course_id,
        semester=subject.semester,
    ).filter(Student.user_id.isnot(None)).order_by(Student.roll_number).all()


@faculty_bp.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if not faculty_allowed():
        flash("Faculty access required.", "danger")
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        try:
            subject_id = int(request.form["subject_id"])
            attendance_date = date.fromisoformat(request.form["date"])
        except (KeyError, ValueError):
            flash("Select a valid subject and attendance date.", "danger")
            return redirect(url_for("faculty.attendance"))
        subject = next((item for item in available_subjects() if item.id == subject_id), None)
        if not subject:
            flash("You are not assigned to that subject.", "danger")
            return redirect(url_for("faculty.attendance"))

        eligible = {student.id for student in students_for_subject(subject)}
        updates = []
        for key, status in request.form.items():
            if not key.startswith("student_"):
                continue
            try:
                student_id = int(key.split("_", 1)[1])
            except ValueError:
                flash("Invalid student record.", "danger")
                return redirect(url_for("faculty.attendance"))
            if student_id not in eligible or status not in ("Present", "Absent", "Leave"):
                flash("Attendance contains an invalid student or status.", "danger")
                return redirect(url_for("faculty.attendance"))
            updates.append((student_id, status))

        if not updates:
            flash("No attendance records were submitted.", "warning")
            return redirect(url_for("faculty.attendance", subject=subject_id, date=attendance_date.isoformat()))

        for student_id, status in updates:
            row = Attendance.query.filter_by(student_id=student_id, subject_id=subject_id, date=attendance_date).first()
            if row:
                row.status = status
            else:
                db.session.add(Attendance(student_id=student_id, subject_id=subject_id,
                                          date=attendance_date, status=status))
        for student_id, _ in updates:
            student = db.session.get(Student, student_id)
            if not student.user_id:
                continue
            student_records = Attendance.query.filter_by(
                student_id=student_id, subject_id=subject_id
            ).all()
            present = sum(record.status == "Present" for record in student_records)
            percentage = present / len(student_records) * 100 if student_records else 100
            if percentage < 75:
                notify_user(
                    student.user,
                    "Attendance below 75%",
                    f"Your attendance is {percentage:.1f}%. Please contact your faculty adviser.",
                    "Attendance",
                )
        count = len(updates)
        audit(current_user, "Attendance Updated", f"Updated {count} attendance records")
        db.session.commit()
        flash("Attendance saved.", "success")
        return redirect(url_for("faculty.attendance", subject=subject_id, date=attendance_date.isoformat()))
    subjects = available_subjects()
    selected_subject = request.args.get("subject")
    selected_date = request.args.get("date", date.today().isoformat())
    students = []
    records = {}
    if selected_subject:
        try:
            subject_id = int(selected_subject)
            selected_day = date.fromisoformat(selected_date)
        except ValueError:
            flash("Select a valid subject and date.", "danger")
            selected_subject = None
        else:
            subject = next((item for item in subjects if item.id == subject_id), None)
            if not subject:
                flash("You are not assigned to that subject.", "danger")
                selected_subject = None
            else:
                students = students_for_subject(subject)
                for row in Attendance.query.filter_by(subject_id=subject_id, date=selected_day).all():
                    records[row.student_id] = row.status
    return render_template("attendance.html", subjects=subjects, students=students, records=records,
                           selected_subject=selected_subject, selected_date=selected_date)


@faculty_bp.route("/marks", methods=["GET", "POST"])
@login_required
def marks():
    if not faculty_allowed():
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        try:
            subject_id = int(request.form["subject_id"])
            max_marks = float(request.form.get("max_marks", "100"))
        except (KeyError, ValueError):
            flash("Select a valid subject and maximum mark.", "danger")
            return redirect(url_for("faculty.marks"))
        examination = request.form.get("examination", "").strip()
        subject = next((item for item in available_subjects() if item.id == subject_id), None)
        if not subject or not examination or len(examination) > 50 or not math.isfinite(max_marks) or max_marks <= 0:
            flash("Enter a valid assigned subject, examination name, and maximum mark.", "danger")
            return redirect(url_for("faculty.marks"))

        eligible = {student.id for student in students_for_subject(subject)}
        updates = []
        for key, value in request.form.items():
            if not key.startswith("marks_") or not value:
                continue
            try:
                student_id = int(key.split("_", 1)[1])
                obtained_marks = float(value)
            except ValueError:
                flash("Marks must be valid numbers.", "danger")
                return redirect(url_for("faculty.marks"))
            if (student_id not in eligible or not math.isfinite(obtained_marks)
                    or obtained_marks < 0 or obtained_marks > max_marks):
                flash("Marks exceed the allowed range or include an invalid student.", "danger")
                return redirect(url_for("faculty.marks"))
            updates.append((student_id, obtained_marks))

        if not updates:
            flash("Enter marks for at least one student before saving.", "warning")
            return redirect(url_for("faculty.marks", subject=subject_id, examination=examination))

        for student_id, obtained_marks in updates:
            row = Mark.query.filter_by(student_id=student_id, subject_id=subject_id, examination=examination).first()
            if row:
                row.obtained_marks = obtained_marks
                row.max_marks = max_marks
            else:
                db.session.add(Mark(student_id=student_id, subject_id=subject_id, examination=examination,
                                    obtained_marks=obtained_marks, max_marks=max_marks))
            student = db.session.get(Student, student_id)
            notify_user(student.user, f"Marks published: {examination}", subject.name, "Results")
        audit(current_user, "Marks Updated", "Updated examination marks")
        db.session.commit()
        flash("Marks saved.", "success")
        return redirect(url_for("faculty.marks", subject=subject_id, examination=examination))
    subjects = available_subjects()
    selected_subject = request.args.get("subject")
    examination = request.args.get("examination", "Internal 1").strip() or "Internal 1"
    students = []
    marks_by_student = {}
    examination_max_marks = 100
    if selected_subject:
        try:
            subject_id = int(selected_subject)
        except ValueError:
            flash("Select a valid subject.", "danger")
            selected_subject = None
        else:
            subject = next((item for item in subjects if item.id == subject_id), None)
            if not subject:
                flash("You are not assigned to that subject.", "danger")
                selected_subject = None
            else:
                students = students_for_subject(subject)
                for mark in Mark.query.filter_by(subject_id=subject_id, examination=examination).all():
                    marks_by_student[mark.student_id] = mark
                    examination_max_marks = mark.max_marks
    return render_template("marks.html", subjects=subjects, students=students,
                           selected_subject=selected_subject, marks_by_student=marks_by_student,
                           examination=examination, examination_max_marks=examination_max_marks)


@faculty_bp.route("/timetable")
@login_required
def timetable():
    if not faculty_allowed():
        return redirect(url_for("admin.dashboard"))
    query = Timetable.query
    if current_user.role == "faculty":
        faculty = Faculty.query.filter_by(user_id=current_user.id).first()
        query = query.filter_by(faculty_id=faculty.id) if faculty else query.filter(False)
    entries = query.order_by(Timetable.day, Timetable.start_time).all()
    return render_template("timetable.html", entries=entries)


@faculty_bp.route("/assignments", methods=["GET", "POST"])
@login_required
def assignments():
    if not faculty_allowed():
        return redirect(url_for("admin.dashboard"))
    faculty_member = Faculty.query.filter_by(user_id=current_user.id).first() if current_user.role == "faculty" else None
    subjects = available_subjects()
    if request.method == "POST":
        subject_id = request.form.get("subject_id", type=int)
        if not any(subject.id == subject_id for subject in subjects):
            flash("You are not assigned to that subject.", "danger")
            return redirect(url_for("faculty.assignments"))
        assignment = Assignment(title=request.form["title"], description=request.form.get("description"),
                                subject_id=subject_id, due_date=date.fromisoformat(request.form["due_date"]),
                                faculty_id=faculty_member.id if faculty_member else request.form.get("faculty_id") or None)
        db.session.add(assignment)
        db.session.flush()
        notify_cohort(assignment.subject, "New assignment", assignment.title, "Assignment")
        audit(current_user, "Assignment Created", f"Created assignment {request.form['title']}")
        db.session.commit()
        flash("Assignment added.", "success")
        return redirect(url_for("faculty.assignments"))
    query = Assignment.query
    if current_user.role == "faculty":
        query = query.join(Subject).filter(
            or_(Assignment.faculty_id == faculty_member.id, Subject.faculty_id == faculty_member.id)
        ) if faculty_member else query.filter(False)
    return render_template("assignments.html", items=query.order_by(Assignment.due_date).all(),
                           subjects=subjects)
