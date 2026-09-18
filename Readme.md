# StarDOM AI Role Visibility Agent Demo

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Upload `StardomUserLocwise.xlsx` in the sidebar. The workbook must contain `LocationwiseUserProfiles` and `LocationAttributes`.

## Demo scope
- Natural-language questions for who can report, review, or investigate at a location
- Evidence-backed user results from explicit Incident Management columns
- Site coverage gaps
- User-level access visibility
- CSV exports
- Responsible AI and governance explanation

This is a read-only showcase. It does not change access, infer hierarchy, assess employees, or assign users to incidents.
