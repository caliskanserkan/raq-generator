"""
CZIB checker using Anthropic API with web search.
"""

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
    "UK":"Ukraine","UU":"Russia","UR":"Russia South","UH":"Russia Far East",
    "UI":"Russia Siberia","UW":"Russia Volga","US":"Russia Ural",
    "UT":"Central Asia","UB":"Azerbaijan","UC":"Kyrgyzstan",
    "UD":"Armenia","UG":"Georgia","UA":"Kazakhstan",
    "RK":"South Korea","RJ":"Japan","RC":"Taiwan","VH":"Hong Kong",
    "ZB":"China","ZG":"China South","ZS":"China East",
    "VT":"Thailand","VV":"Vietnam","WS":"Singapore","WM":"Malaysia",
    "WI":"Indonesia","WB":"Malaysia Borneo","VN":"Nepal",
    "VI":"India North","VA":"India West","VE":"India East","VO":"India South",
    "VD":"Cambodia","VL":"Laos","VY":"Myanmar",
}

# Countries almost certainly with NO active CZIB - skip API call
NO_CZIB = {
    "EG","EI","EK","EL","EN","ED","EE","EF","EH","ES",
    "LH","LI","LK","LM","LO","LP","LZ","LS","LF","LG","LE",
    "RJ","RK","WS","WM","VT","VH",
}

def get_country_from_icao(icao):
    icao = icao.upper().strip()
    p2 = icao[:2]
    if p2 in ICAO_COUNTRY:
        return ICAO_COUNTRY[p2], p2
    p1 = icao[:1]
    one = {"K":"United States","C":"Canada","Y":"Australia","Z":"China"}
    if p1 in one:
        return one[p1], p1
    return None, p2

def check_czib(icao, api_key=None):
    """Returns (has_czib: bool, warning_text: str)"""
    country, prefix = get_country_from_icao(icao)

    if not country or prefix in NO_CZIB:
        return False, ""

    try:
        import anthropic
        import streamlit as st

        key = api_key or st.secrets.get("anthropic", {}).get("api_key")
        if not key:
            return False, ""

        client = anthropic.Anthropic(api_key=key)

        prompt = (
            f"Visit https://www.easa.europa.eu/en/domains/air-operations/czibs "
            f"and check if there are any currently ACTIVE EASA Conflict Zone "
            f"Information Bulletins (CZIBs) for {country} or its airspace region. "
            f"Reply with ONLY 'YES' or 'NO'."
        )

        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )

        answer = " ".join(
            b.text for b in resp.content if hasattr(b, "text")
        ).upper()

        has_czib = "YES" in answer
        warning = (
            f"CHECK LATEST EASA CZIB RELATED WITH {country.upper()} REGION"
            if has_czib else ""
        )
        return has_czib, warning

    except Exception as e:
        return False, ""
