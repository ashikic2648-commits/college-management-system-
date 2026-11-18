import os
import secrets
from flask import Flask
from flask import request, session, abort
from flask_login import LoginManager
from flask_login import current_user
from sqlalchemy import inspect, text
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()


def create_app(test_config=None):
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance"), exist_ok=True)
    app = Flask(__name__)
    app.config.from_object("config.Config")
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from .models import seed_demo_data
    from .auth import auth_bp
    from .admin import admin_bp
    from .faculty import faculty_bp
    from .student import student_bp
    from .management import management_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(management_bp)

    @app.before_request
    def csrf_protection():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        if request.method == "POST" and not app.config.get("TESTING"):
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if supplied != session["csrf_token"]:
                abort(400, "Invalid CSRF token")

    @app.context_processor
    def context():
        from datetime import datetime
        from .models import Notification
        notifications = []
        unread_count = 0
        if current_user.is_authenticated:
            notifications = Notification.query.filter_by(
                user_id=current_user.id, read_at=None
            ).order_by(Notification.created_at.desc()).limit(5).all()
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, read_at=None
            ).count()
        return {
            "csrf_token": session.get("csrf_token"),
            "current_date": datetime.now().strftime("%A, %B %d"),
            "recent_notifications": notifications,
            "unread_notification_count": unread_count,
        }

    with app.app_context():
        db.create_all()
        announcement_columns = {
            column["name"] for column in inspect(db.engine).get_columns("announcement")
        }
        student_columns = {
            column["name"] for column in inspect(db.engine).get_columns("student")
        }
        with db.engine.begin() as connection:
            if "expires_at" not in announcement_columns:
                connection.execute(text("ALTER TABLE announcement ADD COLUMN expires_at DATE"))
            if "subject_id" not in announcement_columns:
                connection.execute(text(
                    "ALTER TABLE announcement ADD COLUMN subject_id INTEGER REFERENCES subject(id)"
                ))
            if "photo_filename" not in student_columns:
                connection.execute(text("ALTER TABLE student ADD COLUMN photo_filename VARCHAR(100)"))
        seed_demo_data()

    return app
