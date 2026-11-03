import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# AI RESUME RANKING SYSTEM
# ============================================================

def rank_candidates(candidates, job_description, required_skills):

    if not candidates:
        return []

    # Convert required skills into a list
    skills = [
        skill.strip().lower()
        for skill in (required_skills or "").split(",")
        if skill.strip()
    ]

    # Job description and required skills
    job_text = (
        (job_description or "") + " " + (required_skills or "")
    )

    documents = [job_text]

    # Extract resume text from candidates
    for candidate in candidates:

        resume_text = candidate.get("resume_text", "")

        documents.append(
            resume_text if isinstance(resume_text, str) else ""
        )

    # Calculate resume similarity
    try:

        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2)
        )

        matrix = vectorizer.fit_transform(documents)

        similarities = cosine_similarity(
            matrix[0:1],
            matrix[1:]
        )[0]

    except ValueError:

        similarities = [0.0] * len(candidates)

    # Calculate candidate scores
    for index, candidate in enumerate(candidates):

        resume_text = candidate.get(
            "resume_text", ""
        )

        resume_text = (
            resume_text.lower()
            if isinstance(resume_text, str)
            else ""
        )

        matched_skills = []

        # Check each required skill
        for skill in skills:

            pattern = (
                r"(?<![a-z0-9+#.])"
                + re.escape(skill)
                + r"(?![a-z0-9+#.])"
            )

            if re.search(pattern, resume_text):

                matched_skills.append(skill)

        # Skill matching score (70%)
        skill_score = (
            len(matched_skills) / len(skills) * 100
            if skills else 0
        )

        # Resume similarity score (30%)
        similarity_score = (
            float(similarities[index]) * 100
        )

        # Final AI matching score
        final_score = (
            skill_score * 0.70
            + similarity_score * 0.30
        )

        # Store candidate results
        candidate["matched_skills"] = matched_skills

        candidate["match_score"] = round(
            final_score, 2
        )

    # Rank candidates from highest to lowest
    candidates.sort(
        key=lambda candidate: candidate["match_score"],
        reverse=True
    )

    # Assign rank numbers
    for index, candidate in enumerate(candidates):

        candidate["rank"] = index + 1

    return candidates