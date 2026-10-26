from brand import header_logo
from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode
import math

import pydeck as pdk
import streamlit as st

from ask_ai import ask, public_rows
from database import initialize, load_resources
from geocode import locate_rows
from translations import format_date, translate_rows

TEXT = {
    "en": {
        "eyebrow": "Your local community, connected", "tagline": "Find help. Discover programs. Make plans nearby.",
        "find_resources": "Find resources", "events": "Events", "ask_ai": "Ask AI", "saved": "Saved",
        "submit": "Submit a resource", "manage": "Manage resources", "other_language": "Español",
        "find_what": "Find what you need", "place": "City or ZIP code", "category": "Category", "all": "All",
        "free_only": "Free only", "when": "When", "anytime": "Anytime", "next_7": "Next 7 days", "next_30": "Next 30 days",
        "place_hint": "McAllen or 78501", "keyword": "Search by word", "keyword_hint": "Tutoring, Food, Screening...", "show_map": "Show map", "map_hint": "Hover over a circle for details, or click it to see the full listing.", "map_selected": "Selected on the map",
        "results_one": "1 result", "results_many": "{n} results", "in_place": " in {place}", "across": " across cities",
        "events_one": "1 upcoming event", "events_many": "{n} upcoming events",
        "no_results": "No listings match these filters. Try another city/ZIP, category, or time range. Demo cities: McAllen, Brownsville, and Edinburg.",
        "no_saved": "Nothing saved yet. Use ♡ Save on any listing to keep it here for this session.",
        "no_map": "These listings don't have a city we can place on the map yet.",
        "free": "Free", "fees": "Fees may apply", "event_period": "Event period", "address": "Address",
        "contact": "Contact", "more_info": "More info / registration", "directions": "↗ Directions",
        "save": "♡ Save", "saved_btn": "❤️ Saved", "calendar": "+ Add to calendar",
        "ask_title": "Ask CommunityConnect",
        "ask_sub": "Describe what you need in your own words and we'll look up resources across the valley.",
        "ask_label": "What do you need help with?", "ask_placeholder": "e.g. I need help with food...",
        "ask_button": "Ask", "ask_try": "Try asking:", "ask_thinking": "Looking through community resources...",
        "ask_new": "Start over", "ask_matches": "Resources that may help", "ask_you_asked": "You asked",
        "ask_disclaimer": "AI answers can make mistakes. Call ahead to confirm hours and eligibility.",
        "suggestions": ["I need help paying my rent this month", "Where can my kids go after school?",
                        "Necesito comida gratis para mi familia", "I want to get my GED in English",
                        "Free healthcare clinic near McAllen",],
    },
    "es": {
        "eyebrow": "Tu comunidad local, conectada", "tagline": "Encuentra ayuda. Descubre programas. Haz planes cerca de ti.",
        "find_resources": "Buscar recursos", "events": "Eventos", "ask_ai": "Pregunta a la IA", "saved": "Guardados",
        "submit": "Enviar un recurso", "manage": "Administrar recursos", "other_language": "English",
        "find_what": "Encuentra lo que necesitas", "place": "Ciudad o código postal", "category": "Categoría",
        "all": "Todas", "free_only": "Solo gratis", "when": "Cuándo", "anytime": "Cualquier fecha",
        "next_7": "Próximos 7 días", "next_30": "Próximos 30 días", "place_hint": "McAllen o 78501", "keyword": "Buscar por palabra",
        "keyword_hint": "Tutoría, comida, exámenes...", "show_map": "Mostrar mapa", "map_hint": "Pasa el cursor sobre un círculo para ver detalles, o haz clic para ver el recurso completo.", "map_selected": "Seleccionado en el mapa",
        "results_one": "1 resultado", "results_many": "{n} resultados", "in_place": " en {place}",
        "across": " en todas las ciudades", "events_one": "1 evento próximo", "events_many": "{n} eventos próximos",
        "no_results": "Ningún resultado coincide con estos filtros. Prueba otra ciudad/código postal, categoría o fecha. Ciudades de demostración: McAllen, Brownsville y Edinburg.",
        "no_saved": "Aún no has guardado nada. Usa ♡ Guardar en cualquier recurso para tenerlo aquí durante esta sesión.",
        "no_map": "Todavía no podemos ubicar la ciudad de estos resultados en el mapa.",
        "free": "Gratis", "fees": "Puede tener costo", "event_period": "Periodo del evento", "address": "Dirección",
        "contact": "Contacto", "more_info": "Más información / registro", "directions": "↗ Cómo llegar",
        "save": "♡ Guardar", "saved_btn": "❤️ Guardado", "calendar": "+ Agregar al calendario",
        "ask_title": "Pregúntale a CommunityConnect",
        "ask_sub": "Describe lo que necesitas con tus propias palabras y buscaremos recursos en todo el Valle.",
        "ask_label": "¿Con qué necesitas ayuda?", "ask_placeholder": "p. ej. Necesito ayuda con comida...",
        "ask_button": "Preguntar", "ask_try": "Prueba preguntar:", "ask_thinking": "Buscando recursos comunitarios...",
        "ask_new": "Empezar de nuevo", "ask_matches": "Recursos que pueden ayudarte", "ask_you_asked": "Preguntaste",
        "ask_disclaimer": "La IA puede cometer errores. Llama antes de ir para confirmar horarios y requisitos.",
        "suggestions": ["Necesito ayuda para pagar la renta este mes", "¿A dónde pueden ir mis hijos después de la escuela?",
                        "Necesito comida gratis para mi familia", "Quiero obtener mi GED en inglés",
                        "Clínica de salud gratuita cerca de McAllen", "Ayuda con preguntas de inmigración"],
    },
}
CATEGORY_NAMES_ES = {"Food": "Comida", "Health": "Salud", "Student": "Estudiantes", "Youth": "Jóvenes",
                     "Parks": "Parques", "Events": "Eventos"}
ICONS = {"Food": "nutrition", "Health": "medical_services", "Student": "school", "Youth": "family_restroom",
         "Parks": "park", "Events": "celebration"}

def lang():
    return st.session_state.get("lang", "en")


def t(key):
    # Fall back to English (then the key itself) so a missing translation never crashes a page.
    return TEXT.get(lang(), TEXT["en"]).get(key, TEXT["en"].get(key, key))


def category_name(category):
    return CATEGORY_NAMES_ES.get(category, category) if lang() == "es" else category


def page_header():
    st.markdown(f'<div class="cc-header">{header_logo()}<div><div class="cc-eyebrow">{escape(t("eyebrow"))}</div>'
                f'<h1>CommunityConnect</h1><p>{escape(t("tagline"))}</p></div></div>', unsafe_allow_html=True)


def calendar_url(row):
    """Build a Google Calendar 'add event' link. Uses the event date when one exists,
    otherwise defaults to today so a recurring program can still be added as a reminder."""
    event_day = date.fromisoformat(row["event_date"]) if row["event_date"] else date.today()
    start = event_day.strftime("%Y%m%d")
    last_day = date.fromisoformat(row["event_end_date"]) if row["event_end_date"] else event_day
    end = (last_day + timedelta(days=1)).strftime("%Y%m%d")
    details = f'{row["description"]} Hours: {row["hours"]}.'
    location = f'{row["address"]}, {row["city"]}, {row["state"]} {row["zip"]}'
    params = {
        "action": "TEMPLATE",
        "text": row["name"],
        "dates": f"{start}/{end}",
        "details": details,
        "location": location,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def resource_card(row, key_prefix):
    with st.container(border=True, key=f'resource_card_{key_prefix}_{row["id"]}'):
        icon = ICONS.get(row["category"], "location_on")
        st.markdown(f'### <i class="cc-ico" aria-hidden="true">{icon}</i> {escape(row["name"])}', unsafe_allow_html=True)
        st.caption(f'{category_name(row["category"])} · {row["city"]}, {row["state"]} {row["zip"]} · {t("free") if row["free"] else t("fees")}')
        if row["event_date"]:
            if row["event_end_date"]:
                st.caption(f'{t("event_period")}: {format_date(date.fromisoformat(row["event_date"]), lang() == "es")} – {format_date(date.fromisoformat(row["event_end_date"]), lang() == "es")}')
            st.markdown(f'<i class="cc-ico" aria-label="date">calendar_month</i> {format_date(date.fromisoformat(row["event_date"]), lang() == "es")} &middot; {escape(row["hours"])}', unsafe_allow_html=True)
        else:
            st.markdown(f'<i class="cc-ico" aria-label="hours">schedule</i> {escape(row["hours"])}', unsafe_allow_html=True)
        st.write(row["description"])
        st.markdown(
            f'<i class="cc-ico" aria-label="address">apartment</i> **{t("address")}:** {escape(row["address"])}, {escape(row["city"])}, {row["state"]} {row["zip"]}  \n'
            f'<i class="cc-ico" aria-label="contact">call</i> **{t("contact")}:** {escape(row["phone"])}',
            unsafe_allow_html=True,
        )
        if row["link"]:
            st.markdown(f'<i class="cc-ico" aria-label="link">link</i> [{t("more_info")}]({row["link"]})', unsafe_allow_html=True)
        left, middle, right = st.columns(3)
        destination = f'{row["address"]}, {row["city"]}, {row["state"]} {row["zip"]}'
        maps_url = "https://www.google.com/maps/dir/?" + urlencode({"api": "1", "destination": destination})
        left.link_button(t("directions"), maps_url, use_container_width=True)
        if middle.button(t("saved_btn") if row["id"] in st.session_state.saved else t("save"),
                         key=f'save_{key_prefix}_{row["id"]}', use_container_width=True):
            st.session_state.saved.symmetric_difference_update({row["id"]})
            st.rerun()
        right.link_button(t("calendar"), calendar_url(row), use_container_width=True)


def resource_map(rows, key_prefix):
    """Clickable map with one circle per listing. Circles are sized in meters, so they shrink and grow with zoom."""
    coords = locate_rows(rows)
    groups = {}
    for row in rows:
        if row["id"] in coords:
            groups.setdefault(coords[row["id"]], []).append(row)
    points = []
    for (lat, lon), group in groups.items():
        for index, row in enumerate(group):
            # Spread listings that share an address or city center in a small ring so each circle can be clicked.
            angle = 2 * math.pi * index / len(group)
            spread = 0.006 if len(group) > 1 else 0
            when = (format_date(date.fromisoformat(row["event_date"]), lang() == "es") + " · " if row["event_date"] else "") + row["hours"]
            points.append({
                "id": row["id"], "lat": lat + spread * math.sin(angle), "lon": lon + spread * math.cos(angle),
                "name": escape(row["name"]), "when": escape(when), "category": escape(category_name(row["category"])),
                "address": escape(f'{row["address"]}, {row["city"]}'),
            })
    if not points:
        st.info(t("no_map"))
        return
    layer = pdk.Layer(
        "ScatterplotLayer", id="listings", data=points, get_position="[lon, lat]",
        get_radius=600, radius_min_pixels=6, radius_max_pixels=30,  # radius is in meters (pydeck's default unit)
        get_fill_color=[22, 138, 130, 190], get_line_color=[255, 255, 255, 230],
        stroked=True, line_width_min_pixels=1.5, pickable=True, auto_highlight=True,
        highlight_color=[16, 93, 105, 255],
    )
    # Fit the starting view to the listings (roughly a 900x380 px map), between region and neighborhood zoom.
    lats, lons = [p["lat"] for p in points], [p["lon"] for p in points]
    center_lat = (max(lats) + min(lats)) / 2
    lon_span = max(max(lons) - min(lons), 0.01)
    lat_span = max(max(lats) - min(lats), 0.01) / math.cos(math.radians(center_lat))
    zoom = min(math.log2(900 * 360 / (512 * lon_span)), math.log2(380 * 360 / (512 * lat_span))) - 0.3
    view = pdk.ViewState(latitude=center_lat, longitude=(max(lons) + min(lons)) / 2, zoom=max(7, min(zoom, 12)))
    tooltip = {"html": "<b>{name}</b><br/>{category} · {when}<br/>{address}",
               "style": {"backgroundColor": "#105d69", "color": "white", "fontSize": "13px", "borderRadius": "8px"}}
    event = st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip, map_style="light"),
                            on_select="rerun", selection_mode="single-object", key=f"listing_map_{key_prefix}", height=420)
    st.caption(t("map_hint"))
    selected = event.selection.objects.get("listings", []) if event and event.selection else []
    if selected:
        by_id = {row["id"]: row for row in rows}
        if selected[0]["id"] in by_id:
            st.markdown(f"**{t('map_selected')}**")
            resource_card(by_id[selected[0]["id"]], f"{key_prefix}_map")
            st.divider()


def current_rows():
    initialize()
    return translate_rows(public_rows(load_resources()), spanish=lang() == "es")


def listing_page(rows, key_prefix, events=False):
    page_header()
    today = date.today()
    with st.sidebar:
        st.header(t("find_what"))
        place = st.text_input(t("place"), placeholder=t("place_hint"), key=f"place_{key_prefix}")
        category = "All"
        if not events:
            categories = ["All"] + sorted({row["category"] for row in rows})
            category = st.selectbox(t("category"), categories, key=f"category_{key_prefix}_{lang()}",
                                    format_func=lambda c: t("all") if c == "All" else category_name(c))
        free_only = st.checkbox(t("free_only"), key=f"free_{key_prefix}")
        timing = "anytime"
        if events:
            timing = st.selectbox(t("when"), ["anytime", "next_7", "next_30"], format_func=t,
                                  key=f"when_{key_prefix}_{lang()}")
        keyword = st.text_input(t("keyword"), placeholder=t("keyword_hint"), key=f"keyword_{key_prefix}")
        show_map = st.toggle(t("show_map"), key=f"map_{key_prefix}")
        st.divider()

    def matches(row):
        q = place.strip().casefold()
        city = row["city"].casefold()
        location_ok = not q or q == row["zip"] or q == city or q == f'{city}, {row["state"].casefold()}'
        if not location_ok or (category != "All" and row["category"] != category):
            return False
        if free_only and not row["free"]:
            return False
        if keyword and keyword.casefold() not in " ".join(str(row[k]) for k in ("name", "category", "summary", "description")).casefold():
            return False
        if timing != "anytime":
            limit = today + timedelta(days=7 if timing == "next_7" else 30)
            if date.fromisoformat(row["event_date"]) > limit:
                return False
        return True

    results = [row for row in rows if matches(row)]
    n = len(results)
    if events:
        heading = t("events_one") if n == 1 else t("events_many").format(n=n)
    else:
        heading = t("results_one") if n == 1 else t("results_many").format(n=n)
    heading += t("in_place").format(place=place.strip()) if place.strip() else t("across")
    st.subheader(heading)
    if not results:
        st.info(t("no_results"))
        return
    if show_map:
        resource_map(results, key_prefix)
    for row in results:
        resource_card(row, key_prefix)


def browse_resources():
    listing_page(current_rows(), "res")


def browse_events():
    rows = sorted((row for row in current_rows() if row["event_date"]), key=lambda row: row["event_date"])
    listing_page(rows, "evt", events=True)


def saved_resources():
    page_header()
    rows = [row for row in current_rows() if row["id"] in st.session_state.saved]
    st.subheader(t("saved"))
    if not rows:
        st.info(t("no_saved"))
    for row in rows:
        resource_card(row, "saved")


def run_question(question):
    question = question.strip()
    if not question:
        return
    with st.spinner(t("ask_thinking")):
        result = ask(question, current_rows(), history=st.session_state.ask_history, spanish=lang() == "es")
    st.session_state.ask_history.append({"question": question, "lang": lang(), **result})


def ask_ai_page():
    if "ask_history" not in st.session_state:
        st.session_state.ask_history = []
    page_header()
    st.subheader(t("ask_title"))
    st.write(t("ask_sub"))
    with st.form("ask_form", clear_on_submit=True):
        question = st.text_input(t("ask_label"), placeholder=t("ask_placeholder"))
        submitted = st.form_submit_button(t("ask_button"), icon=":material/search:")
    if submitted:
        run_question(question)

    st.caption(t("ask_try"))
    with st.container(horizontal=True, key="ask_suggestions"):
        for index, suggestion in enumerate(t("suggestions")):
            if st.button(suggestion, key=f"suggestion_{index}"):
                run_question(suggestion)

    if not st.session_state.ask_history:
        return
    latest = st.session_state.ask_history[-1]
    if latest.get("lang") != lang():
        # The language was switched after asking: answer the same question again in the new language.
        st.session_state.ask_history.pop()
        run_question(latest["question"])
        latest = st.session_state.ask_history[-1]
    with st.container(border=True, key="review_card_ask_answer"):
        st.markdown(f'<i class="cc-ico" aria-hidden="true">auto_awesome</i> **{t("ask_you_asked")}:** {escape(latest["question"])}',
                    unsafe_allow_html=True)
        st.markdown(latest["answer"])
        st.caption(t("ask_disclaimer"))
    rows_by_id = {row["id"]: row for row in current_rows()}
    matched = [rows_by_id[rid] for rid in latest["resource_ids"] if rid in rows_by_id]
    if matched:
        st.subheader(t("ask_matches"))
        for row in matched:
            resource_card(row, f'ask{len(st.session_state.ask_history)}')
    if st.button(t("ask_new"), icon=":material/refresh:", key="ask_reset"):
        st.session_state.ask_history = []
        st.rerun()


from auth import require_account, is_admin

st.set_page_config(page_title="CommunityConnect", page_icon="", layout="wide")
st.markdown("""<style>
:root {color-scheme:light}
.stApp {
    background: #F5FAFE;
    color: #18374b;
}.block-container {max-width:1100px;padding-top:3rem;padding-bottom:2rem}
header[data-testid="stHeader"] {background:transparent}
[data-testid="stSidebar"] {background:#F5FAFE;border-right:1px solid #d4e7e8}
[data-testid="stSidebar"] h2 {font-size:1.2rem;color:#125e65}
h1 {font-size:clamp(1.45rem,4.5vw,2rem)!important;overflow-wrap:anywhere;line-height:1.25!important}
h2 {color:#154b60;font-size:1.35rem!important}
h3 {font-size:1.15rem!important;line-height:1.4!important;overflow-wrap:anywhere}
.cc-ico {font-family:"Material Symbols Rounded";font-style:normal;font-weight:400;line-height:1;letter-spacing:normal;text-transform:none;
 white-space:nowrap;font-feature-settings:"liga";-webkit-font-smoothing:antialiased;vertical-align:-3px;margin-right:4px;color:#168a82;font-size:1.15em}
.cc-header {display:flex;gap:14px;align-items:center;background:linear-gradient(110deg,#105d69,#198d88);padding:20px 24px;border-radius:20px;color:white;box-shadow:0 8px 24px #105d6914;margin-bottom:24px}
.cc-logo {display:grid;place-items:center;flex:0 0 48px;width:48px;height:48px;background:#fff;border:1px solid #ffffff45;border-radius:15px;font-size:22px;font-weight:800;color:white}
.cc-header h1 {color:white!important;margin:0;padding:0;font-size:clamp(1.25rem,4.6vw,1.8rem)!important;line-height:1.25!important;overflow-wrap:anywhere}
.cc-header p {margin:6px 0 0;color:#d9f5ed;font-size:.94rem}
.cc-eyebrow {font-size:.68rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#bceade;margin-bottom:5px}
/* Color the actual keyed Streamlit container, not just an HTML child. */
[class*="st-key-resource_card_"], [class*="st-key-review_card_"],
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-resource_card_"]),
[data-testid="stVerticalBlockBorderWrapper"]:has([class*="st-key-review_card_"]) {
 background:#fff!important;background-image:none!important;border-radius:16px!important;
 border-color:#d7e8e6!important;box-shadow:0 4px 18px #1a4b6310;
}
[class*="st-key-resource_card_"], [class*="st-key-review_card_"] {border-top:3px solid #38afa0!important}
[data-testid="stForm"] {background:white;border:1px solid #d7e8e6;border-radius:16px;padding:20px}
[data-testid="stExpander"] {background:white;border-color:#dbe8ed;border-radius:12px}
[data-testid="stButton"] button,[data-testid="stLinkButton"] a {border-radius:10px;border-color:#c8dddc;color:#125f67;background:#f0faf7;font-weight:600}
[data-testid="stButton"] button:hover,[data-testid="stLinkButton"] a:hover {border-color:#17897e;color:#105d69;background:#e2f5ef}
[data-testid="stFormSubmitButton"] button {background:#147e79;color:white;border:0;border-radius:10px;font-weight:600}
[data-testid="stFormSubmitButton"] button:hover {background:#105d69;color:white}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea {color:#18374b}
[data-testid="stCaptionContainer"] {color:#5c7482}
.st-key-ask_suggestions {gap:.5rem;margin-bottom:1rem}
.st-key-ask_suggestions button {border-radius:999px!important;font-weight:500!important}
.st-key-review_card_ask_answer {margin:1rem 0 1.5rem}
@media(max-width:640px) {
 .block-container {padding:1rem .85rem 2rem}
 .cc-header {padding:16px 14px;gap:10px;border-radius:14px}
 .cc-logo {flex-basis:38px;width:38px;height:38px;border-radius:12px;font-size:18px}
 .cc-header p {font-size:.83rem;line-height:1.5}
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;gap:.6rem}
 [data-testid="stHorizontalBlock"]>[data-testid="stColumn"] {min-width:100%!important;flex:1 1 100%!important}
}
</style>""", unsafe_allow_html=True)
require_account()
if "saved" not in st.session_state:
    st.session_state.saved = set()
with st.sidebar:
    if st.button(t("other_language"), icon=":material/language:", key="language_toggle", use_container_width=True):
        st.session_state.lang = "es" if lang() == "en" else "en"
        st.rerun()
pages = [
    st.Page(browse_resources, title=t("find_resources"), icon=":material/search:", default=True),
    st.Page(browse_events, title=t("events"), icon=":material/event:", url_path="events"),
    st.Page(ask_ai_page, title=t("ask_ai"), icon=":material/auto_awesome:", url_path="ask"),
    st.Page(saved_resources, title=t("saved"), icon=":material/favorite:", url_path="saved"),
    st.Page("Submit_a_Resource.py", title=t("submit"), icon=":material/add_circle:", url_path="submit"),
]
if is_admin():
    pages.append(st.Page("Review_Submissions.py", title=t("manage"), icon=":material/fact_check:", url_path="review"))
navigation = st.navigation(pages)
navigation.run()
