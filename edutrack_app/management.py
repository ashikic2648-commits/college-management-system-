from io import BytesIO
from flask import Blueprint, render_template, redirect, url_for, flash, send_file, Response
from flask_login import login_required, current_user
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from .models import Student, Faculty, Department, Attendance, Mark, Subject
from .services import academic_risk_rows


management_bp = Blueprint("management", __name__, url_prefix="/management")


def read_only_allowed():
    return current_user.is_authenticated and current_user.role in ("admin", "management")


@management_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role not in ("admin", "management"):
        return redirect(url_for("admin.dashboard"))
    departments = Department.query.order_by(Department.name).all()
    department_stats = []
    for department in departments:
        students = Student.query.filter_by(department_id=department.id).filter(
            Student.user_id.isnot(None)
        ).count()
        faculty = Faculty.query.filter_by(department_id=department.id).count()
        records = Attendance.query.join(Student).filter(
            Student.department_id == department.id, Student.user_id.isnot(None)
        ).all()
        present = sum(record.status == "Present" for record in records)
        department_stats.append({
            "department": department,
            "students": students,
            "faculty": faculty,
            "attendance": round(present / len(records) * 100, 1) if records else 0,
        })
    marks = Mark.query.join(Student).filter(Student.user_id.isnot(None)).all()
    average_marks = round(sum(mark.percentage for mark in marks) / len(marks), 1) if marks else 0
    pass_percentage = round(sum(mark.grade != "F" for mark in marks) / len(marks) * 100, 1) if marks else 0
    risk_rows = academic_risk_rows()
    return render_template(
        "management_dashboard.html",
        student_count=Student.query.filter(Student.user_id.isnot(None)).count(),
        faculty_count=Faculty.query.count(),
        department_stats=department_stats,
        average_marks=average_marks,
        pass_percentage=pass_percentage,
        high_risk_count=sum(row["risk"] == "High Risk" for row in risk_rows),
    )


@management_bp.route("/academic-risk")
@login_required
def academic_risk():
    if current_user.role not in ("admin", "management", "faculty"):
        return redirect(url_for("admin.dashboard"))
    rows = academic_risk_rows()
    if current_user.role == "faculty":
        faculty = Faculty.query.filter_by(user_id=current_user.id).first()
        subjects = Subject.query.filter_by(faculty_id=faculty.id).all() if faculty else []
        cohorts = {(subject.department_id, subject.course_id, subject.semester) for subject in subjects}
        rows = [
            row for row in rows
            if (row["student"].department_id, row["student"].course_id, row["student"].semester) in cohorts
        ]
    return render_template("academic_risk.html", rows=rows)


@management_bp.route("/reports")
@login_required
def reports():
    if not read_only_allowed():
        return redirect(url_for("admin.dashboard"))
    departments = Department.query.all()
    rows = []
    for department in departments:
        student_count = Student.query.filter_by(department_id=department.id).filter(
            Student.user_id.isnot(None)
        ).count()
        faculty_count = Faculty.query.filter_by(department_id=department.id).count()
        attendance = Attendance.query.join(Student).filter(
            Student.department_id == department.id, Student.user_id.isnot(None)
        ).all()
        present = sum(row.status == "Present" for row in attendance)
        percentage = round(present / len(attendance) * 100, 1) if attendance else 0
        rows.append({"department": department, "students": student_count, "faculty": faculty_count,
                     "attendance": percentage})
    return render_template("reports.html", rows=rows)


@management_bp.route("/reports/students.pdf")
@login_required
def student_pdf():
    if not read_only_allowed():
        return redirect(url_for("admin.dashboard"))
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle("EduTrack Student Report")
    pdf.drawString(40, 800, "EduTrack - Student Report")
    y = 770
    for student in Student.query.filter(Student.user_id.isnot(None)).order_by(Student.roll_number).all():
        pdf.drawString(40, y, f"{student.roll_number} | {student.full_name} | {student.department.name if student.department else ''}")
        y -= 18
        if y < 40:
            pdf.showPage()
            y = 800
    pdf.save()
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="student_report.pdf", mimetype="application/pdf")


@management_bp.route("/reports/students.xlsx")
@login_required
def student_excel():
    if not read_only_allowed():
        return redirect(url_for("admin.dashboard"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Students"
    sheet.append(["Roll Number", "Name", "Email", "Department", "Course", "Semester", "Status"])
    for student in Student.query.filter(Student.user_id.isnot(None)).all():
        sheet.append([student.roll_number, student.full_name, student.email,
                      student.department.name if student.department else "",
                      student.course.name if student.course else "", student.semester, student.status])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True,
                     download_name="student_report.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
