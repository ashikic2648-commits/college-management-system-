from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from . import db
from datetime import date
from .models import User, Student, Department, Course, LoginEvent, audit


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        department_id = request.form.get("department_id")
        course_id = request.form.get("course_id")
        role = "student"

        if len(name) < 2:
            flash("Enter your full name.", "danger")
        elif not email or "@" not in email:
            flash("Enter a valid email address.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif password != confirm_password:
            flash("Passwords do not match.", "danger")
        elif role == "student" and (not department_id or not course_id):
            flash("Select a department and course.", "danger")
        else:
            department = db.session.get(Department, int(department_id)) if department_id else None
            course = db.session.get(Course, int(course_id)) if course_id else None
            if not department or (
                role == "student" and (not course or course.department_id != department.id)
            ):
                flash("Select a valid department and course.", "danger")
            else:
                user = User(name=name, email=email, role=role, active=True)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()

                if role == "student":
                    linked_student_count = Student.query.filter(Student.user_id.isnot(None)).count()
                    roll_number = f"ET{1000 + linked_student_count + 1}"
                    while Student.query.filter_by(roll_number=roll_number).first():
                        roll_number = f"ET{int(roll_number[2:]) + 1}"
                    student = Student(
                        user_id=user.id,
                        roll_number=roll_number,
                        full_name=name,
                        email=email,
                        department_id=department.id,
                        course_id=course.id,
                        semester=1,
                        admission_year=date.today().year,
                        status="Active",
                    )
                    db.session.add(student)
                audit(user, "Account Signup", f"{name} created a {role} account")
                db.session.commit()
                login_user(user)
                flash("Account created successfully.", "success")
                if role == "student":
                    return redirect(url_for("student.profile"))
                return redirect(url_for("admin.dashboard"))

    return render_template(
        "signup.html",
        departments=Department.query.order_by(Department.name).all(),
        courses=Course.query.order_by(Course.name).all(),
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(password):
            db.session.add(LoginEvent(
                user_id=user.id,
                attempted_email=email,
                role=user.role,
                succeeded=True,
            ))
            login_user(user)
            audit(user, "Login", f"{user.email} logged in")
            db.session.commit()
            if user.role == "student":
                return redirect(url_for("student.profile"))
            return redirect(url_for("admin.dashboard"))
        db.session.add(LoginEvent(
            user_id=user.id if user else None,
            attempted_email=email,
            role=user.role if user else None,
            succeeded=False,
        ))
        db.session.commit()
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    audit(current_user, "Logout", f"{current_user.email} logged out")
    db.session.commit()
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
    elif len(new_password) < 8:
        flash("New password must contain at least 8 characters.", "danger")
    else:
        current_user.set_password(new_password)
        audit(current_user, "Password Change", "User changed account password")
        db.session.commit()
        flash("Password changed successfully.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))
