from brand import header_logo
"""CommunityConnect: submit a new resource or event (goes to the approval queue)."""

from datetime import date

import streamlit as st

from database import add_resource, initialize

st.set_page_config(page_title="Submit a Resource · CommunityConnect")
initialize()


st.markdown(f'<div class="cc-header">{header_logo()}<div><div class="cc-eyebrow">Share something helpful</div><h1>Add a resource or event</h1><p>Help your neighbors discover what is available nearby.</p></div></div>', unsafe_allow_html=True)
st.caption(
    "Know a food bank, clinic, program, or event that isn't listed yet? Add it here. "
    "New submissions are reviewed before they appear on the main page. You won't see "
    "it in the list right away."
)

event_type = st.radio(
    "Schedule", ["Ongoing program", "One-time event", "Multiple dates"],
    horizontal=True, key="submission_event_type"
)

with st.form("submit_resource", clear_on_submit=False):
    name = st.text_input("Name*", placeholder="e.g. Westside Food Pantry")
    category = st.selectbox("Category*", ["Food", "Health", "Student", "Parks", "Events"])
    summary = st.text_input("One-line summary*", placeholder="A short description shown on the card")
    description = st.text_area("Full description*", placeholder="More detail: who it's for, what to expect, requirements, etc.")

    col1, col2 = st.columns(2)
    address = col1.text_input("Street address*", placeholder="123 Main St")
    phone = col2.text_input("Contact phone*", placeholder="(000) 000-0000")

    col3, col4, col5 = st.columns([2, 1, 1])
    city = col3.text_input("City*", placeholder="McAllen")
    state = col4.text_input("State*", placeholder="TX", max_chars=2)
    zip_code = col5.text_input("ZIP*", placeholder="78501", max_chars=10)

    hours = st.text_input("Hours*", placeholder="e.g. Weekdays, 9 AM–3 PM or 10 AM–noon")
    free = st.checkbox("This is free", value=True)

    event_date = None
    event_end_date = None
    if event_type == "One-time event":
        event_date = st.date_input("Event date", value=date.today(), key="submission_single_date", format="MM/DD/YYYY")
    elif event_type == "Multiple dates":
        period = st.date_input(
            "Event period", value=(date.today(), date.today()),
            key="submission_date_range", format="MM/DD/YYYY",
            help="Select a start date and an end date."
        )
        if len(period) == 2:
            event_date, event_end_date = period

    link = st.text_input("Website or registration link", placeholder="https://...")

    submitted = st.form_submit_button("Submit for review", width="stretch")

if submitted:
    required = {
        "Name": name, "Summary": summary, "Description": description, "Address": address,
        "City": city, "State": state, "ZIP": zip_code, "Phone": phone, "Hours": hours,
    }
    missing = [label for label, value in required.items() if not value.strip()]
    if missing:
        st.error(f"Please fill in: {', '.join(missing)}.")
    elif event_type == "Multiple dates" and (event_date is None or event_end_date is None):
        st.error("Select both a start date and an end date.")
    elif event_end_date and event_end_date < event_date:
        st.error("The end date must be on or after the start date.")
    elif link and not (link.startswith("http://") or link.startswith("https://")):
        st.error("Link should start with http:// or https://, or be left blank.")
    else:
        add_resource(
            name=name.strip(),
            category=category,
            description=description.strip(),
            summary=summary.strip(),
            address=address.strip(),
            city=city.strip(),
            state=state.strip().upper(),
            zip_code=zip_code.strip(),
            phone=phone.strip(),
            hours=hours.strip(),
            free=free,
            event_date=event_date.isoformat() if event_date else None,
            event_end_date=event_end_date.isoformat() if event_end_date else None,
            link=link.strip(),
        )
        st.success(f'Thanks! "{name.strip()}" was submitted and is waiting for review before it appears in the list.')