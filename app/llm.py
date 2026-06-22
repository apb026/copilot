"""
llm.py
Thin wrapper around the Groq API. Keeps all prompts in one place so
the writing-style constraints (no buzzwords, no em dashes, no fake
experience) are enforced consistently everywhere, not duplicated.
"""

import os
import json
from groq import Groq

MODEL = "llama-3.3-70b-versatile"

_client = None


def client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to your environment or "
                ".streamlit/secrets.toml as GROQ_API_KEY."
            )
        _client = Groq(api_key=api_key)
    return _client


STYLE_RULES = """
Writing rules, follow strictly:
- No em dashes, anywhere. Use periods or commas instead.
- No AI-sounding buzzwords: avoid "leverage", "synergy", "spearheaded",
  "passionate", "dynamic", "results-driven", "cutting-edge", "utilize".
  Use plain, specific verbs instead.
- No exaggerated claims and no invented experience. Every claim must be
  traceable to the source material provided. If the source material does
  not support a strong claim, write the honest, smaller claim instead.
- No keyword stuffing. Mention a skill only where it is true and relevant.
- Sound like a specific person wrote it, not a template.
"""


def _chat(system_prompt: str, user_prompt: str, temperature: float = 0.4):
    resp = client().chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def generate_resume(jd_text: str, retrieved_items: list, preferences: list, max_pages: int = 1):
    source_block = "\n".join(
        f"- [{i['item_type']}] ({i.get('source_label') or 'unlabeled'}): {i['content']}"
        for i in retrieved_items
    )
    pref_block = "\n".join(f"- {p}" for p in preferences) or "(none set yet)"

    system_prompt = f"""You write tailored, honest, ATS-friendly one-page resumes.
{STYLE_RULES}
Maximum length: {max_pages} page(s) of standard resume content.
You may ONLY use facts from the SOURCE MATERIAL section below. Do not
add skills, tools, employers, or achievements that are not present there.
If the job description asks for something not covered by the source
material, leave it out rather than inventing it; that gap will be
reported separately.
"""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

SOURCE MATERIAL (the only facts you may draw from):
{source_block}

USER PREFERENCES:
{pref_block}

Write the tailored resume now, in markdown, with clear section headers.
Order and select bullets to best match this specific job description,
prioritizing the most relevant projects/experience first.
"""
    return _chat(system_prompt, user_prompt)


def generate_cover_letter(jd_text: str, resume_markdown: str, preferences: list, tone_sample: str = None):
    pref_block = "\n".join(f"- {p}" for p in preferences) or "(none set yet)"
    tone_block = (
        f"\nHere is a sample of the user's own past writing, match this voice:\n{tone_sample}\n"
        if tone_sample else ""
    )

    system_prompt = f"""You write short, specific, honest cover letters.
{STYLE_RULES}
Keep it under 300 words. No generic opening like "I am excited to apply".
Reference one or two specific, true details from the resume that connect
directly to this job description. Do not restate the whole resume.
"""

    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

CANDIDATE'S TAILORED RESUME (only true facts, use only these):
{resume_markdown}

USER PREFERENCES:
{pref_block}
{tone_block}
Write the cover letter now.
"""
    return _chat(system_prompt, user_prompt)


def truth_check(resume_markdown: str, retrieved_items: list):
    """
    Compares every factual claim in the generated resume against the
    source material and flags anything that isn't traceable. Returns
    structured JSON: {"passed": bool, "flagged_claims": [...]}
    """
    source_block = "\n".join(f"- {i['content']}" for i in retrieved_items)

    system_prompt = """You are a strict fact-checker. You compare a resume
against a list of source facts. For every concrete claim in the resume
(numbers, technologies, job titles, achievements), determine if it is
directly supported by the source facts, a reasonable rephrasing of them,
or an unsupported addition.
Respond ONLY with valid JSON, no markdown fences, no preamble, in this
exact shape:
{"passed": true/false, "flagged_claims": [{"claim": "...", "reason": "..."}]}
"passed" is true only if flagged_claims is empty.
"""
    user_prompt = f"""SOURCE FACTS:
{source_block}

RESUME TO CHECK:
{resume_markdown}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "passed": False,
            "flagged_claims": [{"claim": "PARSE_ERROR", "reason": raw[:500]}],
        }


def skill_gap_analysis(jd_text: str, retrieved_items: list):
    source_block = "\n".join(f"- {i['content']}" for i in retrieved_items)
    system_prompt = """Compare a job description's requirements against a
candidate's actual background. Respond ONLY with valid JSON, no markdown
fences, in this shape:
{"matched_skills": ["..."], "missing_skills": ["..."], "notes": "one or two honest sentences"}
"""
    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

CANDIDATE BACKGROUND:
{source_block}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"matched_skills": [], "missing_skills": [], "notes": raw[:500]}


def ats_score(jd_text: str, resume_markdown: str):
    system_prompt = """You score how well a resume's wording and structure
will parse and match in a typical ATS (applicant tracking system) for a
given job description. Respond ONLY with valid JSON:
{"score": 0-100, "reasons": ["..."]}
Score based on: keyword overlap with the JD, standard section headers,
no graphics/tables that break parsing, reverse-chronological clarity.
"""
    user_prompt = f"""JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_markdown}

Return the JSON now.
"""
    raw = _chat(system_prompt, user_prompt, temperature=0.0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": None, "reasons": [raw[:500]]}
