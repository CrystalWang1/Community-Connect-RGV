"""Spanish versions of listing text (descriptions, summaries, hours).

Translations are looked up in this order:
1. A `translations` table in resources.db (a cache; created automatically, existing tables are untouched).
2. The built-in SEED_ES table below, which covers the sample listings.
3. Claude, when an API key is set: every missing string is translated in one request and saved to the cache,
   so each new listing is only translated once.
4. A small word-by-word fallback for hours ("Mon–Thu, 10 AM–4 PM"), so hours read in Spanish even offline.
Organization names and street addresses are proper nouns and stay as written.
"""

import re
import sqlite3
from contextlib import closing

import anthropic
from pydantic import BaseModel

from ask_ai import api_key
from database import DB_PATH

MODEL = "claude-opus-5-5"
FIELDS = ("description", "summary", "hours")

SEED_ES = {
    # Descriptions
    "Weekly grocery pickup for households. Check availability before visiting.":
        "Recogida semanal de alimentos para familias. Confirma la disponibilidad antes de ir.",
    "Basic health screenings and information sessions for residents.":
        "Exámenes básicos de salud y sesiones informativas para residentes.",
    "After-school homework support for grades 3–8; registration is requested.":
        "Apoyo con la tarea después de la escuela para los grados 3 a 8; se pide inscripción.",
    "Outdoor playground and walking area. Some organized activities may charge a fee.":
        "Área de juegos al aire libre y zona para caminar. Algunas actividades organizadas pueden tener costo.",
    "A guided family nature walk. Registration is requested.":
        "Una caminata guiada por la naturaleza para familias. Se pide inscripción.",
    "Pantry support for local households; supplies vary.":
        "Despensa de alimentos para familias locales; los productos disponibles varían.",
    "Family art activities and a community workshop.":
        "Actividades de arte para familias y un taller comunitario.",
    "Tutoring, games, and supervised enrichment for school-age children.":
        "Tutoría, juegos y actividades supervisadas para niños en edad escolar.",
    "Community health screening event; advance registration preferred.":
        "Evento comunitario de exámenes de salud; se prefiere inscripción previa.",
    # Summaries
    "Offers grocery pickup for families. Call ahead to confirm hours and requirements.":
        "Ofrece recogida de alimentos para familias. Llama antes para confirmar horario y requisitos.",
    "Offers basic health screenings and help finding follow-up care.":
        "Ofrece exámenes básicos de salud y ayuda para encontrar atención de seguimiento.",
    "Homework help for grades 3–8 after school. Registration requested.":
        "Ayuda con la tarea para los grados 3 a 8 después de la escuela. Se pide inscripción.",
    "A park with a playground and walking paths. Check activity fees separately.":
        "Un parque con área de juegos y senderos. Consulta por separado el costo de las actividades.",
    "A free guided family nature walk. Sign up before going.":
        "Una caminata guiada gratuita por la naturaleza para familias. Inscríbete antes de ir.",
    "Offers pantry supplies. Call first to check availability.":
        "Ofrece productos de despensa. Llama primero para confirmar disponibilidad.",
    "An afternoon of art activities for families. Some materials may cost extra.":
        "Una tarde de actividades de arte para familias. Algunos materiales pueden tener costo adicional.",
    "After-school tutoring and supervised activities for children.":
        "Tutoría después de la escuela y actividades supervisadas para niños.",
    "Free health screening event. Register in advance if possible.":
        "Evento gratuito de exámenes de salud. Inscríbete con anticipación si es posible.",
    # Hours
    "Weekdays, 9 AM–3 PM": "Lunes a viernes, 9 a. m.–3 p. m.",
    "Mon–Thu, 10 AM–4 PM": "Lun–jue, 10 a. m.–4 p. m.",
    "School days, 3–6 PM": "Días de clases, 3–6 p. m.",
    "Daily, 7 AM–8 PM": "Todos los días, 7 a. m.–8 p. m.",
    "10 AM–noon": "10 a. m.–mediodía",
    "Tue–Fri, 9 AM–2 PM": "Mar–vie, 9 a. m.–2 p. m.",
    "1–4 PM": "1–4 p. m.",
    "9 AM–1 PM": "9 a. m.–1 p. m.",
}

HOURS_WORDS = [
    (r"\bWeekdays\b", "Lunes a viernes"), (r"\bWeekends\b", "Fines de semana"), (r"\bDaily\b", "Todos los días"),
    (r"\bSchool days\b", "Días de clases"), (r"\bBy appointment\b", "Con cita"), (r"\bClosed\b", "Cerrado"),
    (r"\bnoon\b", "mediodía"), (r"\bmidnight\b", "medianoche"), (r"\bAM\b", "a. m."), (r"\bPM\b", "p. m."),
    (r"\bMon(day)?\b", "lun"), (r"\bTue(s|sday)?\b", "mar"), (r"\bWed(nesday)?\b", "mié"),
    (r"\bThu(rs|rsday)?\b", "jue"), (r"\bFri(day)?\b", "vie"), (r"\bSat(urday)?\b", "sáb"), (r"\bSun(day)?\b", "dom"),
    (r"\band\b", "y"), (r"\bto\b", "a"),
]

MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def format_date(day, spanish):
    """'Nov 14, 2026' in English, '14 nov 2026' in Spanish."""
    return f"{day.day} {MONTHS_ES[day.month - 1]} {day.year}" if spanish else day.strftime("%b %d, %Y")


def _hours_fallback(text):
    for pattern, replacement in HOURS_WORDS:
        text = re.sub(pattern, replacement, text)
    return text


def _load_cache(sources):
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS translations (
            lang TEXT NOT NULL, source TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY (lang, source))""")
        found = {}
        for source in sources:
            row = connection.execute("SELECT text FROM translations WHERE lang = 'es' AND source = ?",
                                     (source,)).fetchone()
            if row:
                found[source] = row[0]
    return found


def _save_cache(pairs):
    with closing(sqlite3.connect(DB_PATH)) as connection, connection:
        connection.executemany("INSERT OR REPLACE INTO translations (lang, source, text) VALUES ('es', ?, ?)",
                               pairs.items())


class Translation(BaseModel):
    index: int
    spanish: str


class TranslationBatch(BaseModel):
    translations: list[Translation]


def _translate_with_claude(texts):
    """Translate a list of English strings in one request. Returns {english: spanish}."""
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(texts))
    client = anthropic.Anthropic(api_key=api_key())
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        system=("You translate listings for a community resource directory in the Rio Grande Valley of Texas "
                "into clear, friendly Mexican-American Spanish for residents. Keep organization names, street "
                "addresses, phone numbers, URLs and numbers exactly as written. Write times like '9 a. m.–3 p. m.'."),
        messages=[{"role": "user", "content": f"Translate each numbered line to Spanish:\n\n{numbered}"}],
        output_format=TranslationBatch,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return {}
    return {texts[t.index]: t.spanish for t in response.parsed_output.translations if 0 <= t.index < len(texts)}


def spanish_texts(sources):
    """Map each English string to its Spanish version (falls back to the English text if none is available)."""
    sources = {s for s in sources if s}
    result = {s: SEED_ES[s] for s in sources if s in SEED_ES}
    result.update(_load_cache(sources - result.keys()))
    missing = sorted(sources - result.keys())
    if missing and api_key():
        try:
            new = _translate_with_claude(missing)
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            new = {}
        if new:
            _save_cache(new)
            result.update(new)
    return result


def translate_rows(rows, spanish):
    """Return listings as dicts, with description/summary/hours in Spanish when spanish is True."""
    rows = [dict(row) for row in rows]
    if not spanish:
        return rows
    lookup = spanish_texts(row[field] for row in rows for field in FIELDS)
    for row in rows:
        for field in FIELDS:
            text = row[field]
            if text in lookup:
                row[field] = lookup[text]
            elif field == "hours" and text:
                row[field] = _hours_fallback(text)
    return rows
