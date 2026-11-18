# EduTrack

EduTrack is a college management web application built with Flask, SQLite, Flask-SQLAlchemy, Flask-Login, Bootstrap 5, Chart.js, ReportLab, and OpenPyXL. SQLite is the project's configured database; data is stored locally in `instance/edutrack.db`.

## Run on Windows

```powershell
cd C:\path\to\EduTrack
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

The SQLite database is initialized automatically at `instance/edutrack.db`, together with demo departments, courses, users, students, faculty, attendance, marks, timetable entries, assignments, and announcements. The app does not use a MySQL connection string.

## Demo accounts

Use this common password for every account:

`EduTrack123!`

| Role | Email |
|---|---|
| Administrator | admin@edutrack.com |
| Faculty | faculty@edutrack.com |
| Student | student@edutrack.com |
| Management | management@edutrack.com |

## Security

- Passwords are hashed with Werkzeug.
- Flask-Login protects authenticated routes.
- Role checks protect administrative and faculty operations.
- POST requests are protected by an application CSRF token.
- SQLite access uses Flask-SQLAlchemy parameterized queries.

## Features

The application includes role dashboards, student roll numbers, student profile photos and details, read-only student profile views for administrators/management and assigned faculty, a separate student marks-and-results page, monthly attendance history, per-subject assessment averages and pass/fail results, faculty attendance and examination entry, timetable conflict checks, assignments with student file submissions and faculty grading, notifications, announcements that administrators and management can publish, audit logs, settings, PDF student reports, and Excel student reports. Academic rosters, statistics, and reports include only students linked to login accounts. Attendance shortage alerts are calculated per subject. Administrators can assign a faculty member’s department and subjects from the faculty edit page; faculty attendance, marks, timetable, and assignments are limited to assigned subjects.

Administrators can view login-attempt analytics (including failed attempts, unique successful users, recent activity, and an Excel export). Management and faculty dashboards include a rule-based academic-risk summary. The risk labels are indicators based on recorded attendance and marks, not a substitute for academic review.

Public signup creates student accounts and their student records, which then appear in the Students list. Administrator, faculty, and management accounts are provisioned separately and can still sign in.

Uploaded assignments are limited to 10 MB and an extension allowlist. Files are stored under `instance/uploads`; exclude that directory, the SQLite database, and secret configuration when backing up or distributing the application.

## Tests

```powershell
python -m unittest discover -s tests -v
```
