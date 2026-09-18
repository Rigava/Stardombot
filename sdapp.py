from __future__ import annotations
import io, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="StarDOM AI Role Visibility Agent", page_icon="🤖", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.2rem}.hero{padding:1.1rem 1.3rem;border-radius:14px;background:linear-gradient(110deg,#00243D,#005A80);color:white;margin-bottom:1rem}
.answer{border:1px solid #b8dce9;border-left:5px solid #42B0D5;border-radius:10px;padding:1rem;background:#f7fcfe}.note{color:#586973;font-size:.9rem}
[data-testid='stMetric']{background:#EAF7FB;padding:12px;border-radius:10px}
</style>""", unsafe_allow_html=True)

PROFILE_PREFIX="System Profile - "
INCIDENT_PREFIX="Incident Management - "
META=["SiteMasterId","LocationId","LocationName","Created At","Created By","Updated At","Updated By","Isenabled"]

st.markdown("<div class='hero'><h2>StarDOM AI Role Visibility Agent</h2><p>Ask who can report, review or investigate at a StarDOM location. Results are derived from direct workbook assignments and show their evidence.</p></div>",unsafe_allow_html=True)


def emails(value):
    if pd.isna(value): return []
    return sorted({x.strip().lower() for x in re.split(r"[,;\n]+",str(value)) if "@" in x.strip()})

@st.cache_data(show_spinner=False)
def load_excel(raw: bytes):
    book=pd.ExcelFile(io.BytesIO(raw),engine="openpyxl")
    required={"LocationwiseUserProfiles","LocationAttributes"}
    if not required.issubset(book.sheet_names):
        raise ValueError("Required sheets: LocationwiseUserProfiles and LocationAttributes")
    return (pd.read_excel(book,"LocationwiseUserProfiles"),pd.read_excel(book,"LocationAttributes"))

# DataFrames are deliberately not cached to avoid Streamlit hashing failures.
def build_model(profiles: pd.DataFrame, attrs: pd.DataFrame):
    incident_cols=[c for c in profiles.columns if str(c).startswith(INCIDENT_PREFIX)]
    records=[]
    for _,r in profiles.iterrows():
        base={k:r.get(k) for k in ["SiteMasterId","LocationId","LocationName"]}
        for col in incident_cols:
            role=str(col)[len(INCIDENT_PREFIX):].strip()
            for email in emails(r[col]): records.append({**base,"Email":email,"IncidentRole":role,"EvidenceColumn":col})
    access=pd.DataFrame(records)
    if access.empty: return access, incident_cols
    # Capability logic is deterministic and based on explicit incident-role columns.
    role=access.IncidentRole.str.lower()
    access["CanReport"]=role.str.contains("reporter") | role.eq("admin")
    access["CanReview"]=role.str.contains("reviewer") | role.eq("admin")
    access["CanInvestigate"]=role.str.contains("investigator") | role.eq("admin")
    keep=[c for c in ["SiteMasterId","LocationId","RegionName","AreaName","CountryName","OperationTypeName","BusinessUnitName","IsActiveInSource","IsApplicableStardom"] if c in attrs.columns]
    attributes=attrs[keep].drop_duplicates(subset=[c for c in ["SiteMasterId","LocationId"] if c in keep])
    if "SiteMasterId" in attributes and access.SiteMasterId.notna().any():
        access=access.merge(attributes.drop(columns=["LocationId"],errors="ignore"),on="SiteMasterId",how="left")
    elif "LocationId" in attributes:
        access=access.merge(attributes.drop(columns=["SiteMasterId"],errors="ignore"),on="LocationId",how="left")
    return access, incident_cols

def locate(question, locations):
    q=question.lower()
    exact=[x for x in locations if str(x[0]).lower() in q or str(x[1]).lower() in q]
    return exact[0] if exact else None

def intent(question):
    q=question.lower()
    if any(w in q for w in ["investigate","investigator","investigation"]): return "Investigate","CanInvestigate"
    if any(w in q for w in ["review","reviewer","validate"]): return "Review","CanReview"
    if any(w in q for w in ["report","reporter","raise incident"]): return "Report","CanReport"
    return None,None

uploaded=st.sidebar.file_uploader("Upload StardomUserLocwise.xlsx",type=["xlsx"])
st.sidebar.caption("Demo is read-only. No access changes are made.")
if not uploaded:
    st.info("Upload the workbook to start the demo. The file must contain the two expected sheets.")
    st.stop()
try:
    profiles,attrs=load_excel(uploaded.getvalue())
    access,incident_cols=build_model(profiles,attrs)
except Exception as e:
    st.error(f"The workbook could not be loaded: {e}"); st.stop()
if access.empty:
    st.error("No explicit Incident Management assignment columns with users were found."); st.stop()

c1,c2,c3,c4=st.columns(4)
c1.metric("Users",f"{access.Email.nunique():,}"); c2.metric("Locations",f"{access.LocationId.nunique():,}"); c3.metric("Incident roles",f"{access.IncidentRole.nunique():,}"); c4.metric("Direct assignments",f"{len(access):,}")

tabs=st.tabs(["Ask the agent","Site coverage","User visibility","Logic & governance"])
locations=list(access[["LocationId","LocationName"]].drop_duplicates().itertuples(index=False,name=None))
with tabs[0]:
    examples=["Who can investigate at MATNG02?","Who can review at Suez Canal Container Terminal?","Who can report at IN0160?"]
    question=st.text_input("Ask a question",placeholder=examples[0])
    st.caption("Examples: "+"  |  ".join(examples))
    if question:
        action,field=intent(question); loc=locate(question,locations)
        if not action: st.warning("Please include report, review or investigate in the question.")
        elif not loc:
            matches=[f"{a} | {b}" for a,b in locations if any(t in f"{a} {b}".lower() for t in question.lower().split() if len(t)>3)][:8]
            st.warning("I could not identify one location. Use a LocationId or the full location name.")
            if matches: st.write("Possible matches:",matches)
        else:
            lid,lname=loc; result=access[(access.LocationId==lid)&(access[field])].copy()
            st.markdown(f"<div class='answer'><b>Answer</b><br>{result.Email.nunique()} user(s) have a direct workbook assignment that allows them to <b>{action.lower()}</b> at <b>{lname}</b> ({lid}).</div>",unsafe_allow_html=True)
            show=[c for c in ["Email","IncidentRole","LocationId","LocationName","RegionName","AreaName","CountryName","EvidenceColumn"] if c in result]
            st.dataframe(result[show].drop_duplicates().sort_values(["IncidentRole","Email"]),use_container_width=True,hide_index=True)
            st.download_button("Download evidence",result[show].to_csv(index=False).encode(),f"{lid}_{action.lower()}_eligibility.csv","text/csv")
            st.caption("Eligibility is not the same as assignment to a specific incident. The demo does not assess suitability or performance.")
with tabs[1]:
    capability=st.selectbox("Capability",["Report","Review","Investigate"])
    field={"Report":"CanReport","Review":"CanReview","Investigate":"CanInvestigate"}[capability]
    summary=access.groupby(["LocationId","LocationName"],dropna=False).agg(Reporters=("CanReport","sum"),Reviewers=("CanReview","sum"),Investigators=("CanInvestigate","sum")).reset_index()
    only_gaps=st.checkbox("Show coverage gaps only",True)
    metric={"Report":"Reporters","Review":"Reviewers","Investigate":"Investigators"}[capability]
    if only_gaps: summary=summary[summary[metric]==0]
    st.dataframe(summary.sort_values(metric),use_container_width=True,hide_index=True)
    st.download_button("Download coverage",summary.to_csv(index=False).encode(),"incident_role_coverage.csv","text/csv")
with tabs[2]:
    user=st.selectbox("User",sorted(access.Email.unique()))
    u=access[access.Email==user].copy()
    show=[c for c in ["LocationId","LocationName","RegionName","CountryName","IncidentRole","CanReport","CanReview","CanInvestigate","EvidenceColumn"] if c in u]
    st.dataframe(u[show].drop_duplicates(),use_container_width=True,hide_index=True)
with tabs[3]:
    st.subheader("Deterministic capability rules")
    rules=pd.DataFrame([
        ["Incident Reporter / Incident Reporter Basic","Yes","No","No"],
        ["Reviewer","No","Yes","No"],
        ["Investigator","No","No","Yes"],
        ["Reviewer & Investigator","No","Yes","Yes"],
        ["Admin","Yes","Yes","Yes"],
        ["Confidential Incident Viewer","No","No","No"],
    ],columns=["Explicit incident role","Report","Review","Investigate"])
    st.dataframe(rules,use_container_width=True,hide_index=True)
    st.info("The demo uses the workbook's explicit Incident Management columns. It does not infer regional hierarchy, recommend individuals, or change access.")
    st.write("**Responsible AI controls**")
    st.write("- Transparency: every result shows the evidence column.\n- Accountability: mappings remain deterministic and reviewable.\n- Privacy: deploy behind organizational authentication before broad use.\n- Fairness: results reflect access records only, not employee capability or performance.\n- Safety: the agent never assigns an investigator to a live case.")
