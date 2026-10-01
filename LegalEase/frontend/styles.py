"""Centralised CSS for LegalEase. All visual styling lives here."""
import streamlit as st

NAVY, DARK_NAVY, GOLD = "#0B2A52", "#071D3A", "#D9A62E"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:wght@500;600;700&display=swap');
:root {{ --navy:{NAVY}; --dark:{DARK_NAVY}; --gold:{GOLD}; --gray:#5F6B7A; --lite:#EAF3FC; --vlite:#F6FAFF; }}

/* ---------- base ---------- */
html, body, [class*="css"], .stApp {{ font-family:'Inter',sans-serif; color:var(--navy); }}
.stApp {{ background:linear-gradient(160deg,#F9FBFF 0%,#EEF4FC 100%); }}
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"] {{ display:none !important; }}
.block-container {{ max-width:1100px; padding:1.2rem 1.5rem 3rem; position:relative; z-index:1; }}

/* ---------- decorative background (pure CSS) ---------- */
.stApp::before, .stApp::after {{ content:""; position:fixed; border-radius:50%; pointer-events:none; z-index:0; }}
.stApp::before {{ width:720px; height:720px; top:-430px; left:-330px;
  background:radial-gradient(circle at 60% 60%,#F4F8FE 0%,#DCE8F7 100%);
  border:4px solid transparent; border-bottom-color:rgba(217,166,46,.55); border-right-color:rgba(217,166,46,.25); }}
.stApp::after {{ width:640px; height:640px; bottom:-380px; right:-260px;
  background:radial-gradient(circle at 40% 40%,#F4F8FE 0%,#D9E6F6 100%);
  border:4px solid transparent; border-top-color:rgba(217,166,46,.5); border-left-color:rgba(217,166,46,.2); }}

/* ---------- typography ---------- */
.le-serif {{ font-family:'Source Serif 4',Georgia,serif; }}
.le-title {{ font-family:'Source Serif 4',serif; font-weight:700; color:var(--dark); text-align:center;
  font-size:2.6rem; margin:.2rem 0 .3rem; line-height:1.15; }}
.le-sub {{ text-align:center; color:var(--gray); font-size:1.1rem; margin-bottom:.6rem; }}
.le-desc {{ text-align:center; color:var(--gray); max-width:720px; margin:0 auto 1.4rem; line-height:1.7; }}
.le-divider {{ display:flex; align-items:center; justify-content:center; gap:10px; margin:.6rem auto 1rem; }}
.le-divider span {{ height:2px; width:110px; background:linear-gradient(90deg,transparent,var(--gold)); }}
.le-divider span:last-child {{ transform:scaleX(-1); }}
.le-divider i {{ width:9px; height:9px; background:var(--gold); transform:rotate(45deg); display:block; }}

/* ---------- cards ---------- */
.le-card {{ background:#fff; border-radius:16px; box-shadow:0 6px 24px rgba(11,42,82,.08); padding:1.2rem 1.4rem; }}
.le-card h3 {{ font-family:'Source Serif 4',serif; margin:0 0 .2rem; font-size:1.15rem; color:var(--dark); }}
.le-card p {{ margin:0 0 .6rem; color:var(--gray); font-size:.88rem; }}
div[data-testid="stForm"] {{ background:#fff; border:none; border-radius:16px; padding:1.6rem 2rem;
  box-shadow:0 6px 24px rgba(11,42,82,.08); max-width:860px; margin:0 auto; }}

/* ---------- inputs ---------- */
label p {{ font-weight:600 !important; color:var(--dark) !important; font-size:.95rem !important; }}
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] {{
  border-radius:8px !important; border:1px solid #D5DEEA !important; background:#fff !important; }}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within {{ border-color:var(--gold) !important; box-shadow:0 0 0 2px rgba(217,166,46,.2) !important; }}
[data-testid="stCaptionContainer"] {{ color:var(--gray); }}

/* ---------- buttons ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius:10px; border:1.5px solid #C9D6E6; background:#fff; color:var(--navy);
  font-weight:500; padding:.5rem 1rem; transition:all .15s; width:100%; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color:var(--gold); color:var(--dark); }}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background:var(--dark); color:#fff !important; border:2px solid var(--gold);
  font-family:'Source Serif 4',serif; font-weight:600; letter-spacing:.08em; font-size:1.05rem;
  padding:.75rem 1.2rem; box-shadow:0 4px 14px rgba(217,166,46,.35); }}
.stButton > button[kind="primary"] p, [data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"] p {{ color:#fff !important; }}
.stButton > button[kind="primary"]:hover {{ background:var(--navy); color:#fff; }}

/* ---------- document paper ---------- */
.le-scroll {{ background:#F1F5FA; border:1px solid #DCE4EF; border-radius:10px; padding:14px; }}
.le-paper {{ background:#fff; height:460px; overflow-y:auto; padding:36px 52px; box-shadow:0 1px 4px rgba(0,0,0,.08);
  font-family:'Times New Roman',Times,serif; color:#111; font-size:15px; line-height:1.5; }}
.le-paper.short {{ height:400px; padding:24px 30px; font-size:14px; }}
.le-paper .t {{ text-align:center; font-weight:700; font-size:1.45em; margin:0 0 4px; letter-spacing:.04em; }}
.le-paper .c {{ margin:0 0 6px; padding-left:2.6em; text-indent:-2.6em; text-align:justify; }}
.le-paper .c .n {{ display:inline-block; width:2.6em; text-indent:0; }}
.le-paper mark.ph {{ background:#FFF0B3; border-bottom:1.5px dashed var(--gold); padding:0 2px; color:inherit; }}
.le-paper .s {{ text-align:center; font-weight:700; margin:0 0 18px; padding-bottom:10px; border-bottom:1.5px solid #222; }}
.le-paper .h {{ font-weight:700; margin:18px 0 4px; letter-spacing:.03em; }}
.le-paper .p {{ margin:0 0 4px; text-align:justify; }}
.le-paper .b {{ margin:0 0 2px 22px; }}
.le-ok {{ background:#E8F7EE; border:1px solid #CDEBD8; color:var(--dark); border-radius:8px; padding:.7rem 1rem;
  font-family:'Source Serif 4',serif; font-weight:600; margin-bottom:.8rem; }}
.le-ok b {{ color:#16A34A; margin-right:8px; }}
.le-warn {{ background:#FFF6DC; border:1px solid #F0DC9C; color:#5C4500; border-radius:8px; padding:.7rem 1rem;
  font-size:.9rem; margin-bottom:.8rem; line-height:1.5; }}
.le-warn code {{ background:#FFEFB8; border-radius:4px; padding:0 4px; color:inherit; }}

/* ---------- features ---------- */
.le-feats {{ display:grid; grid-template-columns:repeat(4,1fr); margin-top:2.5rem; }}
.le-feat {{ text-align:center; padding:0 1rem; border-left:1px solid #DCE4EF; }}
.le-feat:first-child {{ border-left:none; }}
.le-ico {{ width:56px; height:56px; border-radius:50%; background:var(--lite); margin:0 auto .6rem; display:flex; align-items:center; justify-content:center; }}
.le-feat h4 {{ font-family:'Source Serif 4',serif; margin:.2rem 0; font-size:1.02rem; color:var(--dark); }}
.le-feat p {{ color:var(--gray); font-size:.85rem; margin:0; }}
.le-note {{ text-align:center; color:#8A96A6; font-size:.75rem; margin-top:2rem; }}

/* ---------- button layout fixes ---------- */
/* newer Streamlit sizes button wrappers to their text; force full-width so columns line up */
div[data-testid="stElementContainer"]:has(.stButton), div[data-testid="stElementContainer"]:has(.stDownloadButton) {{ width:100% !important; }}
.stButton, .stDownloadButton, div[data-testid="stFormSubmitButton"] {{ width:100% !important; display:flex; }}
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {{
  width:100% !important; min-height:3rem; white-space:nowrap; display:flex; align-items:center; justify-content:center; }}
.stButton > button p, .stDownloadButton > button p {{ margin:0; font-size:.9rem; white-space:nowrap; }}
/* centred hero buttons */
.st-key-start .stButton, .st-key-gen_btn .stButton, div[data-testid="stFormSubmitButton"] {{ justify-content:center; }}
.st-key-start button, .st-key-gen_btn button, div[data-testid="stFormSubmitButton"] > button {{ width:auto !important; min-width:340px; max-width:100%; }}
/* header "Back to Home" sits at the far right */
[class*="st-key-back_"] .stButton {{ justify-content:flex-end; }}
[class*="st-key-back_"] button {{ width:auto !important; padding:.4rem 1.1rem; min-height:2.6rem; }}

/* ---------- stepper ---------- */
.le-steps {{ display:flex; max-width:640px; margin:.2rem auto 1.1rem; }}
.le-step {{ flex:1; display:flex; flex-direction:column; align-items:center; position:relative; font-size:.78rem; color:#8A96A6; gap:.3rem; }}
.le-step b {{ width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:#fff;
  border:2px solid #C9D6E6; font-weight:600; z-index:1; font-size:.85rem; }}
.le-step::before {{ content:""; position:absolute; top:15px; left:-50%; width:100%; height:2px; background:#C9D6E6; }}
.le-step:first-child::before {{ display:none; }}
.le-step.done b {{ background:var(--navy); color:#fff; border-color:var(--navy); }}
.le-step.done::before, .le-step.active::before {{ background:var(--navy); }}
.le-step.active b {{ background:var(--gold); border-color:var(--gold); color:var(--dark); box-shadow:0 0 0 4px rgba(217,166,46,.2); }}
.le-step.active, .le-step.done {{ color:var(--dark); font-weight:600; }}

/* ---------- generator card ---------- */
.st-key-gen_card {{ background:#fff; border-radius:16px; padding:1.5rem 2rem 1.6rem; box-shadow:0 6px 24px rgba(11,42,82,.08);
  max-width:900px; margin:0 auto; }}
.le-sec {{ font-family:'Source Serif 4',serif; font-weight:600; font-size:1.08rem; color:var(--dark); margin:1.4rem 0 .5rem;
  padding-bottom:.4rem; border-bottom:1px solid #E3EAF4; display:flex; align-items:center; gap:.55rem; }}
.le-sec i {{ width:7px; height:7px; background:var(--gold); transform:rotate(45deg); display:inline-block; }}
.le-typedesc {{ color:var(--gray); font-size:.88rem; margin:-.3rem 0 .2rem; }}
.le-hint {{ background:var(--vlite); border:1px dashed #C9D6E6; border-radius:12px; padding:1.6rem 1rem; text-align:center;
  color:var(--gray); margin:1.2rem 0 .4rem; }}
.le-prog-label {{ display:flex; justify-content:space-between; font-size:.82rem; color:var(--gray); margin:1.4rem 0 .35rem; }}
.le-prog {{ height:8px; background:#E3EAF4; border-radius:99px; overflow:hidden; margin-bottom:1.1rem; }}
.le-prog div {{ height:100%; background:linear-gradient(90deg,var(--gold),#E8C063); border-radius:99px; transition:width .25s; }}
.le-prog.full div {{ background:linear-gradient(90deg,#16A34A,#4ADE80); }}

/* ---------- info chips ---------- */
.le-chips {{ display:flex; flex-wrap:wrap; gap:.45rem; justify-content:center; margin:0 0 1rem; }}
.le-chip {{ background:#fff; border:1px solid #DCE4EF; color:var(--navy); border-radius:999px; padding:.2rem .85rem; font-size:.8rem; font-weight:500; }}
.le-chip.gold {{ background:#FFF6DC; border-color:#F0DC9C; color:#5C4500; }}

/* ---------- edit page: sticky action bar (Save is always on screen) ---------- */
.st-key-editbar {{ position:sticky; top:0; z-index:100; background:rgba(249,251,255,.95); backdrop-filter:blur(8px);
  border-bottom:1px solid #DCE4EF; padding:.55rem .2rem; margin:0 0 1rem; }}
.st-key-editbar button {{ min-height:2.7rem !important; }}
.le-state {{ font-size:.9rem; font-weight:600; display:flex; align-items:center; gap:.5rem; }}
.le-state i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
.le-state.dirty {{ color:#7A5A00; }} .le-state.dirty i {{ background:var(--gold); box-shadow:0 0 0 4px rgba(217,166,46,.25); }}
.le-state.clean {{ color:#136B3A; }} .le-state.clean i {{ background:#16A34A; }}

/* ---------- text-style link buttons ---------- */
.st-key-link_row button {{ border:none !important; background:transparent !important; color:var(--gray) !important;
  min-height:2rem !important; text-decoration:underline; box-shadow:none !important; }}
.st-key-link_row button:hover {{ color:var(--dark) !important; }}

/* ---------- India notices, review, saved documents ---------- */
.le-legal {{ background:#FFF9E8; border:1px solid #F0DC9C; border-left:5px solid var(--gold); color:#4A3A00; border-radius:8px;
  padding:.8rem 1.1rem; margin:0 0 1rem; font-size:.9rem; }}
.le-legal ul {{ margin:.4rem 0 .3rem 1.1rem; padding:0; }} .le-legal li {{ margin:.25rem 0; }}
.le-legal small {{ color:#7A6A30; }}
.le-review {{ background:#fff; border:1px solid #DCE4EF; border-radius:10px; padding:.8rem 1.1rem; margin:0 0 1rem; }}
.le-review .row {{ border-top:1px solid #EEF2F7; padding:.55rem 0; font-size:.9rem; }} .le-review .row:first-of-type {{ border-top:none; }}
.le-pill {{ display:inline-block; border-radius:999px; padding:0 .55rem; margin-right:.5rem; font-size:.72rem; font-weight:600; text-transform:uppercase; }}
.le-pill.high {{ background:#FDE7E7; color:#9B1C1C; }} .le-pill.medium {{ background:#FFF1D0; color:#7A5A00; }} .le-pill.low {{ background:#E8F0FB; color:#1B4F9C; }}
.le-fix {{ color:var(--gray); }} .le-meta {{ color:#8A96A6; font-size:.78rem; }}

/* ---------- responsive ---------- */
@media (max-width:900px) {{
  .le-feats {{ grid-template-columns:repeat(2,1fr); row-gap:1.5rem; }}
  .le-feat:nth-child(3) {{ border-left:none; }}
  .le-title {{ font-size:2rem; }}
  div[data-testid="stForm"], .st-key-gen_card {{ padding:1rem; }}
  .le-step span {{ display:none; }}
  .le-paper {{ padding:18px; }}
}}
@media (max-width:560px) {{ .le-feats {{ grid-template-columns:1fr; }} .le-feat {{ border-left:none; }} }}
</style>
"""


def load_css() -> None:
    """Inject the global stylesheet once per run."""
    st.markdown(CSS, unsafe_allow_html=True)
