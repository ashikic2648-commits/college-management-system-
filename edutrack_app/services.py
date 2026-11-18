from . import db
from .models import Attendance, Mark, Notification, Student, User


def notify_user(user, title, message, category):
    if user:
        notification = Notification.query.filter_by(
            user_id=user.id, title=title, category=category, read_at=None
        ).first()
        if notification:
            notification.message = message
        else:
            db.session.add(Notification(
                user_id=user.id,
                title=title,
                message=message,
                category=category,
            ))


def notify_cohort(subject, title, message, category):
    students = Student.query.filter_by(
        department_id=subject.department_id,
        course_id=subject.course_id,
        semester=subject.semester,
    ).filter(Student.user_id.isnot(None)).all()
    for student in students:
        notify_user(student.user, title, message, category)


def notify_active_users(title, message, category):
    for user in User.query.filter_by(active=True).all():
        notify_user(user, title, message, category)


def academic_risk_rows():
    attendance_by_student = {}
    for record in Attendance.query.join(Student).filter(Student.user_id.isnot(None)).all():
        counts = attendance_by_student.setdefault(record.student_id, [0, 0])
        counts[1] += 1
        counts[0] += record.status == "Present"

    marks_by_student = {}
    for mark in Mark.query.join(Student).filter(Student.user_id.isnot(None)).all():
        summary = marks_by_student.setdefault(mark.student_id, {"percentages": [], "failed_subjects": set()})
        summary["percentages"].append(mark.percentage)
        if mark.grade == "F":
            summary["failed_subjects"].add(mark.subject_id)

    rows = []
    for student in Student.query.filter(
        Student.user_id.isnot(None)
    ).order_by(Student.full_name).all():
        attendance_counts = attendance_by_student.get(student.id)
        attendance_percent = (
            round(attendance_counts[0] / attendance_counts[1] * 100, 1)
            if attendance_counts else None
        )
        mark_summary = marks_by_student.get(student.id)
        average_marks = (
            round(sum(mark_summary["percentages"]) / len(mark_summary["percentages"]), 1)
            if mark_summary and mark_summary["percentages"] else None
        )
        failed_subjects = len(mark_summary["failed_subjects"]) if mark_summary else 0
        if attendance_percent is None and average_marks is None:
            risk = "Insufficient data"
            action = "Collect attendance and assessment data."
        else:
            score = 0
            if attendance_percent is not None and attendance_percent < 75:
                score += 2
            if attendance_percent is not None and attendance_percent < 60:
                score += 1
            if average_marks is not None and average_marks < 50:
                score += 1
            if average_marks is not None and average_marks < 35:
                score += 1
            score += min(failed_subjects, 2)
            risk = "High Risk" if score >= 3 else ("Medium Risk" if score else "Low Risk")
            if attendance_percent is not None and attendance_percent < 75:
                action = "Schedule an attendance review and student support meeting."
            elif failed_subjects:
                action = "Arrange subject-specific academic support."
            elif average_marks is not None and average_marks < 50:
                action = "Review recent assessments and offer tutoring."
            else:
                action = "Continue routine academic monitoring."
        rows.append({
            "student": student,
            "attendance": attendance_percent,
            "average_marks": average_marks,
            "failed_subjects": failed_subjects,
            "risk": risk,
            "action": action,
        })
    risk_order = {"High Risk": 0, "Medium Risk": 1, "Low Risk": 2, "Insufficient data": 3}
    rows.sort(key=lambda row: (risk_order[row["risk"]], row["student"].full_name.lower()))
    return rows
