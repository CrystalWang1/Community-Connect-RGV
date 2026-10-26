"""Ask AI: Claude answers a resident's question by looking up resources in the database.

Claude gets one tool, search_resources, that runs against the same approved listings shown on
the Resources page. When no API key is configured (or the API is unreachable), a keyword search
over the same data answers instead, so the page still works offline.
"""

import json
import os
import re
from datetime import date

import anthropic
from anthropic import beta_tool

MODEL = "claude-opus-5-5"

# Everyday words (English and Spanish) people use for each category in the database.
SYNONYMS = {
    "Food": "food meal meals groceries grocery pantry hungry hunger eat lunch dinner breakfast snap "
            "comida comidas despensa alimentos hambre mercado",
    "Health": "health healthcare clinic doctor medical medicine screening checkup wellness dental sick nurse "
              "salud clinica clínica médico medico doctor enfermo",
    "Youth": "youth kids kid children child family families teens after-school afterschool homework mentoring camp "
             "niños ninos hijos familia jóvenes jovenes tarea",
    "Student": "student students school tutoring tutor homework learn class classes education ged english esl college "
               "estudiante escuela tutoría tutoria clases educación educacion inglés ingles",
    "Parks": "park parks outdoor outdoors playground walk walking trail nature "
             "parque parques aire libre caminar",
    "Events": "event events festival workshop activity activities weekend fair "
              "evento eventos taller actividad actividades",
}
STOPWORDS = set("""a an and are as at be can do for from get go help i in is it me my near need of on or our
please some the this to want where with you your who what when how find looking any free gratis
el la los las un una de del y en para por que me mi mis necesito quiero donde dónde hay con""".split())

SYSTEM_PROMPT = """You are the Ask AI assistant for CommunityConnect, a directory of community \
resources in the Rio Grande Valley of Texas (McAllen, Edinburg, Brownsville, and nearby cities).

Residents describe what they need. Use the search_resources tool to look up listings, then \
recommend the ones that fit. Search more than once when a first search comes back thin: try a \
category, a different wording, or drop the city filter.

Only recommend resources the tool returned. Never invent organizations, phone numbers, hours, or \
eligibility rules. Refer to each resource you recommend with its id in double square brackets, \
like [[3]]; the app turns these into the resource name and shows a card for each one. Keep the \
answer short and practical: a sentence or two on why each resource fits, plus anything worth \
doing first (call ahead, register, bring ID). If nothing in the directory fits, say so plainly \
and suggest dialing 2-1-1 (Texas 2-1-1) for referrals. Do not give legal, medical, or immigration \
advice yourself; point to resources that can help.

Reply in the language the message asks for. Use plain text with short paragraphs or a \
short list; no headings."""


def public_rows(rows, today=None):
    """Approved listings, minus events that have already ended."""
    today = today or date.today()
    result = []
    for row in rows:
        if "status" in row.keys() and row["status"] != "approved":
            continue
        if row["event_date"]:
            last_day = date.fromisoformat(row["event_end_date"] or row["event_date"])
            if last_day < today:
                continue
        result.append(row)
    return result


def _words(text):
    return [w for w in re.findall(r"[\wáéíóúñü-]+", text.casefold()) if w not in STOPWORDS and len(w) > 1]


def _haystack(row):
    fields = ("name", "category", "summary", "description", "city", "zip", "hours")
    return " ".join(str(row[k]) for k in fields).casefold() + " " + SYNONYMS.get(row["category"], "")


def search(rows, query="", category="", city="", free_only=False, limit=8):
    """Rank listings by how many query words they match (including category synonyms)."""
    matches = []
    for row in rows:
        if category and row["category"].casefold() != category.casefold():
            continue
        if city and city.casefold() not in (row["city"].casefold(), row["zip"]):
            continue
        if free_only and not row["free"]:
            continue
        words = _words(query)
        haystack = _haystack(row)
        score = sum(1 for w in words if w in haystack)
        if words and not score:
            continue
        matches.append((score, row))
    matches.sort(key=lambda pair: -pair[0])
    best = matches[0][0] if matches else 0
    # Drop weak matches (e.g. a listing that only shares the city name) when stronger ones exist.
    return [row for score, row in matches if score * 2 >= best][:limit]


def describe(row):
    return {
        "id": row["id"], "name": row["name"], "category": row["category"],
        "description": row["description"], "summary": row["summary"],
        "address": f'{row["address"]}, {row["city"]}, {row["state"]} {row["zip"]}',
        "phone": row["phone"], "hours": row["hours"], "free": bool(row["free"]),
        "event_date": row["event_date"], "event_end_date": row["event_end_date"],
        "link": row["link"],
    }


def api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def cited_ids(text, valid_ids):
    seen = []
    for match in re.findall(r"\[\[(\d+)\]\]", text):
        rid = int(match)
        if rid in valid_ids and rid not in seen:
            seen.append(rid)
    return seen


def render_citations(text, rows_by_id):
    """Swap [[id]] markers for bold resource names (unknown ids are dropped)."""
    def name(match):
        row = rows_by_id.get(int(match.group(1)))
        return f'**{row["name"]}**' if row else ""
    return re.sub(r"\[\[(\d+)\]\]", name, text)


def ask(question, rows, history=(), spanish=False):
    """Answer a question. Returns {"answer", "resource_ids", "source"}.

    history holds earlier {"question", "answer"} turns so follow-up questions keep their context.
    """
    rows = public_rows(rows)
    rows_by_id = {row["id"]: row for row in rows}
    if not api_key():
        return local_answer(question, rows, spanish)
    try:
        return claude_answer(question, rows, rows_by_id, history, spanish)
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        # Bad key, rate limit, or no connection: answer with the keyword search instead.
        return local_answer(question, rows, spanish)


def claude_answer(question, rows, rows_by_id, history, spanish=False):
    cities = sorted({row["city"] for row in rows})
    categories = sorted({row["category"] for row in rows})

    @beta_tool
    def search_resources(query: str = "", category: str = "", city: str = "", free_only: bool = False) -> str:
        """Search the CommunityConnect directory of Rio Grande Valley resources and events.

        Matches words against each listing's name, category, description, city, ZIP code and hours,
        and understands common English and Spanish words for each category. Leave query empty to
        list everything in a category or city.

        Args:
            query: Keywords describing the need, e.g. "after school tutoring" or "comida".
            category: Optional exact category filter.
            city: Optional city name or 5-digit ZIP code filter.
            free_only: Only return listings that are free.
        """
        found = search(rows, query, category, city, free_only)
        return json.dumps({"results": [describe(row) for row in found], "count": len(found)})

    language = ("The resident is using the Spanish version of the site, so reply in Spanish."
                if spanish else "Reply in the language the resident wrote in.")
    context = (f"Today is {date.today():%A, %B %d, %Y}. Categories in the directory: "
               f"{', '.join(categories)}. Cities covered: {', '.join(cities)}. {language}")
    messages = []
    for turn in history[-4:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["raw_answer"]})
    messages.append({"role": "user", "content": f"{context}\n\n{question}"})

    client = anthropic.Anthropic(api_key=api_key())
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[search_resources],
        messages=messages,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    final = None
    for message in runner:
        final = message
    if final is None or final.stop_reason == "refusal":
        answer = ("Lo siento, no puedo ayudar con esa solicitud. Intenta describir el tipo de ayuda que necesitas, "
                  "como comida, atención médica o programas después de la escuela." if spanish else
                  "Sorry, I can't help with that request. Try describing the kind of help you need, "
                  "like food, health care, or after-school programs.")
        return {"answer": answer, "raw_answer": answer, "resource_ids": [], "source": "ai"}
    raw = "\n\n".join(block.text for block in final.content if block.type == "text").strip()
    return {"answer": render_citations(raw, rows_by_id), "raw_answer": raw,
            "resource_ids": cited_ids(raw, rows_by_id.keys()), "source": "ai"}


SPANISH_HINTS = set("necesito quiero ayuda dónde donde comida para mis hijos familia gratis gratuita clínica cerca "
                    "renta escuela inglés trabajo cómo puedo".split())


def looks_spanish(text):
    return len(SPANISH_HINTS & set(text.casefold().replace("¿", " ").replace("?", " ").split())) >= 2


def local_answer(question, rows, spanish):
    spanish = spanish or looks_spanish(question)
    found = search(rows, question, limit=6)
    if found:
        answer = ("Estos recursos podrían ayudarte. Llama antes de ir para confirmar el horario y los requisitos."
                  if spanish else
                  "These resources may help. Call ahead to confirm hours and any requirements before you go.")
    else:
        answer = ("No encontré un recurso que coincida en el directorio. Llama al 2-1-1 (Texas 2-1-1) para recibir "
                  "referencias a programas cerca de ti." if spanish else
                  "I couldn't find a matching resource in the directory. Dial 2-1-1 (Texas 2-1-1) to get referrals "
                  "to programs near you.")
    return {"answer": answer, "raw_answer": answer, "resource_ids": [row["id"] for row in found], "source": "search"}
