# AHU Alarm Chatbot (Streamlit)

Small Streamlit app that accepts BAS alarm text and returns likely reasons and recommended actions,
based on a Sequence-of-Operation (SOO) for AHUs (economizer, coils, pumps, safeties, filters, CO2/humidity, etc).

## Run locally
1. Create a virtualenv (recommended):
   python -m venv .venv
   source .venv/bin/activate   # mac/linux
   .venv\Scripts\activate      # windows

2. Install requirements:
   pip install -r requirements.txt

3. Run:
   streamlit run app.py

Open the URL shown by Streamlit (usually http://localhost:8501).

## Deploy to Streamlit Cloud (quick)
1. Create a new GitHub repo, push the files (app.py and requirements.txt).
2. Sign in to https://share.streamlit.io and connect your GitHub.
3. Create a new app from your repository and branch — Streamlit will deploy automatically.

## Improve detection
Add your exact BAS alarm phrases to the `ALARM_DB` `keywords` list in `app.py` to increase matching accuracy.
