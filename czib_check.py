"""
CZIB checker - fetches EASA CZIB page directly with requests.
No API key needed.
"""
import re

ICAO_COUNTRY = {
    "EG":"United Kingdom","EI":"Ireland","EK":"Denmark","EL":"Luxembourg",
    "EN":"Norway","EP":"Poland","ES":"Sweden","ED":"Germany","EE":"Estonia",
    "EF":"Finland","EH":"Netherlands","LH":"Hungary","LI":"Italy",
    "LK":"Czech Republic","LL":"Israel","LM":"Malta","LO":"Austria",
    "LP":"Portugal","LQ":"Bosnia","LR":"Romania","LS":"Switzerland",
    "LT":"Turkey","LU":"Moldova","LW":"North Macedonia","LY":"Serbia",
    "LZ":"Slovakia","LA":"Albania","LB":"Bulgaria","LC":"Cyprus",
    "LD":"Croatia","LE":"Spain","LF":"France","LG":"Greece",
    "OR":"Iraq","OI":"Iran","OJ":"Jordan","OL":"Lebanon","OM":"UAE",
    "OO":"Oman","OP":"Pakistan","OS":"Syria","OT":"Qatar","OY":"Yemen",
    "OB":"Bahrain","OE":"Saudi Arabia","OA":"Afghanistan",
    "HL":"Libya","HE":"Egypt","HA":"Ethiopia","HC":"Somalia",
    "DA":"Algeria","DT":"Tunisia","DN":"Nigeria",
    "UK":"Ukraine","UU":"Russia","UR":"Russia","UH":"Russia",
    "UI":"Russia","UW":"Russia","US":"Russia",
    "UT":"Central Asia","UB":"Azerbaijan","UC":"Kyrgyzstan",
    "UD":"Armenia","UG":"Georgia","UA":"Kazakhstan",
    "RK":"South Korea","RJ":"Japan","RC":"Taiwan","VH":"Hong Kong",
    "VT":"Thailand","VV":"Vietnam","WS":"Singapore","WM":"Malaysia",
    "WI":"Indonesia","WB":"Borneo","VN":"Nepal",
    "VI":"India","VA":"India","VE":"India","VO":"India",
    "VD":"Cambodia","VL":"Laos","VY":"Myanmar",
}

NO_CZIB = {
    "EG","EI","EK","EL","EN","ED","EE","EF","EH","ES",
    "LH","LI","LK","LM","LO","LP","LZ","LS","LF","LG","LE",
    "RJ","RK","WS","WM","VT","VH","LT","LG","LS","LH",
}

def get_country_from_icao(icao):
    icao = icao.upper().strip()
    p2 = icao[:2]
    if p2 in ICAO_COUNTRY:
        return ICAO_COUNTRY[p2], p2
    return None, p2

import streamlit as st

@st.cache_data(ttl=3600)  # Cache 1 hour
def _fetch_czib_page():
    """Fetch EASA CZIB page content."""
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        # Try the EASA information sharing platform which has static content
        r = requests.get(
            'https://www.easa.europa.eu/en/domains/air-operations/czibs',
            headers=headers, timeout=10
        )
        return r.text.lower()
    except:
        try:
            # Fallback: try the information sharing platform
            import requests
            r = requests.get(
                'https://www.easa.europa.eu/european-information-sharing-and-cooperation-platform-conflict-zones',
                headers=headers, timeout=10
            )
            return r.text.lower()
        except:
            return ""

def check_czib(icao, api_key=None):
    """Returns (has_czib: bool, warning_text: str)"""
    country, prefix = get_country_from_icao(icao)

    if not country or prefix in NO_CZIB:
        return False, ""

    try:
        page = _fetch_czib_page()
        if not page:
            return False, ""

        # Search for country name in CZIB page
        country_lower = country.lower()
        
        # Check for CZIB references near country name
        # Look for patterns like "iraq", "iran", "syria" etc. with czib nearby
        keywords = [country_lower]
        
        # Add country variants
        variants = {
            "iraq": ["iraq", "baghdad"],
            "iran": ["iran", "tehran"],
            "syria": ["syria", "syrian"],
            "ukraine": ["ukraine", "ukrainian"],
            "russia": ["russia", "russian"],
            "libya": ["libya", "libyan"],
            "yemen": ["yemen", "yemeni"],
            "lebanon": ["lebanon", "beirut"],
            "pakistan": ["pakistan"],
            "afghanistan": ["afghanistan", "kabul"],
        }
        keywords = variants.get(country_lower, [country_lower])

        # Check if any keyword appears near "czib" in the page
        for kw in keywords:
            # Find all positions of keyword
            idx = 0
            while True:
                pos = page.find(kw, idx)
                if pos == -1:
                    break
                # Check if "czib" appears within 500 chars
                context = page[max(0, pos-500):pos+500]
                if "czib" in context:
                    warning = f"CHECK LATEST EASA CZIB RELATED WITH {country.upper()} REGION"
                    return True, warning
                idx = pos + 1

        return False, ""

    except Exception as e:
        return False, ""
