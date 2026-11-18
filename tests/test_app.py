import io
import os
import unittest
import uuid
from datetime import date
from edutrack_app import create_app, db
from edutrack_app.models import (
    User, Student, Faculty, Department, Course, Subject, Attendance, Mark,
    Announcement, Notification,
    Assignment, AssignmentSubmission, Timetable,
)


class EduTrackTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

    def test_login_page(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome back", response.data)

    def test_demo_login_and_logout(self):
        with self.client as client:
            client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            client.get("/logout")

    def test_role_permission(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/departments")
        self.assertIn(response.status_code, (302, 403))

    def test_student_signup(self):
        email = f"new.student.{uuid.uuid4().hex}@example.com"
        with self.app.app_context():
            department = Department.query.first()
            course = Course.query.filter_by(department_id=department.id).first()
            department_id = department.id
            course_id = course.id
        response = self.client.post("/signup", data={
            "name": "New Student",
            "email": email,
            "password": "MyPassword123!",
            "confirm_password": "MyPassword123!",
            "department_id": department_id,
            "course_id": course_id,
        })
        self.assertEqual(response.status_code, 302, response.location)
        with self.app.app_context():
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "student")
            self.assertTrue(user.check_password("MyPassword123!"))
            self.assertIsNotNone(Student.query.filter_by(user_id=user.id).first())

    def test_public_signup_creates_student_record_shown_in_student_list(self):
        email = f"new.student.{uuid.uuid4().hex}@example.com"
        name = "New List Student"
        with self.app.app_context():
            department = Department.query.first()
            course = Course.query.filter_by(department_id=department.id).first()
            department_id, course_id = department.id, course.id
        response = self.client.post("/signup", data={
            "name": name,
            "email": email,
            "password": "MyPassword123!",
            "confirm_password": "MyPassword123!",
            "role": "admin",
            "department_id": department_id,
            "course_id": course_id,
        })
        self.assertEqual(response.status_code, 302, response.location)
        with self.app.app_context():
            user = User.query.filter_by(email=email).one()
            self.assertEqual(user.role, "student")
            student = Student.query.filter_by(user_id=user.id).one()
            self.assertEqual(student.full_name, name)
        self.client.get("/logout")
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get(f"/students?q={name.replace(' ', '+')}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(name.encode(), response.data)

    def test_demo_database_has_records(self):
        with self.app.app_context():
            self.assertGreater(User.query.count(), 0)
            self.assertGreater(Student.query.count(), 0)
            self.assertGreater(Department.query.count(), 0)

    def test_mark_calculation(self):
        with self.app.app_context():
            mark = Mark.query.first()
            if mark:
                self.assertGreaterEqual(mark.percentage, 0)
                self.assertIn(mark.grade, ("A+", "A", "B", "C", "D", "F"))

    def test_admin_can_record_attendance_and_marks(self):
        with self.app.app_context():
            subject = Subject.query.first()
            test_user = User(
                name="Temporary Test Student",
                email=f"{uuid.uuid4().hex}@example.com",
                role="student",
            )
            test_user.set_password("TestPassword123!")
            db.session.add(test_user)
            db.session.flush()
            student = Student(
                user_id=test_user.id,
                roll_number=f"TEST{uuid.uuid4().hex[:12]}",
                full_name="Temporary Test Student",
                email=test_user.email,
                department_id=subject.department_id,
                course_id=subject.course_id,
                semester=subject.semester,
                admission_year=2026,
            )
            db.session.add(student)
            db.session.commit()
            subject_id, student_id = subject.id, student.id
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        attendance_date = "2026-11-18"
        self.client.post("/faculty/attendance", data={
            "subject_id": subject_id,
            "date": attendance_date,
            f"student_{student_id}": "Present",
        })
        self.client.post("/faculty/marks", data={
            "subject_id": subject_id,
            "examination": "Test 1",
            "max_marks": "50",
            f"marks_{student_id}": "42",
        })
        with self.app.app_context():
            attendance = Attendance.query.filter_by(
                student_id=student_id, subject_id=subject_id, date=date(2026, 11, 18)
            ).first()
            mark = Mark.query.filter_by(
                student_id=student_id, subject_id=subject_id, examination="Test 1"
            ).first()
            self.assertEqual(attendance.status, "Present")
            self.assertEqual(mark.obtained_marks, 42)
            self.assertEqual(mark.max_marks, 50)
            db.session.delete(attendance)
            db.session.delete(mark)
            db.session.delete(db.session.get(Student, student_id))
            test_user = User.query.filter_by(name="Temporary Test Student").one()
            Notification.query.filter_by(user_id=test_user.id).delete()
            db.session.delete(test_user)
            db.session.commit()

    def test_admin_can_assign_faculty_department_and_subject(self):
        with self.app.app_context():
            faculty = Faculty.query.first()
            subject = Subject.query.filter_by(department_id=faculty.department_id).first()
            faculty_id, subject_id = faculty.id, subject.id
            previous_faculty_id = subject.faculty_id
            previous_subject_ids = [
                assigned.id for assigned in Subject.query.filter_by(faculty_id=faculty_id).all()
            ]
            form = {
                "employee_id": faculty.employee_id,
                "full_name": faculty.full_name,
                "email": faculty.email,
                "department_id": faculty.department_id,
                "subject_ids": [str(subject_id)],
            }
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post(f"/faculty/{faculty_id}/edit", data=form)
        self.assertEqual(response.status_code, 302, response.location)
        with self.app.app_context():
            self.assertEqual(db.session.get(Subject, subject_id).faculty_id, faculty_id)
            for assigned in Subject.query.filter_by(faculty_id=faculty_id).all():
                assigned.faculty_id = None
            for assigned_id in previous_subject_ids:
                db.session.get(Subject, assigned_id).faculty_id = faculty_id
            db.session.get(Subject, subject_id).faculty_id = previous_faculty_id
            db.session.commit()

    def test_faculty_is_limited_to_assigned_subjects(self):
        with self.app.app_context():
            faculty_user = User.query.filter_by(role="faculty").first()
            assigned_subject = Subject.query.filter_by(faculty_id=Faculty.query.filter_by(user_id=faculty_user.id).first().id).first()
            other_subject = Subject.query.filter(Subject.faculty_id != Faculty.query.filter_by(user_id=faculty_user.id).first().id).first()
            assigned_subject_id = assigned_subject.id
            other_subject_id = other_subject.id
        self.client.post("/login", data={"email": "faculty@edutrack.com", "password": "EduTrack123!"})
        page = self.client.get(f"/faculty/marks?subject={assigned_subject_id}")
        self.assertEqual(page.status_code, 200)
        denied = self.client.get(f"/faculty/marks?subject={other_subject_id}")
        self.assertEqual(denied.status_code, 200)
        self.assertIn(b"You are not assigned to that subject.", denied.data)

    def test_student_profile_shows_roll_and_attendance_summary(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/student/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My Profile", response.data)
        self.assertNotIn(b"Monday \xc2\xb7 9:00\xe2\x80\x9310:00", response.data)
        self.assertIn(b"Attendance by subject", response.data)
        self.assertIn(b"ET0001", response.data)
        self.assertIn(b"Phone number", response.data)
        self.assertIn(b"Class", response.data)
        self.assertIn(b"Marks & Results", response.data)
        self.assertNotIn(b"Examination Marks", response.data)
        self.assertIn(b"Average mark score", response.data)
        self.assertIn(b"57.0%", response.data)
        marks_page = self.client.get("/student/marks")
        self.assertEqual(marks_page.status_code, 200)
        self.assertIn(b"Subject performance", marks_page.data)
        self.assertIn(b"Pass", marks_page.data)

    def test_student_timetable_is_a_separate_page_limited_to_their_class(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/timetable")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Weekly Timetable", response.data)
        self.assertIn(b"Data Structures", response.data)
        self.assertNotIn(b"Database Systems", response.data)
        self.assertNotIn(b"Business Management", response.data)

    def test_student_navigation_opens_each_section_in_a_new_tab(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/student/profile")
        for href in (
            b'href="/" target="_blank" rel="noopener"',
            b'href="/student/profile" target="_blank" rel="noopener"',
            b'href="/student/marks" target="_blank" rel="noopener"',
            b'href="/timetable" target="_blank" rel="noopener"',
            b'href="/assignments" target="_blank" rel="noopener"',
            b'href="/announcements" target="_blank" rel="noopener"',
        ):
            self.assertIn(href, response.data)

    def test_student_profile_and_marks_visibility_is_role_scoped(self):
        with self.app.app_context():
            student = Student.query.filter_by(
                user_id=User.query.filter_by(email="student@edutrack.com").first().id
            ).one()
            non_login_student = Student.query.filter(Student.user_id.is_(None)).first()
            student_id, non_login_student_id = student.id, non_login_student.id
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        own_profile = self.client.get(f"/student/profile/{student_id}")
        self.assertEqual(own_profile.status_code, 200)
        self.assertEqual(self.client.get("/student/marks").status_code, 200)
        self.assertEqual(self.client.get(f"/student/profile/{non_login_student_id}").status_code, 403)
        self.assertEqual(self.client.get(f"/student/marks/{non_login_student_id}").status_code, 403)

        self.client.get("/logout")
        self.client.post("/login", data={"email": "faculty@edutrack.com", "password": "EduTrack123!"})
        self.assertEqual(self.client.get(f"/student/profile/{student_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/student/marks/{student_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/student/profile/{non_login_student_id}").status_code, 403)

    def test_student_can_filter_monthly_attendance(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        month = date.today().strftime("%Y-%m")
        response = self.client.get(f"/student/profile?month={month}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Monthly attendance", response.data)
        self.assertIn(b"Attendance records", response.data)
        self.assertIn(month.encode(), response.data)

    def test_student_can_upload_and_view_profile_photo(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post(
            "/student/profile",
            data={
                "phone": "+1 555 0100",
                "photo": (io.BytesIO(b"\xff\xd8\xfftest-image"), "profile.jpg"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            student = Student.query.filter_by(
                user_id=User.query.filter_by(email="student@edutrack.com").first().id
            ).one()
            self.assertEqual(student.phone, "+1 555 0100")
            self.assertTrue(student.photo_filename.endswith(".jpg"))
            stored_path = os.path.join(
                self.app.config["UPLOAD_FOLDER"], "student_profiles", student.photo_filename
            )
            photo_url = f"/student/photo/{student.id}"
        self.assertTrue(os.path.isfile(stored_path))
        photo_response = self.client.get(photo_url)
        self.assertEqual(photo_response.status_code, 200)
        self.assertIn(b"\xff\xd8\xff", photo_response.data)
        photo_response.close()
        os.remove(stored_path)

    def test_attendance_shortage_uses_selected_subject_not_other_subjects(self):
        with self.app.app_context():
            student = Student.query.filter_by(
                user_id=User.query.filter_by(email="student@edutrack.com").first().id
            ).one()
            subject = Subject.query.filter_by(
                department_id=student.department_id, course_id=student.course_id,
                semester=student.semester,
            ).one()
            other_subject = Subject.query.filter(Subject.id != subject.id).first()
            student_id, subject_id = student.id, subject.id
            for offset in range(20):
                db.session.add(Attendance(
                    student_id=student.id,
                    subject_id=other_subject.id,
                    date=date.fromordinal(date.today().toordinal() - offset),
                    status="Absent",
                ))
            db.session.commit()
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post("/faculty/attendance", data={
            "subject_id": subject_id,
            "date": date.today().isoformat(),
            f"student_{student_id}": "Present",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                Notification.query.filter_by(
                    user_id=User.query.filter_by(email="student@edutrack.com").first().id,
                    title="Attendance below 75%",
                ).count(),
                0,
            )

    def test_empty_assessment_submission_is_not_reported_as_saved(self):
        with self.app.app_context():
            subject_id = Subject.query.first().id
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post("/faculty/marks", data={
            "subject_id": subject_id,
            "examination": "Empty assessment",
            "max_marks": "100",
        }, follow_redirects=True)
        self.assertIn(b"Enter marks for at least one student before saving.", response.data)

    def test_academic_rosters_only_show_students_with_login_accounts(self):
        with self.app.app_context():
            student = Student.query.filter(
                Student.user_id.isnot(None)
            ).order_by(Student.roll_number).first()
            subject = Subject.query.filter_by(
                department_id=student.department_id,
                course_id=student.course_id,
                semester=student.semester,
            ).first()
            subject_id = subject.id
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        directory = self.client.get("/students")
        self.assertIn(b"Student 1", directory.data)
        self.assertNotIn(b"Student 2", directory.data)
        marks_page = self.client.get(f"/faculty/marks?subject={subject_id}")
        self.assertEqual(marks_page.status_code, 200)
        self.assertIn(b"Student 1", marks_page.data)
        self.assertIn(b"Pass", marks_page.data)
        self.assertNotIn(b"Student 7", marks_page.data)

    def test_subject_summary_marks_failed_average_as_fail(self):
        with self.app.app_context():
            student = Student.query.filter_by(
                user_id=User.query.filter_by(email="student@edutrack.com").first().id
            ).one()
            subject = Subject.query.filter_by(
                department_id=student.department_id, course_id=student.course_id,
                semester=student.semester,
            ).first()
            failing_mark = Mark(
                student_id=student.id,
                subject_id=subject.id,
                examination="Low assessment",
                obtained_marks=40,
                max_marks=100,
            )
            db.session.add(failing_mark)
            db.session.commit()
            failing_mark_id = failing_mark.id
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/student/marks")
        self.assertIn(b"Fail", response.data)
        with self.app.app_context():
            db.session.delete(db.session.get(Mark, failing_mark_id))
            db.session.commit()

    def test_admin_login_count_counts_distinct_users(self):
        client = self.app.test_client()
        client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        client.get("/logout")
        client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        with client:
            response = client.get("/login-count")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Unique users logged in", response.data)
        self.assertIn(b">1<", response.data)

    def test_login_count_is_admin_only(self):
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/login-count")
        self.assertEqual(response.status_code, 302)

    def test_subject_announcement_notifies_only_its_cohort(self):
        with self.app.app_context():
            student = Student.query.filter_by(user_id=User.query.filter_by(email="student@edutrack.com").first().id).first()
            subject = Subject.query.filter_by(
                department_id=student.department_id, course_id=student.course_id,
                semester=student.semester,
            ).first()
            subject_id = subject.id
            cohort_user_ids = {
                row.user_id for row in Student.query.filter_by(
                    department_id=student.department_id, course_id=student.course_id,
                    semester=student.semester,
                ).all() if row.user_id
            }
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post("/announcements", data={
            "title": "Cohort notice",
            "content": "Subject-specific information",
            "subject_id": subject_id,
            "publication_date": date.today().isoformat(),
            "expires_at": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            announcement = Announcement.query.filter_by(title="Cohort notice").one()
            self.assertEqual(announcement.subject_id, subject_id)
            notified_user_ids = {
                row.user_id for row in Notification.query.filter_by(title="Announcement: Cohort notice").all()
            }
            self.assertEqual(notified_user_ids, cohort_user_ids)
        self.client.get("/logout")
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        self.assertIn(b"Cohort notice", self.client.get("/announcements").data)

    def test_management_can_publish_announcements(self):
        self.client.post("/login", data={"email": "management@edutrack.com", "password": "EduTrack123!"})
        page = self.client.get("/announcements")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"New announcement", page.data)
        response = self.client.post("/announcements", data={
            "title": "Management notice",
            "content": "Academic schedule update",
            "publication_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            announcement = Announcement.query.filter_by(title="Management notice").one()
            announcement_id = announcement.id
        response = self.client.post(f"/announcements/{announcement_id}/delete")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Announcement, announcement_id))

    def test_faculty_cannot_announce_to_unassigned_subject(self):
        with self.app.app_context():
            faculty = Faculty.query.filter_by(user_id=User.query.filter_by(role="faculty").first().id).first()
            other_subject = Subject.query.filter(Subject.faculty_id != faculty.id).first()
            other_subject_id = other_subject.id
        self.client.post("/login", data={"email": "faculty@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post("/announcements", data={
            "title": "Unauthorized notice",
            "content": "Should not be saved",
            "subject_id": other_subject_id,
            "publication_date": date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(Announcement.query.filter_by(title="Unauthorized notice").first())

    def test_student_can_submit_assignment_file(self):
        with self.app.app_context():
            student = Student.query.filter_by(user_id=User.query.filter_by(email="student@edutrack.com").first().id).first()
            assignment = Assignment.query.join(Subject).filter(
                Subject.department_id == student.department_id,
                Subject.course_id == student.course_id,
                Subject.semester == student.semester,
            ).first()
            assignment_id = assignment.id
        self.client.post("/login", data={"email": "student@edutrack.com", "password": "EduTrack123!"})
        response = self.client.post(
            f"/student/assignments/{assignment_id}/submit",
            data={"file": (io.BytesIO(b"test submission"), "homework.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            student = Student.query.filter_by(user_id=User.query.filter_by(email="student@edutrack.com").first().id).first()
            submission = AssignmentSubmission.query.filter_by(
                assignment_id=assignment_id, student_id=student.id,
            ).one()
            stored_path = os.path.join(
                self.app.config["UPLOAD_FOLDER"], "assignments", submission.stored_name
            )
            self.assertTrue(os.path.isfile(stored_path))
            os.remove(stored_path)

    def test_login_analytics_excel_export(self):
        self.client.post("/login", data={"email": "admin@edutrack.com", "password": "EduTrack123!"})
        response = self.client.get("/login-count/export.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    unittest.main()
