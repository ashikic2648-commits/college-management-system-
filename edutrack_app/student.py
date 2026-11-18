from datetime import date, datetime
import os
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from . import db
from .models import Student, Faculty, Attendance, Mark, Assignment, AssignmentSubmission, Announcement, Subject
from .services import notify_user


student_bp = Blueprint("student", __name__, url_prefix="/student")
ALLOWED_ASSIGNMENT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "png", "jpg", "jpeg"}
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def can_view_student(student):
    if not student.user_id:
        return False
    if current_user.role in ("admin", "management"):
        return True
    if current_user.role == "student":
        return student.user_id == current_user.id
    if current_user.role != "faculty":
        return False
    faculty_member = Faculty.query.filter_by(user_id=current_user.id).first()
    if not faculty_member:
        return False
    return Subject.query.filter_by(
        faculty_id=faculty_member.id,
        department_id=student.department_id,
        course_id=student.course_id,
        semester=student.semester,
    ).first() is not None


def student_mark_data(student):
    marks = Mark.query.filter_by(student_id=student.id).order_by(
        Mark.subject_id, Mark.examination
    ).all()
    marks_by_subject = {}
    for mark in marks:
        group = marks_by_subject.setdefault(mark.subject_id, {
            "subject": mark.subject.name,
            "percentages": [],
        })
        group["percentages"].append(mark.percentage)
    subject_mark_summary = [
        {
            "subject": group["subject"],
            "assessments": len(group["percentages"]),
            "average": round(sum(group["percentages"]) / len(group["percentages"]), 1),
        }
        for group in marks_by_subject.values()
    ]
    for row in subject_mark_summary:
        row["result"] = "Pass" if row["average"] >= 50 else "Fail"
    overall_mark_average = (
        round(sum(mark.percentage for mark in marks) / len(marks), 1) if marks else None
    )
    return marks, subject_mark_summary, overall_mark_average


@student_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if current_user.role != "student":
        return redirect(url_for("admin.dashboard"))
    student = Student.query.filter_by(user_id=current_user.id).first()
    if not student:
        flash("No student profile is linked to this account.", "warning")
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        if len(phone) > 20:
            flash("Phone number must be 20 characters or fewer.", "danger")
            return redirect(url_for("student.profile"))

        upload = request.files.get("photo")
        old_photo = student.photo_filename
        if upload and upload.filename:
            original_name = secure_filename(upload.filename)
            extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
            if not original_name or extension not in ALLOWED_PROFILE_IMAGE_EXTENSIONS:
                flash("Choose a PNG, JPG, or WEBP profile image.", "danger")
                return redirect(url_for("student.profile"))
            header = upload.stream.read(12)
            upload.stream.seek(0)
            valid_image = (
                extension == "png" and header.startswith(b"\x89PNG\r\n\x1a\n")
            ) or (
                extension in ("jpg", "jpeg") and header.startswith(b"\xff\xd8\xff")
            ) or (
                extension == "webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
            )
            if not valid_image:
                flash("The selected file is not a valid PNG, JPG, or WEBP image.", "danger")
                return redirect(url_for("student.profile"))
            folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "student_profiles")
            os.makedirs(folder, exist_ok=True)
            photo_filename = f"{uuid.uuid4().hex}.{extension}"
            upload.save(os.path.join(folder, photo_filename))
            student.photo_filename = photo_filename

        student.phone = phone or None
        db.session.commit()
        if old_photo and old_photo != student.photo_filename:
            old_path = os.path.join(current_app.config["UPLOAD_FOLDER"], "student_profiles", old_photo)
            if os.path.isfile(old_path):
                os.remove(old_path)
        flash("Profile updated.", "success")
        return redirect(url_for("student.profile"))

    attendance = Attendance.query.filter_by(student_id=student.id).all()
    present = sum(row.status == "Present" for row in attendance)
    percentage = round(present / len(attendance) * 100, 1) if attendance else 0
    attendance_groups = {}
    for row in attendance:
        group = attendance_groups.setdefault(row.subject_id, {
            "subject": row.subject.name,
            "present": 0,
            "total": 0,
            "records": [],
        })
        group["present"] += row.status == "Present"
        group["total"] += 1
        group["records"].append(row)
    attendance_summary = [
        {
            **group,
            "percentage": round(group["present"] / group["total"] * 100, 1),
        }
        for group in attendance_groups.values()
    ]
    selected_month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m").date().replace(day=1)
        if month_start.strftime("%Y-%m") != selected_month:
            raise ValueError
    except ValueError:
        flash("Choose a valid month for the attendance report.", "warning")
        selected_month = date.today().strftime("%Y-%m")
        month_start = date.today().replace(day=1)
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    monthly_records = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date >= month_start,
        Attendance.date < next_month,
    ).order_by(Attendance.date.desc(), Attendance.subject_id).all()
    monthly_groups = {}
    for record in monthly_records:
        group = monthly_groups.setdefault(record.subject_id, {
            "subject": record.subject.name,
            "present": 0,
            "total": 0,
        })
        group["present"] += record.status == "Present"
        group["total"] += 1
    monthly_attendance_summary = [
        {
            **group,
            "percentage": round(group["present"] / group["total"] * 100, 1),
        }
        for group in monthly_groups.values()
    ]
    marks, subject_mark_summary, overall_mark_average = student_mark_data(student)
    assignments = Assignment.query.join(Subject).filter(
        Subject.department_id == student.department_id,
        Subject.course_id == student.course_id,
        Subject.semester == student.semester,
    ).order_by(Assignment.due_date).all()
    subject_ids = [
        subject.id for subject in Subject.query.filter_by(
            department_id=student.department_id, course_id=student.course_id,
            semester=student.semester,
        ).all()
    ]
    announcements = Announcement.query.filter(
        Announcement.publication_date <= date.today(),
        or_(Announcement.subject_id.is_(None), Announcement.subject_id.in_(subject_ids)),
        or_(Announcement.expires_at.is_(None), Announcement.expires_at >= date.today()),
    ).order_by(Announcement.publication_date.desc()).all()
    return render_template("student_profile.html", student=student, attendance_percentage=percentage,
                           attendance_summary=attendance_summary, marks=marks,
                           subject_mark_summary=subject_mark_summary,
                           overall_mark_average=overall_mark_average,
                           selected_month=selected_month,
                           monthly_attendance_summary=monthly_attendance_summary,
                           monthly_records=monthly_records,
                           assignments=assignments, announcements=announcements)


@student_bp.route("/profile/<int:student_id>")
@login_required
def view_profile(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    if not can_view_student(student):
        abort(403)
    attendance = Attendance.query.filter_by(student_id=student.id).all()
    present = sum(row.status == "Present" for row in attendance)
    attendance_percentage = round(present / len(attendance) * 100, 1) if attendance else 0
    marks, _, overall_mark_average = student_mark_data(student)
    return render_template(
        "student_view_profile.html",
        student=student,
        attendance_percentage=attendance_percentage,
        marks_count=len(marks),
        overall_mark_average=overall_mark_average,
    )


@student_bp.route("/marks", defaults={"student_id": None})
@student_bp.route("/marks/<int:student_id>")
@login_required
def student_marks(student_id):
    if student_id is None:
        if current_user.role != "student":
            abort(403)
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    else:
        student = db.session.get(Student, student_id)
        if not student:
            abort(404)
    if not can_view_student(student):
        abort(403)
    marks, subject_mark_summary, overall_mark_average = student_mark_data(student)
    return render_template(
        "student_marks.html",
        student=student,
        marks=marks,
        subject_mark_summary=subject_mark_summary,
        overall_mark_average=overall_mark_average,
        own_profile=student.user_id == current_user.id,
    )


@student_bp.route("/photo/<int:student_id>")
@login_required
def profile_photo(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    if not can_view_student(student):
        abort(403)
    if not student.photo_filename:
        abort(404)
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "student_profiles")
    response = send_from_directory(folder, student.photo_filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@student_bp.route("/assignments/<int:assignment_id>/submit", methods=["POST"])
@login_required
def submit_assignment(assignment_id):
    if current_user.role != "student":
        flash("Student access required.", "danger")
        return redirect(url_for("admin.assignments"))
    student = Student.query.filter_by(user_id=current_user.id).first()
    assignment = db.session.get(Assignment, assignment_id)
    if not student or not assignment or (
        assignment.subject.department_id != student.department_id
        or assignment.subject.course_id != student.course_id
        or assignment.subject.semester != student.semester
    ):
        flash("Assignment not found for your class.", "danger")
        return redirect(url_for("admin.assignments"))

    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a file to submit.", "danger")
        return redirect(url_for("admin.assignments"))
    filename = secure_filename(upload.filename)
    if not filename or "." not in filename:
        flash("Invalid file name.", "danger")
        return redirect(url_for("admin.assignments"))
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_ASSIGNMENT_EXTENSIONS:
        flash("Unsupported file type. Upload a document, spreadsheet, presentation, image, or PDF.", "danger")
        return redirect(url_for("admin.assignments"))

    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "assignments")
    os.makedirs(folder, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    upload.save(os.path.join(folder, stored_name))

    submission = AssignmentSubmission.query.filter_by(
        assignment_id=assignment.id, student_id=student.id
    ).first()
    old_path = None
    if submission:
        old_path = os.path.join(folder, submission.stored_name)
        submission.file_name = filename
        submission.stored_name = stored_name
        submission.submitted_at = datetime.utcnow()
        submission.grade = None
        submission.feedback = None
    else:
        submission = AssignmentSubmission(
            assignment_id=assignment.id,
            student_id=student.id,
            file_name=filename,
            stored_name=stored_name,
        )
        db.session.add(submission)
    faculty_member = assignment.faculty or assignment.subject.faculty
    if faculty_member and faculty_member.user:
        notify_user(
            faculty_member.user,
            "Assignment submitted",
            f"{student.full_name} submitted {assignment.title}.",
            "Assignment",
        )
    db.session.commit()
    if old_path and os.path.isfile(old_path):
        os.remove(old_path)
    flash("Assignment submitted successfully.", "success")
    return redirect(url_for("admin.assignments"))
