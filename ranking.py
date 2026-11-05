
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def clean_text(text):
    """Clean text before AI comparison."""
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9+#.\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def calculate_similarity(job_description, resume_text):
    """Calculate job-description and resume similarity."""
    job_description = clean_text(job_description)
    resume_text = clean_text(resume_text)

    if not job_description or not resume_text:
        return 0.0

    try:
        vectorizer = TfidfVectorizer(stop_words="english")
        vectors = vectorizer.fit_transform(
            [job_description, resume_text]
        )

        score = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
        return round(float(score) * 100, 2)

    except ValueError:
        return 0.0


def find_matched_skills(required_skills, resume_text):
    """Find required skills mentioned in the resume."""
    resume = clean_text(resume_text)

    if isinstance(required_skills, str):
        skills = required_skills.split(",")
    else:
        skills = required_skills or []

    matched = []

    for skill in skills:
        skill = skill.strip()
        if not skill:
            continue

        pattern = r"(?<![a-z0-9+#])" + re.escape(
            clean_text(skill)
        ) + r"(?![a-z0-9+#])"

        if re.search(pattern, resume):
            matched.append(skill)

    return matched


def calculate_resume_score(job_description, required_skills, resume_text):
    """
    Calculate a combined resume score:
    70% required skill match and 30% text similarity.
    """

    skills = [
        skill.strip()
        for skill in (
            required_skills.split(",")
            if isinstance(required_skills, str)
            else (required_skills or [])
        )
        if skill.strip()
    ]

    matched_skills = find_matched_skills(skills, resume_text)

    if skills:
        skill_score = (len(matched_skills) / len(skills)) * 100
    else:
        skill_score = 0

    similarity_score = calculate_similarity(
        job_description, resume_text
    )

    final_score = (skill_score * 0.70) + (
        similarity_score * 0.30
    )

    return {
        "score": round(final_score, 2),
        "skill_score": round(skill_score, 2),
        "similarity_score": round(similarity_score, 2),
        "matched_skills": matched_skills,
        "status": "Selected" if final_score >= 70 else "Not Selected"
    }


def rank_resumes(job_description, required_skills, resumes):
    """Rank multiple resumes from highest to lowest score."""

    results = []

    for resume in resumes:
        result = calculate_resume_score(
            job_description,
            required_skills,
            resume["text"]
        )

        results.append({
            **resume,
            **result
        })

    return sorted(
        results,
        key=lambda item: item["score"],
        reverse=True
    )
