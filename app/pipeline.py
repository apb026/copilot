"""
pipeline.py
The actual "JD in, tailored resume + cover letter + scores out" flow.
Everything in app.py and the extension receiver calls into this, so
there's exactly one place that defines what "generate for this JD" means.
"""

import json
from db import get_connection, now
import memory
import llm
from jd_parser import parse_jd


def ingest_job_description(raw_text: str, url: str = None, source_platform: str = None):
    """Parse and store a new JD. Returns the job_description_id and parsed fields."""
    parsed = parse_jd(raw_text, url=url, source_platform=source_platform)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO job_descriptions
           (company, title, raw_text, url, source_platform,
            parsed_requirements, parsed_responsibilities, parsed_preferred_skills, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed.get("company"),
            parsed.get("title"),
            raw_text,
            url,
            source_platform,
            json.dumps(parsed.get("requirements", [])),
            json.dumps(parsed.get("responsibilities", [])),
            json.dumps(parsed.get("preferred_skills", [])),
            now(),
        ),
    )
    jd_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jd_id, parsed


def generate_for_job(jd_id: int, max_pages: int = 1):
    """
    Full pipeline for one job description:
    retrieve relevant memory -> generate resume -> truth-check ->
    skill gap -> ATS score -> generate cover letter.
    Returns a dict with everything, and persists the resume/cover letter rows.
    """
    conn = get_connection()
    jd_row = conn.execute(
        "SELECT * FROM job_descriptions WHERE id = ?", (jd_id,)
    ).fetchone()
    conn.close()
    if jd_row is None:
        raise ValueError(f"No job_description with id {jd_id}")
    jd_text = jd_row["raw_text"]

    preferences = memory.get_active_preferences()
    retrieved = memory.retrieve_relevant(
        jd_text, top_k=15, item_types=["bullet", "project", "skill", "cert", "summary"]
    )

    resume_md = llm.generate_resume(jd_text, retrieved, preferences, max_pages=max_pages)
    truth_result = llm.truth_check(resume_md, retrieved)
    gap_result = llm.skill_gap_analysis(jd_text, retrieved)
    ats_result = llm.ats_score(jd_text, resume_md)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO resume_versions
           (job_description_id, content_markdown, ats_score, truth_check_passed,
            truth_check_notes, skill_gap_notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            jd_id,
            resume_md,
            ats_result.get("score"),
            1 if truth_result.get("passed") else 0,
            json.dumps(truth_result.get("flagged_claims", [])),
            json.dumps(gap_result),
            now(),
        ),
    )
    resume_id = cur.lastrowid
    conn.commit()
    conn.close()

    cover_letter_md = llm.generate_cover_letter(jd_text, resume_md, preferences)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO cover_letters (job_description_id, resume_version_id, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (jd_id, resume_id, cover_letter_md, now()),
    )
    cover_letter_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "jd_id": jd_id,
        "resume_id": resume_id,
        "cover_letter_id": cover_letter_id,
        "resume_markdown": resume_md,
        "cover_letter": cover_letter_md,
        "ats_score": ats_result,
        "truth_check": truth_result,
        "skill_gap": gap_result,
        "retrieved_count": len(retrieved),
    }


def save_user_edit(resume_id: int = None, cover_letter_id: int = None, final_text: str = None):
    """
    Persist what the user actually sent after editing. This is the
    learning signal: future generations can be compared against what
    you actually kept versus what you changed.
    """
    conn = get_connection()
    if resume_id is not None:
        conn.execute(
            "UPDATE resume_versions SET user_edited_final = ? WHERE id = ?",
            (final_text, resume_id),
        )
    if cover_letter_id is not None:
        conn.execute(
            "UPDATE cover_letters SET user_edited_final = ? WHERE id = ?",
            (final_text, cover_letter_id),
        )
    conn.commit()
    conn.close()


def update_application_status(jd_id: int, resume_id: int, status: str, notes: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM applications WHERE job_description_id = ?", (jd_id,)
    ).fetchone()
    if existing:
        cur.execute(
            "UPDATE applications SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (status, notes, now(), existing["id"]),
        )
    else:
        cur.execute(
            """INSERT INTO applications
               (job_description_id, resume_version_id, status, notes, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (jd_id, resume_id, status, notes, now()),
        )
    conn.commit()
    conn.close()
