import sqlite3
import os

DATABASE_PATH = os.path.join("database", "resume.db")


def get_connection():
    os.makedirs("database", exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_connection()

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
            FOREIGN KEY (job_id) REFERENCES jobs(id)
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
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (candidate_id) REFERENCES candidates(id)
        )
    """)

    connection.commit()
    connection.close()


def create_job(title, description, required_skills, unique_link):
    connection = get_connection()

    cursor = connection.execute("""
        INSERT INTO jobs
        (title, description, required_skills, unique_link)
        VALUES (?, ?, ?, ?)
    """, (
        title,
        description,
        required_skills,
        unique_link
    ))

    job_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return job_id


def get_all_jobs():
    connection = get_connection()

    jobs = connection.execute("""
        SELECT *
        FROM jobs
        ORDER BY created_at DESC
    """).fetchall()

    connection.close()

    return jobs


def get_job(job_id):
    connection = get_connection()

    job = connection.execute("""
        SELECT *
        FROM jobs
        WHERE id = ?
    """, (job_id,)).fetchone()

    connection.close()

    return job


def get_job_by_link(unique_link):
    connection = get_connection()

    job = connection.execute("""
        SELECT *
        FROM jobs
        WHERE unique_link = ?
    """, (unique_link,)).fetchone()

    connection.close()

    return job


def get_candidate_count(job_id):
    connection = get_connection()

    result = connection.execute("""
        SELECT COUNT(*) AS count
        FROM candidates
        WHERE job_id = ?
    """, (job_id,)).fetchone()

    connection.close()

    return result["count"]


def get_total_candidates():
    connection = get_connection()

    result = connection.execute("""
        SELECT COUNT(*) AS count
        FROM candidates
    """).fetchone()

    connection.close()

    return result["count"]


def create_candidate(
    job_id,
    name,
    address,
    phone,
    email,
    resume_filename
):
    connection = get_connection()

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
    connection.close()

    return candidate_id


def get_candidates_by_job(job_id):
    connection = get_connection()

    candidates = connection.execute("""
        SELECT *
        FROM candidates
        WHERE job_id = ?
        ORDER BY created_at DESC
    """, (job_id,)).fetchall()

    connection.close()

    return candidates


def save_result(
    job_id,
    candidate_id,
    score,
    matched_skills
):
    connection = get_connection()

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
    connection.close()


def get_job_results(job_id):
    connection = get_connection()

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

    connection.close()

    return results


def get_high_match_count(job_id):
    connection = get_connection()

    result = connection.execute("""
        SELECT COUNT(*) AS count
        FROM results
        WHERE job_id = ?
        AND score >= 70
    """, (job_id,)).fetchone()

    connection.close()

    return result["count"]


# ============================================================
# DELETE JOB
# ============================================================

def delete_job(job_id):
    connection = get_connection()

    try:
        # First delete ranking results
        connection.execute("""
            DELETE FROM results
            WHERE job_id = ?
        """, (job_id,))

        # Then delete candidates
        connection.execute("""
            DELETE FROM candidates
            WHERE job_id = ?
        """, (job_id,))

        # Finally delete the job
        connection.execute("""
            DELETE FROM jobs
            WHERE id = ?
        """, (job_id,))

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()