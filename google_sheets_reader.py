import os
import re
from datetime import datetime

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

import json

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


# -------------------------------------
# GOOGLE SHEETS CLIENT
# -------------------------------------

def get_gspread_client(readonly=True):
    scopes = SCOPES if readonly else ["https://www.googleapis.com/auth/spreadsheets"]

    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if service_account_json:
        credentials_info = json.loads(service_account_json)
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=scopes
        )
    else:
        credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=scopes
        )

    return gspread.authorize(credentials)

# -------------------------------------
# LOAD PACKAGES FROM GOOGLE SHEETS
# -------------------------------------

def load_packages_from_google_sheet(sheet_id: str, worksheet_name: str = "packages") -> pd.DataFrame:
    client = get_gspread_client(readonly=True)

    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)

    records = worksheet.get_all_records()
    df = pd.DataFrame(records)

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

    return df


# -------------------------------------
# PACKAGE SEARCH HELPERS
# -------------------------------------

def clean_query_terms(user_query: str):
    if not user_query:
        return []

    stopwords = {
        "i", "am", "a", "an", "the", "to", "for", "in", "on", "of", "and",
        "or", "with", "want", "would", "like", "looking", "look", "somewhere",
        "place", "trip", "vacation", "holiday", "please", "me", "my", "we",
        "us", "can", "you", "show", "find", "need",
        "quiero", "quisiera", "busco", "necesito", "un", "una", "unos", "unas",
        "el", "la", "los", "las", "de", "del", "para", "con", "por", "favor",
        "viaje", "vacaciones", "lugar"
    }

    query = user_query.lower()
    query = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", query)

    terms = []

    for term in query.split():
        term = term.strip()

        if len(term) < 3:
            continue

        if term in stopwords:
            continue

        terms.append(term)

    return list(dict.fromkeys(terms))


def get_searchable_columns(df: pd.DataFrame):
    possible_columns = [
        "category_tags",
        "destination_tags",
        "region",
        "country",
        "destination",
        "hotel",
        "package_name",
        "short_title",
        "short_title_es",
        "meal_plan",
        "meal_plan_es",
        "description",
        "description_es",
        "package_type",
        "ideal_for",
        "promotion_label",
        "included",
        "included_es",
        "booking_notes",
        "currency",
        "nights"
    ]

    return [col for col in possible_columns if col in df.columns]


# -------------------------------------
# FILTER PACKAGES
# -------------------------------------

def filter_packages(df: pd.DataFrame, user_query: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    results = df.copy()

    # -------------------------------------
    # ACTIVE PACKAGE FILTER
    # -------------------------------------

    if "active" in results.columns:
        results = results[
            results["active"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "yes", "1", "active"])
        ]

    # -------------------------------------
    # EXPIRY DATE FILTER
    # -------------------------------------

    if "valid_until" in results.columns:

        today = pd.Timestamp.today().normalize()

        def is_valid_date(date_value):

            if pd.isna(date_value):
                return True

            date_str = str(date_value).strip()

            # Empty date = no expiry
            if date_str == "":
                return True

            try:
                expiry_date = pd.to_datetime(date_str).normalize()
                return expiry_date >= today

            except:
                # Invalid date format → keep package visible
                return True

        results = results[
            results["valid_until"].apply(is_valid_date)
        ]

    if results.empty:
        return pd.DataFrame()

    terms = clean_query_terms(user_query)

    if not terms:
        return pd.DataFrame()

    searchable_columns = get_searchable_columns(results)

    # IMPORTANT:
    # Use a lowercase copy for scoring only.
    # Do NOT lowercase the original results dataframe,
    # because app.py uses original package names to match images.
    lowercase_results = results.copy()

    for col in searchable_columns:
        lowercase_results[col] = lowercase_results[col].astype(str).str.lower()

    scores = []

    for _, row in lowercase_results.iterrows():
        score = 0

        category_tags = row.get("category_tags", "")
        destination_tags = row.get("destination_tags", "")
        promotion_label = row.get("promotion_label", "")
        package_name = row.get("package_name", "")
        short_title = row.get("short_title", "")
        short_title_es = row.get("short_title_es", "")
        description = row.get("description", "")
        description_es = row.get("description_es", "")

        for term in terms:

            # VERY HIGH PRIORITY
            if term in package_name:
                score += 15

            if term in destination_tags:
                score += 12

            # HIGH PRIORITY
            if term in category_tags:
                score += 10

            if term in promotion_label:
                score += 8

            # MEDIUM PRIORITY
            if term in short_title:
                score += 6

            if term in short_title_es:
                score += 6

            # LOWER PRIORITY
            if term in description:
                score += 3

            if term in description_es:
                score += 3

            # BONUS RULES

            if term in ["luxury", "premium", "deluxe", "lujo"]:
                if any(x in category_tags for x in ["luxury", "premium", "deluxe", "lujo"]):
                    score += 20

            if term in ["budget", "cheap", "affordable", "barato", "económico", "economico"]:
                if any(x in category_tags for x in ["budget", "cheap", "affordable", "sale", "discount"]):
                    score += 20

            if term in ["family", "kids", "children", "familia", "niños", "ninos"]:
                if any(x in category_tags for x in ["family", "kids", "children", "familia"]):
                    score += 15

            if term in ["nature", "mountains", "naturaleza", "aventura"]:
                if any(x in category_tags for x in ["nature", "mountains", "eco", "adventure"]):
                    score += 15

            if term in ["beach", "hot", "tropical", "playa", "calor"]:
                if any(x in category_tags for x in ["beach", "tropical", "island", "hot"]):
                    score += 15

        scores.append(score)

    results["_score"] = scores

    results = results[results["_score"] > 0]

    if results.empty:
        return pd.DataFrame()

    results = results.sort_values(
        by=["_score"],
        ascending=False
    )

    return results.drop(columns=["_score"], errors="ignore")


# -------------------------------------
# SEARCH PACKAGES
# -------------------------------------

def search_packages(df: pd.DataFrame, user_query: str) -> pd.DataFrame:
    return filter_packages(df, user_query)


# -------------------------------------
# FORMAT PRICE
# -------------------------------------

def format_price(price, currency):
    try:
        price = float(price)
        formatted = f"{int(price):,}"
        return f"{currency} ${formatted}"
    except:
        return ""


def get_value(row, primary_col, fallback_col=None):
    value = row.get(primary_col, "")

    if value is not None and str(value).strip() != "":
        return value

    if fallback_col:
        fallback = row.get(fallback_col, "")
        if fallback is not None:
            return fallback

    return ""


# -------------------------------------
# FORMAT PACKAGE RESULTS
# -------------------------------------

def format_package_results(results: pd.DataFrame, max_results: int = 3) -> str:
    if results.empty:
        return "I couldn’t find a matching package. Would you like to speak with a travel advisor?"

    messages = []

    for _, row in results.head(max_results).iterrows():
        price = row.get("price_from", "")
        currency = row.get("currency", "")
        formatted_price = format_price(price, currency)

        price_text = ""
        if formatted_price:
            price_text = f"\nFrom: {formatted_price}"

        message = (
            f"🌍 {row.get('package_name', 'Travel Package')}\n"
            f"{row.get('short_title', '')}\n"
            f"{row.get('nights', '')} nights"
            f"{price_text}\n"
            f"{row.get('description', '')}"
        )

        messages.append(message.strip())

    return "\n\n".join(messages)


# -------------------------------------
# FORMAT PACKAGES FOR WHATSAPP
# -------------------------------------

def format_packages_for_whatsapp(results, max_results=3, lang="en"):
    if results.empty:
        if lang == "es":
            return (
                "No pude encontrar un paquete que coincida 😊\n"
                "Puedes intentar: playa, familia, naturaleza, calor, viaje económico, oferta de hotel o lugar para descansar."
            )

        return (
            "I couldn’t find a matching package 😊\n"
            "You can try: beach, family, nature, hot weather, cheap vacation, hotel sale, or relaxing place."
        )

    if lang == "es":
        nights_label = "noches"
        meal_label = "Plan de alimentación"
        price_label = "Desde"
        includes_label = "Incluye"
        valid_label = "Válido hasta"
    else:
        nights_label = "nights"
        meal_label = "Meal plan"
        price_label = "From"
        includes_label = "Includes"
        valid_label = "Valid until"

    messages = []

    for _, row in results.head(max_results).iterrows():
        package_name = row.get("package_name", "Travel package")
        nights = row.get("nights", "")
        price = row.get("price_from", "")
        currency = row.get("currency", "")
        destination = row.get("destination", "")
        promotion_label = row.get("promotion_label", "")
        valid_until = row.get("valid_until", "")

        if lang == "es":
            short_title = get_value(row, "short_title_es", "short_title")
            description = get_value(row, "description_es", "description")
            meal_plan = get_value(row, "meal_plan_es", "meal_plan")
            included = get_value(row, "included_es", "included")
        else:
            short_title = get_value(row, "short_title")
            description = get_value(row, "description")
            meal_plan = get_value(row, "meal_plan")
            included = get_value(row, "included")

        formatted_price = format_price(price, currency)

        promo_text = ""

        if promotion_label:
            label = str(promotion_label).strip()

            if "sale" in label.lower() or "discount" in label.lower() or "offer" in label.lower() or "oferta" in label.lower():
                promo_text = f"🔥 {label.upper()}\n"
            elif "family" in label.lower() or "familia" in label.lower():
                promo_text = f"👨‍👩‍👧 {label}\n"
            elif "nature" in label.lower() or "naturaleza" in label.lower():
                promo_text = f"🌿 {label}\n"
            elif "caribbean" in label.lower() or "beach" in label.lower() or "caribe" in label.lower() or "playa" in label.lower():
                promo_text = f"🌴 {label}\n"
            else:
                promo_text = f"⭐ {label}\n"

        price_text = ""
        if formatted_price:
            price_text = f"💰 {price_label}: {formatted_price}\n"

        meal_text = ""
        if meal_plan:
            meal_text = f"🍽️ {meal_label}: {meal_plan}\n"

        included_text = ""
        if included:
            included_text = f"✅ {includes_label}: {included}\n"

        valid_text = ""
        if valid_until:
            valid_text = f"📅 {valid_label}: {valid_until}\n"

        text = (
            f"{promo_text}"
            f"🌍 {package_name}\n"
            f"📍 {destination}\n"
            f"✨ {short_title}\n"
            f"🛏️ {nights} {nights_label}\n"
            f"{meal_text}"
            f"{price_text}"
            f"{included_text}"
            f"{valid_text}\n"
            f"{description}"
        )

        messages.append(text.strip())

    return "\n\n---\n\n".join(messages)


# =========================================
# LOAD BUSINESS INFO FROM GOOGLE SHEETS
# =========================================

def load_business_info_from_google_sheet(sheet_id: str, worksheet_name: str = "business_info") -> dict:
    client = get_gspread_client(readonly=True)

    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)

    records = worksheet.get_all_records()

    business_info = {}

    for row in records:
        field = str(row.get("field", "")).strip()
        value = str(row.get("value", "")).strip()

        if field:
            business_info[field] = value

    return business_info


# =========================================
# SAVE LEAD TO GOOGLE SHEETS
# =========================================

def save_lead_to_google_sheet(sheet_id: str, lead_data: dict, worksheet_name: str = "leads"):
    client = get_gspread_client(readonly=False)

    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        lead_data.get("customer_phone", ""),
        lead_data.get("customer_name", ""),
        lead_data.get("last_search", ""),
        ", ".join(lead_data.get("interested_packages", [])),
        lead_data.get("last_message", ""),
        str(lead_data.get("handoff_requested", False)),
        lead_data.get("lead_type", ""),
        lead_data.get("status", "new")
    ]

    worksheet.append_row(row)


# =========================================
# SAVE FLIGHT REQUEST TO GOOGLE SHEETS
# =========================================

def save_flight_request_to_google_sheet(sheet_id: str, flight_data: dict, worksheet_name: str = "flight_requests"):
    client = get_gspread_client(readonly=False)

    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        flight_data.get("name", ""),
        flight_data.get("phone", ""),
        flight_data.get("email", ""),
        flight_data.get("trip_type", ""),
        flight_data.get("origin", ""),
        flight_data.get("destination", ""),
        flight_data.get("departure_date", ""),
        flight_data.get("return_date", ""),
        flight_data.get("passengers", ""),
        flight_data.get("preferences", ""),
        flight_data.get("status", "new")
    ]

    worksheet.append_row(row)


# =========================================
# SAVE PACKAGE REQUEST TO GOOGLE SHEETS
# =========================================

def save_package_request_to_google_sheet(sheet_id: str, package_data: dict, worksheet_name: str = "package_requests"):
    client = get_gspread_client(readonly=False)

    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        package_data.get("name", ""),
        package_data.get("phone", ""),
        package_data.get("email", ""),
        package_data.get("package_interest", ""),
        package_data.get("travel_dates", ""),
        package_data.get("passengers", ""),
        package_data.get("notes", ""),
        package_data.get("status", "new")
    ]

    worksheet.append_row(row)