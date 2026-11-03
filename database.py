import sqlite3
import os


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FOLDER = os.path.join(BASE_DIR, "database")

DATABASE_PATH = os.path.join(
    DATABASE_FOLDER,
    "resume.db"
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    os.makedirs(DATABASE_FOLDER, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    connection = get_connection()

    try:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                title TEXT NOT NULL,

                description TEXT NOT NULL,

                required_skills TEXT NOT NULL,

                unique_link TEXT UNIQUE NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS candidates (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                name TEXT NOT NULL,

                address TEXT NOT NULL,

                phone TEXT NOT NULL,

                email TEXT NOT NULL,

                resume_filename TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (job_id)
                REFERENCES jobs(id)
                ON DELETE CASCADE

            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS results (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                candidate_id INTEGER NOT NULL,

                score REAL NOT NULL,

                matched_skills TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(job_id, candidate_id),

                FOREIGN KEY (job_id)
                REFERENCES jobs(id)
                ON DELETE CASCADE,

                FOREIGN KEY (candidate_id)
                REFERENCES candidates(id)
                ON DELETE CASCADE

            )
        """)

        connection.commit()

    except Exception as error:

        connection.rollback()

        print("Database initialization error:", error)

        raise

    finally:

        connection.close()


# ============================================================
# CREATE JOB
# ============================================================

def create_job(title, description, required_skills, unique_link):

    connection = get_connection()

    try:

        cursor = connection.execute("""
            INSERT INTO jobs
            (
                title,
                description,
                required_skills,
                unique_link
            )
            VALUES (?, ?, ?, ?)
        """, (
            title,
            description,
            required_skills,
            unique_link
        ))

        job_id = cursor.lastrowid

        connection.commit()

        return job_id

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# GET ALL JOBS WITH CANDIDATE COUNT
# ============================================================

def get_all_jobs():

    connection = get_connection()

    try:

        jobs = connection.execute("""
            SELECT
                jobs.*,

                (
                    SELECT COUNT(*)
                    FROM candidates
                    WHERE candidates.job_id = jobs.id

                ) AS candidate_count

            FROM jobs

            ORDER BY jobs.created_at DESC

        """).fetchall()

        return jobs

    finally:

        connection.close()


# ============================================================
# GET JOB BY ID
# ============================================================

def get_job(job_id):

    connection = get_connection()

    try:

        job = connection.execute("""
            SELECT *
            FROM jobs
            WHERE id = ?
        """, (job_id,)).fetchone()

        return job

    finally:

        connection.close()


# ============================================================
# GET JOB BY UNIQUE LINK
# ============================================================

def get_job_by_link(unique_link):

    connection = get_connection()

    try:

        job = connection.execute("""
            SELECT *
            FROM jobs
            WHERE unique_link = ?
        """, (unique_link,)).fetchone()

        return job

    finally:

        connection.close()


# ============================================================
# GET CANDIDATE COUNT FOR A JOB
# ============================================================

def get_candidate_count(job_id):

    connection = get_connection()

    try:

        result = connection.execute("""
            SELECT COUNT(*) AS count
            FROM candidates
            WHERE job_id = ?
        """, (job_id,)).fetchone()

        return result["count"]

    finally:

        connection.close()


# ============================================================
# GET TOTAL CANDIDATES
# ============================================================

def get_total_candidates():

    connection = get_connection()

    try:

        result = connection.execute("""
            SELECT COUNT(*) AS count
            FROM candidates
        """).fetchone()

        return result["count"]

    finally:

        connection.close()


# ============================================================
# CREATE CANDIDATE
# ============================================================

def create_candidate(
    job_id,
    name,
    address,
    phone,
    email,
    resume_filename
):

    connection = get_connection()

    try:

        cursor = connection.execute("""
            INSERT INTO candidates
            (
                job_id,
                name,
                address,
                phone,
                email,
                resume_filename
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            name,
            address,
            phone,
            email,
            resume_filename
        ))

        candidate_id = cursor.lastrowid

        connection.commit()

        return candidate_id

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# GET CANDIDATES BY JOB
# ============================================================

def get_candidates_by_job(job_id):

    connection = get_connection()

    try:

        candidates = connection.execute("""
            SELECT *
            FROM candidates
            WHERE job_id = ?
            ORDER BY created_at DESC
        """, (job_id,)).fetchall()

        return candidates

    finally:

        connection.close()


# ============================================================
# SAVE CANDIDATE RANKING RESULT
# ============================================================

def save_result(
    job_id,
    candidate_id,
    score,
    matched_skills
):

    connection = get_connection()

    try:

        if isinstance(matched_skills, list):

            matched_skills = ", ".join(matched_skills)

        connection.execute("""
            INSERT OR REPLACE INTO results
            (
                job_id,
                candidate_id,
                score,
                matched_skills
            )
            VALUES (?, ?, ?, ?)
        """, (
            job_id,
            candidate_id,
            score,
            matched_skills
        ))

        connection.commit()

    except Exception:

        connection.rollback()

        raise

    finally:

        connection.close()


# ============================================================
# GET JOB RANKING RESULTS
# ============================================================

def get_job_results(job_id):

    connection = get_connection()

    try:

        results = connection.execute("""
            SELECT
                c.id,
                c.name,
                c.address,
                c.phone,
                c.email,
                c.resume_filename,
                r.score,
                r.matched_skills

            FROM candidates c

            INNER JOIN results r
                ON c.id = r.candidate_id

            WHERE c.job_id = ?

            ORDER BY r.score DESC

        """, (job_id,)).fetchall()

        return results

    finally:

        connection.close()


# ============================================================
# GET HIGH-MATCH CANDIDATE COUNT
# ============================================================

def get_high_match_count(job_id):

    connection = get_connection()

    try:

        result = connection.execute("""
            SELECT COUNT(*) AS count

            FROM results

            WHERE job_id = ?

            AND score >= 70

        """, (job_id,)).fetchone()

        return result["count"]

    finally:

        connection.close()


# ============================================================
# DELETE JOB
# ============================================================

def delete_job(job_id):

    connection = get_connection()

    try:

        connection.execute("""
            DELETE FROM results
            WHERE job_id = ?
        """, (job_id,))

        connection.execute("""
            DELETE FROM candidates
            WHERE job_id = ?
        """, (job_id,))

        connection.execute("""
            DELETE FROM jobs
            WHERE id = ?
        """, (job_id,))

        connection.commit()

        return True

    except Exception as error:

        connection.rollback()

        print("Delete job error:", error)

        raise

    finally:

        connection.close()