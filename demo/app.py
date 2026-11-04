"""Five-page research dashboard: research, enrollment, Reddit, work, and economy."""
from pathlib import Path
import hmac
import sys
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DEMO_ROOT))
st.set_page_config(page_title="International Student Research", layout="wide")


def app_password() -> str | None:
    """Password from .streamlit/secrets.toml; without one (local runs) the app stays open."""
    try:
        return st.secrets.get("password")
    except FileNotFoundError:
        return None


def login() -> None:
    st.title("International Student Research")
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.authenticated = True
                st.rerun()
            st.error("Incorrect password.")


password = app_password()
if password and not st.session_state.get("authenticated"):
    # Login is the only registered page, so page URLs can't bypass it and no sidebar shows.
    page = st.navigation([st.Page(login, title="Log in")], position="hidden")
else:
    page = st.navigation([
        st.Page(str(DEMO_ROOT / "pages/0_research.py"), title="Research question", default=True),
        st.Page(str(DEMO_ROOT / "pages/1_enrollment.py"), title="Enrollment & new intake"),
        st.Page(str(DEMO_ROOT / "pages/2_discourse.py"), title="Reddit sentiment"),
        st.Page(str(DEMO_ROOT / "pages/3_h1b.py"), title="H-1B"),
        st.Page(str(DEMO_ROOT / "pages/4_economy.py"), title="Economy & policy"),
    ])
page.run()
