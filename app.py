# app.py
"""
AHU Alarm Chatbot (Streamlit)
- Enter an alarm text and the app suggests possible reasons and recommended actions
- Lightweight: uses keywords + difflib fuzzy matching
"""

import streamlit as st
import difflib
import re
from datetime import datetime

st.set_page_config(page_title="AHU Alarm Chatbot", layout="wide")

# ---------- Metadata ----------
APP_TITLE = "AHU Alarm Chatbot — SOO-based Diagnostics"
st.title(APP_TITLE)
st.caption("Type or paste an alarm message from the BAS and get likely causes and suggested corrective actions. Based on your SOO (heating/cooling, economizer, safeties, filters, pumps, dampers, CO2/humidity alarms).")

# ---------- Alarm definition database (derived from SOO) ----------
# Each alarm has:
#  - keywords: short list of words to detect
#  - reasons: list of potential causes (ordered by likelihood)
#  - actions: recommended next steps / checks
#  - severity: informational / warning / critical
ALARM_DB = {
    "mixed_air_low_limit_trip": {
        "keywords": ["low limit", "freeze", "mixed air", "38 degrees", "38°", "low limit thermostat"],
        "reasons": [
            "Mixed air temperature dropped below low limit (freeze risk).",
            "Outside air damper stuck open during low outdoor temperature or incorrect blending.",
            "Faulty mixed air temperature sensor or miscalibrated sensor.",
            "Heating valve not opening / hot water not circulating.",
            "Airflow too low causing heat exchange imbalance."
        ],
        "actions": [
            "Verify mixed air temperature sensor reading and wiring.",
            "Confirm outside air damper position (should close) and check actuator.",
            "Check heating water valve position and hot water supply/return temperatures.",
            "Confirm supply fan is running and airflow setpoints.",
            "If low-limit tripped >3x auto-reset, lock out and alert operator as per SOO."
        ],
        "severity": "critical"
    },
    "discharge_air_high_static_or_high_temp": {
        "keywords": ["discharge static", "high static", "high limit", "5 inches", "5\" w.c.", "static pressure high"],
        "reasons": [
            "Blockage or dirty filter, coil, or duct causing high static.",
            "Fan speed or VFD malfunction / wrong command causing overpressure.",
            "Damper(s) closed in downstream branch creating overpressure.",
            "Faulty pressure sensor reading or wiring."
        ],
        "actions": [
            "Check filter differential pressure and filter banks (replace if required).",
            "Inspect downstream dampers and grilles for closure or obstruction.",
            "Verify fan VFD command vs actual speed and check fan proving status.",
            "Check static pressure transducer for correct reading and calibration."
        ],
        "severity": "critical"
    },
    "filter_differential_high": {
        "keywords": ["filter", "differential", "dp high", "pressure drop", "pre-filter", "primary filter"],
        "reasons": [
            "Pre-filter or primary filter is loaded or blocked.",
            "Bypass or leak may be mis-reporting DP sensor (sensor fault).",
            "Incorrect sensor span or wiring issue."
        ],
        "actions": [
            "Inspect pre-filter and primary filter banks; change filters if DP above setpoint.",
            "Confirm DP sensor wiring and calibration.",
            "Reset alarm after maintenance through BAS graphics."
        ],
        "severity": "warning"
    },
    "fan_failure": {
        "keywords": ["fan fail", "fan proving", "no fan", "fan status", "motor alarm", "vfd trip"],
        "reasons": [
            "Supply fan is not running (motor or VFD failure).",
            "Fan proving switch or sensor failure/fault.",
            "Electrical supply loss or motor overload trip."
        ],
        "actions": [
            "Check fan proving device status and wiring.",
            "Inspect VFD faults and motor starter; check electrical supply.",
            "Examine fan mechanical components (belt, bearings) for seizure."
        ],
        "severity": "critical"
    },
    "valve_position_alarm": {
        "keywords": ["valve", "stuck", "position", "control valve", "heating valve", "chilled water valve"],
        "reasons": [
            "Actuator failure or lost feedback (valve stuck).",
            "Control signal not reaching actuator or wrong control direction.",
            "Hydronic pump not running causing valve to be ineffective."
        ],
        "actions": [
            "Check valve actuator health and position feedback in BAS.",
            "Verify control signal (0-10V / 4-20mA or BACnet command) and wiring.",
            "Confirm associated pump is running and check flow/temperatures."
        ],
        "severity": "warning"
    },
    "pump_failure": {
        "keywords": ["pump fail", "pump loss", "pump alarm", "no pump", "pump trip", "current transducer"],
        "reasons": [
            "Pump motor failure or electrical supply lost.",
            "Pump tripped on overload or dry-run protection.",
            "Broken belt / coupling or mechanical seizure."
        ],
        "actions": [
            "Check current transducer reading and pump run status.",
            "Inspect electrical supply, motor starter, and overloads.",
            "Verify pump priming and piping; confirm flow."
        ],
        "severity": "critical"
    },
    "economizer_lockout_or_enthalpy": {
        "keywords": ["economizer", "enthalpy", "outside air", "mixing damper", "free cooling", "economizer lockout"],
        "reasons": [
            "Enthalpy control indicates outside air cannot be used (OA enthalpy above return).",
            "Damper actuator stuck or min/max positions not available.",
            "Enthalpy sensor or temperature/humidity sensor mismatch."
        ],
        "actions": [
            "Check outside air temperature/humidity sensors and enthalpy calculation.",
            "Inspect economizer damper positions and actuators.",
            "If economizer should be available, verify BAS permit logic and lockouts."
        ],
        "severity": "warning"
    },
    "co2_high": {
        "keywords": ["co2", "ppm", "carbon dioxide", "1000", "ppm"],
        "reasons": [
            "Space occupancy has increased beyond ventilation design.",
            "Outside air minimum or demand-control ventilation not functioning.",
            "CO2 sensor miscalibrated or drifted."
        ],
        "actions": [
            "Verify space CO2 sensor reading and calibration.",
            "Check outside air damper minimum position and CO2 demand control loop.",
            "Recommend increasing outside air or checking space occupancy."
        ],
        "severity": "warning"
    },
    "humidity_high": {
        "keywords": ["humidity", "rh", "%", "dehumidif", "60 percent", "60%"],
        "reasons": [
            "Moisture load increase or chilled water coil not providing sufficient dehumidification.",
            "Hot water reheat not available when required for dehumidification.",
            "Outside air enthalpy too high so economizer can't help."
        ],
        "actions": [
            "Check chilled water valve position and leaving coil temperature.",
            "Verify hot water heating system availability (required for reheat during dehumidification).",
            "If alarm prevents dehumid mode due to hot water system off, generate BAS alarm per SOO."
        ],
        "severity": "warning"
    },
    "night_purge_not_permitted": {
        "keywords": ["night purge", "purge", "purging", "night purge"],
        "reasons": [
            "Outdoor conditions do not satisfy night purge enthalpy criteria.",
            "Damper or control scheduling preventing night purge.",
            "Outside air actuator fault."
        ],
        "actions": [
            "Check outdoor air enthalpy vs indoor enthalpy and night purge schedule.",
            "Verify damper positions and that purge window (4 to 2 hours before occupancy) is enabled."
        ],
        "severity": "informational"
    },
    "sensors_lost": {
        "keywords": ["sensor", "reading", "no reading", "na", "failed sensor", "disconnected"],
        "reasons": [
            "Sensor failure or wiring/communication issue.",
            "Sensor out of range or uncalibrated.",
            "BAS point mapping changed or device offline."
        ],
        "actions": [
            "Identify which sensor is reporting invalid; check wiring and device status.",
            "Replace or recalibrate sensor as necessary.",
            "Confirm BACnet/device communication is healthy."
        ],
        "severity": "warning"
    },
    "short_cycle_protection": {
        "keywords": ["short cycle", "short-cycling", "min run", "min off", "prevent short"],
        "reasons": [
            "Unit cycling because setpoints or scheduling causing frequent starts/stops.",
            "Control deadband too narrow or sensor noise.",
        ],
        "actions": [
            "Check minimum run and off timers (user adjustable).",
            "Increase deadband or adjust hysteresis to prevent nuisance cycling."
        ],
        "severity": "informational"
    }
}

# Flatten alarm keys for matching
ALARM_KEYS = list(ALARM_DB.keys())

# ---------- Helper functions ----------
def normalize_text(t: str) -> str:
    return re.sub(r"[^0-9a-zA-Z%.\s]", " ", t).lower()

def keyword_match(text: str):
    found = []
    for key, dd in ALARM_DB.items():
        for kw in dd["keywords"]:
            if kw.lower() in text:
                found.append((key, kw))
                break
    return [k for k, _ in found]

def fuzzy_best_matches(text: str, n=3, cutoff=0.5):
    # Build a list of representative strings to compare against: alarm name + keywords joined
    choices = {}
    for key, dd in ALARM_DB.items():
        rep = key + " " + " ".join(dd["keywords"])
        choices[key] = rep
    # get ratios using difflib.SequenceMatcher via get_close_matches on the representative strings
    reps = list(choices.values())
    keys = list(choices.keys())
    matches = difflib.get_close_matches(text, reps, n=n, cutoff=cutoff)
    # map matched reps back to keys
    matched_keys = []
    for m in matches:
        # find index
        try:
            idx = reps.index(m)
            matched_keys.append(keys[idx])
        except ValueError:
            pass
    return matched_keys

def score_and_aggregate(input_text: str):
    text = normalize_text(input_text)
    direct = keyword_match(text)
    fuzzy = fuzzy_best_matches(text, n=5, cutoff=0.45)
    # Merge preserving direct matches first
    ordered = []
    for k in direct + fuzzy:
        if k not in ordered:
            ordered.append(k)
    # If nothing found, try word-level partial matches
    if not ordered:
        words = [w for w in text.split() if len(w) > 3]
        for k, dd in ALARM_DB.items():
            hits = sum(1 for kw in dd["keywords"] for w in words if w in kw)
            if hits:
                ordered.append(k)
    return ordered

# ---------- UI: Chat Input ----------
st.subheader("Enter alarm text (paste the BAS alarm message or type)")

with st.form("alarm_form"):
    user_alarm = st.text_area("Alarm message", height=140, placeholder="e.g. 'Mixed air low limit trip: MAT = 36°F — outside air damper open', or 'Filter DP high on AHU F201' ...")
    include_context = st.checkbox("Include timestamp and unit name (helpful)", value=True)
    submitted = st.form_submit_button("Diagnose alarm")

if submitted and user_alarm.strip():
    ts = datetime.now().isoformat(sep=" ", timespec="seconds") if include_context else None
    st.markdown("---")
    st.write(f"**Alarm received:** `{user_alarm.strip()}`")
    if ts:
        st.caption(f"Diagnosed at {ts}")
    matched_keys = score_and_aggregate(user_alarm)
    if not matched_keys:
        st.warning("No close automatic match found. Shown below are general troubleshooting suggestions.")
        # fall back general suggestions
        st.info("General checks:")
        st.write("- Confirm sensor readings in the AHU graphic (MAT, RAT, OAT, SAT, coil leaving temps).")
        st.write("- Check damper and valve positions from BAS graphics.")
        st.write("- Inspect VFD/Fan status and filter differential pressures.")
    else:
        st.success(f"Found {len(matched_keys)} possible alarm type(s).")
        for mk in matched_keys:
            dd = ALARM_DB[mk]
            st.markdown(f"### {mk.replace('_',' ').title()}  —  *Severity: {dd['severity'].title()}*")
            st.markdown("**Possible reasons (most likely → less likely):**")
            for i, r in enumerate(dd["reasons"], start=1):
                st.write(f"{i}. {r}")
            st.markdown("**Recommended actions / troubleshooting steps:**")
            for j, a in enumerate(dd["actions"], start=1):
                st.write(f"{j}. {a}")
            st.markdown("---")

    # Offer an exportable diagnostic summary
    if matched_keys:
        if st.button("Generate diagnostic summary (copyable)"):
            summary_lines = []
            summary_lines.append("AHU Alarm Diagnostic Summary")
            if ts:
                summary_lines.append(f"Timestamp: {ts}")
            summary_lines.append("Original alarm: " + user_alarm.strip())
            for mk in matched_keys:
                dd = ALARM_DB[mk]
                summary_lines.append("")
                summary_lines.append(f"Alarm match: {mk}  (severity: {dd['severity']})")
                summary_lines.append("Possible reasons:")
                for r in dd["reasons"]:
                    summary_lines.append(" - " + r)
                summary_lines.append("Actions:")
                for a in dd["actions"]:
                    summary_lines.append(" - " + a)
            summary_text = "\n".join(summary_lines)
            st.code(summary_text, language="text")
else:
    st.info("Enter an alarm message above and click Diagnose alarm.")

# ---------- Admin / debugging ----------
with st.expander("Show available alarm types (for reference)"):
    st.write("The app matches these SOO-derived alarm types (you can add or edit entries in the source).")
    for k in ALARM_KEYS:
        st.write(f"- **{k}**: {', '.join(ALARM_DB[k]['keywords'])}")

st.markdown("---")
st.caption("Pro-tip: add exact alarm phrases from your BAS into the keywords list to improve detection. This is intentionally conservative (keyword+fuzzy) to avoid false positives.")
