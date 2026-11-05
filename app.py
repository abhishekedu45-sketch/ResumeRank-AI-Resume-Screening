
import os
import re
import secrets
import json
import urllib.request
import urllib.error
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_from_directory
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from database import (
    initialize_database, create_job, get_all_jobs,
    get_job, get_job_by_link, create_candidate,
    get_candidates_by_job, get_total_candidates,
    save_result, delete_job as db_delete_job
)
from resume_parser import extract_text_from_pdf
from ranking import calculate_resume_score

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get("RENDER_EXTERNAL_URL"):
    app.config["SESSION_COOKIE_SECURE"] = True

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

initialize_database()


# --------------------------------------------------
# ADMIN LOGIN PROTECTION
# --------------------------------------------------

def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


# --------------------------------------------------
# BREVO EMAIL API
# --------------------------------------------------

def send_gmail_email(to_email, subject, message_text):
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = os.environ.get("BREVO_SENDER_EMAIL", "").strip()

    if not api_key or not sender_email:
        app.logger.error("Brevo configuration is missing.")
        return False

    payload = {
        "sender": {
            "name": "ResumeRank Recruitment Team",
            "email": sender_email
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": message_text
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return response.status in (200, 201, 202)

    except urllib.error.HTTPError as error:
        app.logger.error(
            "Brevo email failed: %s",
            error.read().decode("utf-8", errors="replace")
        )
        return False

    except Exception:
        app.logger.exception("Brevo email sending failed.")
        return False


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def allowed_file(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() == "pdf"
    )


def public_base_url():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")

    if render_url:
        return render_url.rstrip("/")

    return request.url_root.rstrip("/")


def rank_job_candidates(job_id, job):
    candidates = get_candidates_by_job(job_id)
    ranked_candidates = []

    for candidate in candidates:
        resume_path = os.path.join(
            UPLOAD_FOLDER,
            candidate["resume_filename"]
        )

        if not os.path.isfile(resume_path):
            continue

        try:
            resume_text = extract_text_from_pdf(resume_path)

            result = calculate_resume_score(
                job["description"],
                job["required_skills"],
                resume_text
            )

            save_result(
                job_id,
                candidate["id"],
                result["score"],
                result["matched_skills"]
            )

            ranked_candidates.append({
                "id": candidate["id"],
                "name": candidate["name"],
                "email": candidate["email"],
                "phone": candidate["phone"],
                "address": candidate["address"],
                "resume_filename": candidate["resume_filename"],
                "match_score": result["score"],
                "matched_skills": result["matched_skills"],
                "skill_score": result["skill_score"],
                "similarity_score": result["similarity_score"]
            })

        except Exception:
            app.logger.exception("Candidate ranking failed.")

    ranked_candidates.sort(
        key=lambda item: item["match_score"],
        reverse=True
    )

    for index, candidate in enumerate(ranked_candidates, start=1):
        candidate["rank"] = index

    return ranked_candidates


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def index():
    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))

    return render_template("index.html")


# --------------------------------------------------
# ADMIN LOGIN
# --------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not ADMIN_USERNAME or not ADMIN_PASSWORD:
            flash(
                "Admin credentials are not configured. Check your .env file.",
                "error"
            )
            return render_template("login.html")

        if (
            secrets.compare_digest(username, ADMIN_USERNAME)
            and secrets.compare_digest(password, ADMIN_PASSWORD)
        ):
            session.clear()
            session["admin_logged_in"] = True
            flash("Welcome back, Admin!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
@admin_required
def dashboard():

    jobs = get_all_jobs()
    total_jobs = len(jobs)
    total_candidates = get_total_candidates()
    high_matches = 0

    for job in jobs:
        try:
            ranked = rank_job_candidates(job["id"], job)

            high_matches += sum(
                1 for candidate in ranked
                if candidate["match_score"] >= 70
            )

        except Exception:
            app.logger.exception("Dashboard ranking failed.")

    return render_template(
        "admin.html",
        jobs=jobs,
        total_jobs=total_jobs,
        total_candidates=total_candidates,
        high_matches=high_matches
    )


# --------------------------------------------------
# CREATE JOB
# --------------------------------------------------

@app.route(
    "/create-job",
    methods=["GET", "POST"],
    endpoint="create_job_page"
)
@app.route(
    "/create_job",
    methods=["GET", "POST"],
    endpoint="create_job_route"
)
@admin_required
def create_job_page():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        required_skills = request.form.get(
            "required_skills", ""
        ).strip()

        if not title or not description or not required_skills:
            flash("Please fill in all job details.", "error")
            return render_template("create_job.html")

        unique_link = secrets.token_urlsafe(20)

        try:
            job_id = create_job(
                title,
                description,
                required_skills,
                unique_link
            )

            job = get_job(job_id)

            if job is None:
                raise RuntimeError(
                    "Job was saved but could not be retrieved."
                )

            public_link = (
                f"{public_base_url()}/register/{unique_link}"
            )

            return render_template(
                "job_created.html",
                job=job,
                public_link=public_link,
                unique_link=unique_link
            )

        except Exception:
            app.logger.exception("Job creation failed.")
            flash("Unable to create job.", "error")

    return render_template("create_job.html")


# --------------------------------------------------
# DELETE JOB
# --------------------------------------------------

@app.route(
    "/delete-job/<int:job_id>",
    methods=["POST"],
    endpoint="delete_job"
)
@app.route(
    "/delete_job/<int:job_id>",
    methods=["POST"],
    endpoint="delete_job_route"
)
@admin_required
def delete_job_view(job_id):

    try:
        deleted = db_delete_job(job_id)

        if deleted:
            flash("Job deleted successfully.", "success")
        else:
            flash("Job not found.", "error")

    except Exception:
        app.logger.exception("Job deletion failed.")
        flash("Unable to delete job.", "error")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# PUBLIC CANDIDATE REGISTRATION
# --------------------------------------------------

@app.route("/register/<unique_link>", methods=["GET", "POST"])
def candidate_register(unique_link):

    job = get_job_by_link(unique_link)

    if not job:
        return render_template("registration_closed.html"), 404

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        resume = request.files.get("resume")

        if not all([name, address, phone, email, resume]):
            flash("Please complete all fields.", "error")
            return render_template(
                "candidate_register.html",
                job=job
            )

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.", "error")
            return render_template(
                "candidate_register.html",
                job=job
            )

        if not allowed_file(resume.filename):
            flash("Only PDF resumes are allowed.", "error")
            return render_template(
                "candidate_register.html",
                job=job
            )

        filename = secure_filename(resume.filename)

        if not filename:
            flash("Invalid resume filename.", "error")
            return render_template(
                "candidate_register.html",
                job=job
            )

        unique_filename = (
            f"{secrets.token_hex(12)}_{filename}"
        )

        resume_path = os.path.join(
            UPLOAD_FOLDER,
            unique_filename
        )

        try:
            resume.save(resume_path)

            extract_text_from_pdf(resume_path)

            create_candidate(
                job["id"],
                name,
                address,
                phone,
                email,
                unique_filename
            )

            # Registration does not send an automatic email.
            flash(
                "Application submitted successfully.",
                "success"
            )

            return render_template(
                "upload_success.html",
                candidate_name=name,
                job=job
            )

        except Exception:
            if os.path.exists(resume_path):
                os.remove(resume_path)

            app.logger.exception("Registration failed.")
            flash("Unable to submit application.", "error")

    return render_template(
        "candidate_register.html",
        job=job
    )


# --------------------------------------------------
# AI RESULTS
# --------------------------------------------------

@app.route("/results/<int:job_id>")
@admin_required
def results(job_id):

    job = get_job(job_id)

    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("dashboard"))

    candidates = rank_job_candidates(job_id, job)

    total_applicants = len(
        get_candidates_by_job(job_id)
    )

    high_matches = sum(
        1 for candidate in candidates
        if candidate["match_score"] >= 70
    )

    return render_template(
        "results.html",
        job=job,
        candidates=candidates,
        total_applicants=total_applicants,
        high_matches=high_matches
    )


# --------------------------------------------------
# DOWNLOAD RESUME
# --------------------------------------------------

@app.route("/resume/<filename>")
@admin_required
def download_resume(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename,
        as_attachment=True
    )


# --------------------------------------------------
# SEND INTERVIEW EMAIL
# --------------------------------------------------

@app.route(
    "/send-interview-email/<int:job_id>/<int:candidate_id>",
    methods=["POST"]
)
@admin_required
def send_interview_email(job_id, candidate_id):

    job = get_job(job_id)

    if not job:
        flash("Job not found.", "error")
        return redirect(url_for("dashboard"))

    candidates = get_candidates_by_job(job_id)

    candidate = next(
        (
            item for item in candidates
            if item["id"] == candidate_id
        ),
        None
    )

    if not candidate:
        flash("Candidate not found.", "error")
        return redirect(
            url_for("results", job_id=job_id)
        )

    ranked = rank_job_candidates(job_id, job)

    selected = next(
        (
            item for item in ranked
            if item["id"] == candidate_id
        ),
        None
    )

    if not selected or selected["match_score"] < 70:
        flash(
            "Only candidates scoring 70% or above can receive interview emails.",
            "error"
        )
        return redirect(
            url_for("results", job_id=job_id)
        )

    message = f"""Dear {candidate['name']},

Congratulations!

Your resume has been shortlisted for {job['title']}.

You have been selected for the next stage of the interview process.

Regards,
ResumeRank Recruitment Team
"""

    sent = send_gmail_email(
        candidate["email"],
        f"Interview Invitation - {job['title']}",
        message
    )

    if sent:
        flash("Interview email sent successfully.", "success")
    else:
        flash(
            "Email could not be sent. Check Brevo API key, sender verification and Render logs.",
            "error"
        )

    return redirect(
        url_for("results", job_id=job_id)
    )


# --------------------------------------------------
# PRIVACY POLICY
# --------------------------------------------------

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))


# --------------------------------------------------
# ERROR HANDLERS
# --------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(413)
def file_too_large(error):
    return "File too large. Maximum allowed size is 16 MB.", 413


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
