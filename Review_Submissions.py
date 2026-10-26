from brand import header_logo
"""Account-restricted resource management."""
from datetime import date
import streamlit as st
from auth import is_admin
from database import initialize, load_admin_resources, set_status, update_resource, delete_resource

st.set_page_config(page_title="Manage resources · CommunityConnect", layout="wide")
if not is_admin():
    st.error("Administrator access required.")
    st.stop()
initialize()
st.markdown(f'<div class="cc-header">{header_logo()}<div><div class="cc-eyebrow">Community curation</div><h1>Manage resources</h1><p>Review submissions and keep local information useful.</p></div></div>', unsafe_allow_html=True)
view = st.selectbox("Show", ["Pending", "Approved", "Rejected", "All"])
rows = load_admin_resources()
rows = [row for row in rows if view == "All" or row["status"] == view.lower()]
st.caption(f"{len(rows)} resources")
if not rows:
    st.info("No resources in this view.")

for row in rows:
    resource_id = row["id"]
    with st.container(border=True, key=f"review_card_{resource_id}"):
        st.subheader(row["name"])
        st.caption(f'{row["category"]} · {row["city"]} · {row["status"]}')
        st.write(row["description"])
        with st.expander("Edit resource or submission"):
            with st.form(f"edit_{resource_id}", clear_on_submit=False):
                fields = {}
                for field, label in [("name", "Name"), ("summary", "Summary"), ("description", "Description"), ("address", "Address"), ("city", "City"), ("state", "State"), ("zip", "ZIP"), ("phone", "Phone"), ("hours", "Hours"), ("link", "Website or registration link")]:
                    widget = st.text_area if field == "description" else st.text_input
                    fields[field] = widget(label, value=row[field] or "", key=f"edit_{resource_id}_{field}")
                options = list(dict.fromkeys([row["category"], "Food", "Health", "Student", "School", "Parks", "Events"]))
                fields["category"] = st.selectbox("Category", options, key=f"category_{resource_id}")
                fields["free"] = st.checkbox("Free", value=bool(row["free"]), key=f"free_{resource_id}")
                start = st.date_input("Event date (leave empty for an ongoing program)", value=date.fromisoformat(row["event_date"]) if row["event_date"] else None, key=f"start_{resource_id}")
                end = st.date_input("End date (optional)", value=date.fromisoformat(row["event_end_date"]) if row["event_end_date"] else None, key=f"end_{resource_id}")
                save = st.form_submit_button("Save changes")
            if save:
                if any(not fields[field].strip() for field in ("name", "summary", "description", "address", "city", "state", "zip", "phone", "hours")):
                    st.error("Fill in all fields except the website and dates.")
                elif end and (not start or end < start):
                    st.error("Choose a start date and an end date on or after it.")
                elif fields["link"] and not fields["link"].startswith(("http://", "https://")):
                    st.error("Website must start with http:// or https://.")
                else:
                    fields.update(event_date=start.isoformat() if start else None, event_end_date=end.isoformat() if end else None)
                    update_resource(resource_id, **fields)
                    st.rerun()
        with st.container(horizontal=True):
            if row["status"] != "approved" and st.button("Approve", key=f"approve_{resource_id}"):
                set_status(resource_id, "approved")
                st.rerun()
            if row["status"] != "rejected" and st.button("Reject", key=f"reject_{resource_id}"):
                set_status(resource_id, "rejected")
                st.rerun()
        with st.expander("Delete resource"):
            confirmed = st.checkbox("Permanently delete this resource", key=f"confirm_delete_{resource_id}")
            if st.button("Delete", key=f"delete_{resource_id}", disabled=not confirmed):
                delete_resource(resource_id)
                st.rerun()