
import os
import uuid
import sqlite3
import requests
import secrets
import hmac

from dotenv import load_dotenv
load_dotenv()

from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory
)

from werkzeug.utils import secure_filename

from database import (
    initialize_database,
    create_job,
    get_all_jobs,
    get_job,
    get_job_by_link,
    get_candidate_count,
    get_total_candidates,
    create_candidate,
    save_result,
    get_high_match_count,
    rejection_email_already_sent,
    record_rejection_email_sent
)

from ranking import rank_candidates
from resume_parser import extract_text_from_pdf


# ==================================================
# FLASK CONFIGURATION
# ==================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATABASE_FOLDER = os.path.join(BASE_DIR, "database")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATABASE_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get("RENDER_EXTERNAL_URL"):
    app.config["SESSION_COOKIE_SECURE"] = True

ALLOWED_EXTENSIONS = {"pdf"}
DATABASE_PATH = os.path.join(DATABASE_FOLDER, "resume.db")


# ==================================================
# RESEND EMAIL CONFIGURATION
# ==================================================

def send_resend_email(to_email, to_name, subject, email_text):

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender_email = os.environ.get(
        "RESEND_FROM_EMAIL", ""
    ).strip()

    if not api_key or not sender_email:
        app.logger.error(
            "Resend settings missing: RESEND_API_KEY or RESEND_FROM_EMAIL."
        )
        return False

    payload = {
        "from": sender_email,
        "to": [to_email],
        "subject": subject,
        "text": email_text
    }

    if to_name:
        payload["to"] = [f"{to_name} <{to_email}>"]

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=25
        )

        if response.status_code in (200, 201, 202):
            app.logger.info(
                "Resend accepted email for %s. Response: %s",
                to_email,
                response.text[:500]
            )
            return True

        app.logger.error(
            "Resend email failed. Status: %s; Response: %s",
            response.status_code,
            response.text[:1000]
        )

        return False

    except requests.RequestException:
        app.logger.exception("Resend API request failed.")
        return False


# ==================================================
# CSRF SECURITY PROTECTION
# ==================================================

@app.before_request
def csrf_protect():

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):

        token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRF-Token")
        )

        session_token = session.get("csrf_token", "")

        if (
            not token
            or not session_token
            or not hmac.compare_digest(token, session_token)
        ):
            return "Invalid or missing CSRF token.", 400


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": session.get("csrf_token", "")}


# ==================================================
# ADMIN LOGIN SETTINGS
# ==================================================

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ==================================================
# DATABASE INITIALIZATION
# ==================================================

initialize_database()


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def allowed_file(filename):

    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def admin_required(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return decorated_function


def get_public_base_url():

    render_url = os.environ.get("RENDER_EXTERNAL_URL")

    if render_url:
        return render_url.rstrip("/")

    return request.url_root.rstrip("/")


def get_db_connection():

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def get_candidate_details(job_id):

    connection = get_db_connection()

    try:

        candidates = connection.execute(
            """
            SELECT *
            FROM candidates
            WHERE job_id = ?
            ORDER BY id DESC
            """,
            (job_id,)
        ).fetchall()

        return candidates

    finally:
        connection.close()


# ==================================================
# AI RESUME RANKING
# ==================================================

def rank_job_candidates(job_id, job):

    candidates = get_candidate_details(job_id)
    candidate_list = []

    for candidate in candidates:

        resume_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            candidate["resume_filename"]
        )

        if not os.path.isfile(resume_path):

            app.logger.warning(
                "Resume file not found: %s",
                resume_path
            )

            continue

        try:

            resume_text = extract_text_from_pdf(resume_path)

            candidate_list.append({
                "id": candidate["id"],
                "name": candidate["name"],
                "email": candidate["email"],
                "phone": candidate["phone"],
                "address": candidate["address"],
                "resume_filename": candidate["resume_filename"],
                "resume_text": resume_text
            })

        except Exception:

            app.logger.exception(
                "Resume extraction failed for candidate ID %s",
                candidate["id"]
            )

    if not candidate_list:
        return []

    ranked = rank_candidates(
        candidate_list,
        job["description"],
        job["required_skills"]
    )

    for candidate in ranked:

        try:

            save_result(
                job_id,
                candidate["id"],
                candidate["match_score"],
                candidate["matched_skills"]
            )

        except Exception:

            app.logger.exception(
                "Unable to save ranking result for candidate ID %s",
                candidate["id"]
            )

    return ranked


# ==================================================
# AUTOMATIC REJECTION EMAILS - BELOW 70%
# ==================================================

def send_automatic_rejection_emails(job_id, job, ranked_candidates):

    sender_name = os.environ.get(
        "RESEND_SENDER_NAME",
        "ResumeRank"
    ).strip()

    sent_count = 0

    for candidate in ranked_candidates:

        try:

            score = float(candidate.get("match_score", 0))

            if score >= 70:
                continue

            candidate_id = candidate["id"]
            candidate_email = (
                candidate.get("email") or ""
            ).strip()

            if not candidate_email:
                continue

            if rejection_email_already_sent(job_id, candidate_id):
                continue

            email_text = f"""Dear {candidate["name"]},

Thank you for applying for the position of {job["title"]}.

We appreciate the time and effort you took to submit your application.

After reviewing your resume against the requirements for this position,
we regret to inform you that your application has not been shortlisted
for the next stage of the selection process.

We appreciate your interest and wish you success in your future career.

Thank you.

Recruitment Team
{sender_name}
"""

            email_sent = send_resend_email(
                candidate_email,
                candidate["name"],
                f"Application Update - {job['title']}",
                email_text
            )

            if email_sent:

                record_rejection_email_sent(
                    job_id,
                    candidate_id
                )

                sent_count += 1

                app.logger.info(
                    "Rejection email accepted by Resend for candidate ID %s.",
                    candidate_id
                )

        except Exception:

            app.logger.exception(
                "Automatic rejection email failed for candidate ID %s.",
                candidate.get("id")
            )

    return sent_count


# ==================================================
# DASHBOARD HIGH MATCH COUNT
# ==================================================

def get_dashboard_high_matches(jobs):

    total_high_matches = 0

    for job in jobs:

        try:

            rank_job_candidates(job["id"], job)

            total_high_matches += get_high_match_count(job["id"])

        except Exception:

            app.logger.exception(
                "Dashboard ranking failed for job ID %s",
                job["id"]
            )

    return total_high_matches


# ==================================================
# HOME PAGE
# ==================================================

@app.route("/")
def home():

    return redirect(url_for("admin_login"))


@app.route("/privacy")
def privacy():

    return render_template("privacy.html")


# ==================================================
# ADMIN LOGIN
# ==================================================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()
            session["admin_logged_in"] = True

            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/dashboard")
@admin_required
def dashboard():

    jobs = get_all_jobs()

    total_jobs = len(jobs)
    total_candidates = get_total_candidates()
    job_data = []

    for job in jobs:

        candidate_count = get_candidate_count(job["id"])

        job_data.append({
            "id": job["id"],
            "title": job["title"],
            "description": job["description"],
            "required_skills": job["required_skills"],
            "unique_link": job["unique_link"],
            "candidate_count": candidate_count
        })

    high_matches = get_dashboard_high_matches(jobs)

    return render_template(
        "admin.html",
        jobs=job_data,
        total_jobs=total_jobs,
        total_candidates=total_candidates,
        high_matches=high_matches
    )


# ==================================================
# CREATE JOB
# ==================================================

@app.route("/create-job", methods=["GET", "POST"])
@admin_required
def create_job_route():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        required_skills = request.form.get(
            "required_skills",
            ""
        ).strip()

        if not title or not description or not required_skills:

            flash("Please fill in all required fields.", "error")

            return redirect(url_for("create_job_route"))

        unique_link = uuid.uuid4().hex

        try:

            create_job(
                title,
                description,
                required_skills,
                unique_link
            )

            job = get_job_by_link(unique_link)

            public_link = (
                get_public_base_url()
                + url_for(
                    "candidate_register",
                    unique_link=unique_link
                )
            )

            return render_template(
                "job_created.html",
                job=job,
                public_link=public_link
            )

        except Exception:

            app.logger.exception("Job creation failed.")

            flash(
                "Unable to create job. Please try again.",
                "error"
            )

            return redirect(url_for("create_job_route"))

    return render_template("create_job.html")


# ==================================================
# CANDIDATE REGISTRATION
# ==================================================

@app.route("/register/<unique_link>", methods=["GET", "POST"])
def candidate_register(unique_link):

    job = get_job_by_link(unique_link)

    if not job:
        return "Job registration link not found.", 404

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        resume = request.files.get("resume")

        if not all([name, address, phone, email]):

            flash("Please complete all fields.", "error")

            return redirect(request.url)

        if not resume or not resume.filename:

            flash("Please select your resume.", "error")

            return redirect(request.url)

        if not allowed_file(resume.filename):

            flash("Only PDF resumes are allowed.", "error")

            return redirect(request.url)

        original_filename = secure_filename(resume.filename)

        if not original_filename:

            flash("Invalid resume filename.", "error")

            return redirect(request.url)

        filename = str(uuid.uuid4()) + "_" + original_filename

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        try:

            resume.save(filepath)

            create_candidate(
                job["id"],
                name,
                address,
                phone,
                email,
                filename
            )

        except Exception:

            if os.path.exists(filepath):
                os.remove(filepath)

            app.logger.exception("Candidate registration failed.")

            flash(
                "Unable to submit your application. Please try again.",
                "error"
            )

            return redirect(request.url)

        return render_template(
            "upload_success.html",
            name=name,
            job=job
        )

    return render_template("register.html", job=job)


# ==================================================
# VIEW JOB
# ==================================================

@app.route("/job/<int:job_id>")
@admin_required
def view_job(job_id):

    job = get_job(job_id)

    if not job:
        return "Job not found.", 404

    return redirect(url_for("results", job_id=job_id))


# ==================================================
# RESUME VIEW
# ==================================================

@app.route("/uploads/<filename>")
@admin_required
def uploaded_resume(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=False
    )


# ==================================================
# RESULTS AND AI RANKING
# ==================================================

@app.route("/results/<int:job_id>")
@admin_required
def results(job_id):

    job = get_job(job_id)

    if not job:
        return "Job not found.", 404

    try:

        ranked_candidates = rank_job_candidates(job_id, job)

    except Exception:

        app.logger.exception("Candidate ranking failed.")

        ranked_candidates = []

        flash(
            "Unable to rank candidates. Please check ranking.py.",
            "error"
        )

    try:

        rejected_email_count = send_automatic_rejection_emails(
            job_id,
            job,
            ranked_candidates
        )

        if rejected_email_count > 0:

            flash(
                f"{rejected_email_count} rejection email(s) accepted by Resend.",
                "success"
            )

    except Exception:

        app.logger.exception(
            "Automatic rejection email process failed for job %s.",
            job_id
        )

    total_applicants = get_candidate_count(job_id)

    high_matches = sum(
        1
        for candidate in ranked_candidates
        if float(candidate.get("match_score", 0)) >= 70
    )

    return render_template(
        "results.html",
        job=job,
        candidates=ranked_candidates,
        total_applicants=total_applicants,
        high_matches=high_matches
    )


# ==================================================
# DELETE JOB
# ==================================================

@app.route("/delete-job/<int:job_id>", methods=["POST"])
@admin_required
def delete_job(job_id):

    connection = get_db_connection()

    try:

        job = connection.execute(
            "SELECT id FROM jobs WHERE id = ?",
            (job_id,)
        ).fetchone()

        if not job:

            flash("Job not found.", "error")

            return redirect(url_for("dashboard"))

        candidates = connection.execute(
            """
            SELECT resume_filename
            FROM candidates
            WHERE job_id = ?
            """,
            (job_id,)
        ).fetchall()

        connection.execute(
            "DELETE FROM results WHERE job_id = ?",
            (job_id,)
        )

        connection.execute(
            "DELETE FROM candidates WHERE job_id = ?",
            (job_id,)
        )

        connection.execute(
            "DELETE FROM jobs WHERE id = ?",
            (job_id,)
        )

        connection.commit()

        for candidate in candidates:

            filename = candidate["resume_filename"]

            filepath = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            if os.path.isfile(filepath):

                try:
                    os.remove(filepath)

                except OSError:
                    app.logger.exception("Could not delete resume file.")

        flash("Job deleted successfully.", "success")

    except Exception:

        connection.rollback()

        app.logger.exception("Job deletion failed.")

        flash(
            "Unable to delete job. Please try again.",
            "error"
        )

    finally:
        connection.close()

    return redirect(url_for("dashboard"))


# ==================================================
# SEND INDIVIDUAL INTERVIEW EMAIL USING RESEND
# ==================================================

@app.route(
    "/send-interview-email/<int:candidate_id>/<int:job_id>",
    methods=["POST"]
)
@admin_required
def send_interview_email(candidate_id, job_id):

    connection = get_db_connection()

    try:

        candidate = connection.execute(
            """
            SELECT *
            FROM candidates
            WHERE id = ? AND job_id = ?
            """,
            (candidate_id, job_id)
        ).fetchone()

        job = connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,)
        ).fetchone()

    finally:
        connection.close()

    if not candidate or not job:

        flash("Candidate or job not found.", "error")

        return redirect(url_for("dashboard"))

    if not candidate["email"]:

        flash("Candidate email address is missing.", "error")

        return redirect(url_for("results", job_id=job_id))

    email_text = f"""Dear {candidate["name"]},

Congratulations!

Your resume has been shortlisted for the position of
{job["title"]}.

Our recruitment team would like to invite you for the
next stage of the selection process.

Please contact our recruitment team for interview details.

Thank you.

Recruitment Team
ResumeRank
AI Resume Screening and Ranking System
"""

    email_sent = send_resend_email(
        candidate["email"],
        candidate["name"],
        f"Interview Invitation - {job['title']}",
        email_text
    )

    if email_sent:

        flash(
            "Interview invitation accepted by Resend.",
            "success"
        )

    else:

        flash(
            "Email could not be sent. Check RESEND_API_KEY, RESEND_FROM_EMAIL and the Render logs.",
            "error"
        )

    return redirect(url_for("results", job_id=job_id))


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.clear()

    response = redirect(url_for("admin_login"))

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# ==================================================
# PREVENT DASHBOARD CACHE
# ==================================================

@app.after_request
def prevent_cache(response):

    if request.endpoint in [
        "dashboard",
        "admin_login",
        "results",
        "create_job_route"
    ]:

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# ==================================================
# COMPATIBILITY ENDPOINTS
# ==================================================

app.add_url_rule(
    "/results/<int:job_id>",
    endpoint="job_results",
    view_func=results
)

app.add_url_rule(
    "/delete-job/<int:job_id>",
    endpoint="delete_job_route",
    view_func=delete_job,
    methods=["POST"]
)

app.add_url_rule(
    "/create-job",
    endpoint="create_job_page",
    view_func=create_job_route,
    methods=["GET", "POST"]
)


# ==================================================
# ERROR HANDLERS
# ==================================================

@app.errorhandler(404)
def page_not_found(error):

    template_path = os.path.join(
        BASE_DIR,
        "templates",
        "404.html"
    )

    if os.path.isfile(template_path):
        return render_template("404.html"), 404

    return "Page not found.", 404


@app.errorhandler(413)
def file_too_large(error):

    return (
        "Resume file is too large. Maximum size is 16 MB.",
        413
    )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=(
            os.environ.get("FLASK_DEBUG", "false").lower() == "true"
        )
    )
