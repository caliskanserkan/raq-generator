"""
CZIB checker using Anthropic API with web search.
Returns (has_czib: bool, czib_text: str) for a given ICAO code.
"""

# ICAO prefix → country mapping
ICAO_COUNTRY = {
    # Europe
    "EG": "United Kingdom", "EI": "Ireland", "EK": "Denmark",
    "EL": "Luxembourg", "EN": "Norway", "EP": "Poland",
    "ES": "Sweden", "ET": "Germany (military)", "EV": "Latvia",
    "EY": "Lithuania", "ED": "Germany", "EE": "Estonia",
    "EF": "Finland", "LH": "Hungary", "LI": "Italy",
    "LK": "Czech Republic", "LL": "Israel", "LM": "Malta",
    "LO": "Austria", "LP": "Portugal", "LQ": "Bosnia and Herzegovina",
    "LR": "Romania", "LS": "Switzerland", "LT": "Turkey",
    "LU": "Moldova", "LW": "North Macedonia", "LY": "Serbia",
    "LZ": "Slovakia", "LA": "Albania", "LB": "Bulgaria",
    "LC": "Cyprus", "LD": "Croatia", "LE": "Spain",
    "LF": "France", "LG": "Greece",
    # Middle East / conflict zones
    "OR": "Iraq", "OI": "Iran", "OJ": "Jordan",
    "OL": "Lebanon", "OM": "UAE", "OO": "Oman",
    "OP": "Pakistan", "OS": "Syria", "OT": "Qatar",
    "OY": "Yemen", "OB": "Bahrain", "OE": "Saudi Arabia",
    "OA": "Afghanistan",
    # Africa
    "HL": "Libya", "HE": "Egypt", "HA": "Ethiopia",
    "HC": "Somalia", "HR": "Rwanda", "HT": "Tanzania",
    "DA": "Algeria", "DT": "Tunisia", "DN": "Nigeria",
    # CIS / Russia / Ukraine
    "UK": "Ukraine", "UU": "Russia (Moscow)", "UR": "Russia (South)",
    "UH": "Russia (Far East)", "UI": "Russia (Siberia)",
    "UW": "Russia (Volga-Ural)", "US": "Russia (Ural)",
    "UT": "Turkmenistan/Uzbekistan/Tajikistan",
    "UB": "Azerbaijan", "UC": "Kyrgyzstan", "UD": "Armenia",
    "UG": "Georgia",
    # Asia
    "RK": "South Korea", "RJ": "Japan", "RC": "Taiwan",
    "VH": "Hong Kong", "ZB": "China (Beijing)", "ZG": "China (Guangzhou)",
    "ZS": "China (Shanghai)", "ZU": "China (Chengdu)",
    "VT": "Thailand", "VV": "Vietnam", "WS": "Singapore",
    "WM": "Malaysia", "WI": "Indonesia", "WB": "Malaysia (Sabah/Sarawak)",
    "VN": "Nepal", "VI": "India (North)", "VA": "India (West)",
    "VE": "India (East)", "VO": "India (South)",
    "VD": "Cambodia", "VL": "Laos", "VY": "Myanmar",
    "OA": "Afghanistan", "OI": "Iran",
    # Caucasus/Central Asia
    "UA": "Kazakhstan", "UB": "Azerbaijan",
}

def get_country_from_icao(icao):
    """Get country name from ICAO prefix."""
    icao = icao.upper().strip()
    # Try 2-letter prefix first
    prefix2 = icao[:2]
    if prefix2 in ICAO_COUNTRY:
        return ICAO_COUNTRY[prefix2], prefix2
    # Try 1-letter prefix
    prefix1 = icao[:1]
    prefix1_map = {
        "K": "United States", "C": "Canada", "M": "Mexico/Central America",
        "S": "South America", "Z": "China", "R": "East Asia",
        "V": "South/Southeast Asia", "W": "Indonesia/Malaysia",
        "Y": "Australia", "N": "Pacific Islands", "F": "Africa (South)",
        "G": "Africa (West)", "H": "Africa (East/Northeast)",
        "D": "Africa (North/West)",
    }
    if prefix1 in prefix1_map:
        return prefix1_map[prefix1], prefix1
    return "Unknown", icao[:2]

def check_czib(icao, api_key=None):
    """
    Check EASA CZIB for given ICAO.
    Returns (has_czib, warning_text)
    """
    import anthropic

    country, prefix = get_country_from_icao(icao)

    # Countries/regions that almost certainly have no CZIB — skip API call
    no_czib_prefixes = {
        "EG","EI","EK","EL","EN","ED","EE","EF","ES","EH",
        "LH","LI","LK","LM","LO","LP","LZ","LK","LS",
        "LF","LG","LE","RJ","RK","YM","YP","YS",
        "K","C","WS","WM",
    }
    if prefix in no_czib_prefixes:
        return False, ""

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    prompt = (
        f"Check the EASA Conflict Zone Information Bulletins (CZIBs) page at "
        f"https://www.easa.europa.eu/en/domains/air-operations/czibs "
        f"Are there currently any ACTIVE EASA CZIBs related to {country} "
        f"(ICAO region prefix: {prefix})? "
        f"Answer with only YES or NO. If YES, also state the CZIB reference number if visible."
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )

        answer = ""
        for block in response.content:
            if hasattr(block, "text"):
                answer += block.text

        has_czib = "YES" in answer.upper()
        ref = ""
        if has_czib and "CZIB" in answer.upper():
            import re
            refs = re.findall(r'CZIB[\s\-]?\d{4}[\s\-]?\d+', answer, re.IGNORECASE)
            if refs:
                ref = " – " + ", ".join(refs)

        warning = f"⚠ CHECK LATEST EASA CZIB RELATED WITH {country.upper()}{ref}" if has_czib else ""
        return has_czib, warning

    except Exception as e:
        return False, ""
