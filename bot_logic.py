# =========================================
# TRAVELBOT CONVERSATION LOGIC
# =========================================

import os
import re

from openai import AzureOpenAI

from google_sheets_reader import (
    save_lead_to_google_sheet,
    save_flight_request_to_google_sheet,
    save_package_request_to_google_sheet
)


def detect_language(message):
    msg = message.lower().strip()

    spanish_words = [
        "hola", "quiero", "quisiera", "busco", "necesito",
        "paquete", "paquetes", "viaje", "viajes", "vacaciones",
        "playa", "calor", "caliente", "soleado", "sol",
        "familia", "niños", "barato", "económico", "economico",
        "oferta", "promoción", "promocion", "asesor", "persona",
        "vuelo", "vuelos", "cotización", "cotizacion",
        "reservar", "reserva", "más", "mas", "información",
        "informacion", "colombia", "san andrés", "san andres",
        "lujo", "más barato", "mas barato",
        "algo más barato", "algo mas barato"
    ]

    spanish_chars = ["á", "é", "í", "ó", "ú", "ñ", "¿", "¡"]

    if any(char in msg for char in spanish_chars):
        return "es"

    if any(word in msg for word in spanish_words):
        return "es"

    return "en"


def get_language(memory, user_message):
    detected = detect_language(user_message)

    if detected == "es":
        memory["language"] = "es"
        return "es"

    return memory.get("language", "en")


def get_main_menu(lang="en"):
    if lang == "es":
        return (
            "Hola 👋 ¡Bienvenido a TravelBot!\n\n"
            "¿Cómo puedo ayudarte hoy?\n\n"
            "1️⃣ Ver paquetes de vacaciones\n"
            "2️⃣ Solicitar cotización de vuelos\n"
            "3️⃣ Hablar con un asesor\n"
            "4️⃣ Información de la agencia"
        )

    return (
        "Hi 👋 Welcome to TravelBot!\n\n"
        "How can I help you today?\n\n"
        "1️⃣ View vacation packages\n"
        "2️⃣ Request a flight quote\n"
        "3️⃣ Talk to a travel advisor\n"
        "4️⃣ Business information"
    )


def is_valid_phone(phone):
    cleaned = re.sub(r"[^\d]", "", phone)
    return 8 <= len(cleaned) <= 15


def create_handoff_summary(memory, business_info=None):
    if not memory:
        return "New customer needs assistance."

    last_search = memory.get("last_search", "")
    interested_packages = memory.get("interested_packages", [])
    last_message = memory.get("last_user_message", "")

    packages_text = ""
    if interested_packages:
        packages_text = "\n".join([f"- {p}" for p in interested_packages])

    business_name = ""
    if business_info:
        business_name = business_info.get("business_name", "Travel Agency")

    return (
        f"📩 New Customer Handoff - {business_name}\n\n"
        f"🔎 Last search: {last_search}\n\n"
        f"🎯 Interested packages:\n{packages_text}\n\n"
        f"💬 Last message: {last_message}\n\n"
        f"📌 Action: Follow up with customer"
    )


# =========================================
# GPT TRAVEL INTERPRETER
# =========================================

def gpt_interpret_travel_request(message, lang="en"):
    use_gpt = os.getenv("USE_GPT_INTERPRETER", "false").lower() == "true"

    if not use_gpt:
        return None

    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not api_key or not endpoint or not deployment:
        print("[GPT INTERPRETER SKIPPED] Missing Azure OpenAI env variables", flush=True)
        return None

    try:
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2024-12-01-preview"
        )

        available_destinations = [
            "Aruba", "San Andrés", "Panama", "Coffee Region", "Cartagena",
            "Salento", "Dubai", "Maldives", "Caribbean", "Colombia", "Central America"
        ]

        available_categories = [
            "beach", "hot", "warm", "sunny", "tropical", "family", "kids",
            "couples", "romantic", "honeymoon", "budget", "affordable",
            "cheap", "sale", "hot sale", "discount", "luxury", "premium",
            "deluxe", "nature", "eco", "mountains", "coffee", "culture",
            "shopping", "city", "adventure", "relaxation", "all-inclusive",
            "resort", "hotel"
        ]

        destination_context = ", ".join(available_destinations)
        category_context = ", ".join(available_categories)

        if lang == "es":
            system_prompt = f"""
Eres un intérprete de intención para una agencia de viajes por WhatsApp.

Tu trabajo es convertir el mensaje del cliente en palabras clave cortas para buscar paquetes turísticos.

NO respondas al cliente.
NO expliques nada.
Devuelve solamente palabras clave separadas por comas.

Usa estas opciones reales del catálogo cuando sean relevantes.

Destinos disponibles:
{destination_context}

Categorías disponibles:
{category_context}

Incluye palabras clave en español e inglés cuando sea útil.
Si el mensaje coincide con un destino disponible, incluye ese destino exacto.
Si el mensaje coincide con una categoría disponible, incluye esa categoría exacta.
"""
        else:
            system_prompt = f"""
You are a travel intent interpreter for a WhatsApp travel agency chatbot.

Your job is to convert the customer's message into short searchable travel keywords.

Do not answer the customer.
Do not explain anything.
Return only comma-separated search keywords.

Use these real catalog options when relevant.

Available destinations:
{destination_context}

Available categories:
{category_context}

Always include simple searchable words that may match package tags.
If the message matches an available destination, include that exact destination.
If the message matches an available category, include that exact category.
"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=100,
            temperature=0.2
        )

        keywords = response.choices[0].message.content.strip()

        if keywords:
            print("\n[GPT INTERPRETED QUERY]", flush=True)
            print(keywords, flush=True)
            print("", flush=True)
            return message + " " + keywords

        return None

    except Exception as e:
        print("\n[GPT INTERPRETER ERROR]", flush=True)
        print(e, flush=True)
        print("", flush=True)
        return None


# =========================================
# CONVERSATIONAL REFINEMENT
# =========================================

def build_refined_query(user_message, memory):
    msg = user_message.lower().strip()

    if not memory.get("last_search"):
        return None

    refinement_terms = []

    if any(x in msg for x in [
        "cheaper", "cheap", "budget", "affordable", "less expensive",
        "barato", "barata", "económico", "economico", "más barato", "mas barato",
        "algo más barato", "algo mas barato"
    ]):
        refinement_terms.append("budget affordable sale discount hot sale oferta promoción mejor precio")

    if any(x in msg for x in [
        "luxury", "premium", "deluxe", "fancy", "more luxury",
        "lujo", "más lujo", "mas lujo"
    ]):
        refinement_terms.append("luxury premium deluxe resort hotel lujo")

    if any(x in msg for x in [
        "family", "kids", "children", "for families",
        "familia", "niños", "ninos", "para familia", "con niños", "con ninos"
    ]):
        refinement_terms.append("family kids children resort group familia niños")

    if any(x in msg for x in [
        "relax", "relaxing", "quiet", "rest",
        "descansar", "descanso", "relajante", "tranquilo", "tranquila"
    ]):
        refinement_terms.append("relaxing quiet resort spa beach nature descanso relajacion")

    if any(x in msg for x in [
        "nature", "mountains", "outdoors", "adventure",
        "naturaleza", "montañas", "montanas", "aventura", "campo"
    ]):
        refinement_terms.append("nature outdoors mountains countryside eco adventure naturaleza montaña")

    if any(x in msg for x in [
        "beach", "hot", "sunny", "warm", "island",
        "playa", "calor", "caliente", "sol", "isla"
    ]):
        refinement_terms.append("beach hot warm sunny tropical island playa calor sol")

    if any(x in msg for x in [
        "not beach", "no beach", "not the beach",
        "no playa", "sin playa"
    ]):
        refinement_terms.append("nature mountains countryside coffee culture city hotel naturaleza montaña cultura")

    if not refinement_terms:
        return None

    return " ".join(refinement_terms)


def refinement_intro(lang="en"):
    if lang == "es":
        return "Claro 😊 Refiné la búsqueda con tu nueva preferencia:\n\n"

    return "Sure 😊 I refined the search with your new preference:\n\n"


def looks_like_destination_request(message):
    msg = message.lower().strip()

    cleaned = msg.replace(" ", "")

    travel_keywords = [
    "japan", "tokyo", "dubai", "thailand", "italy",
    "spain", "france", "peru", "brazil", "mexico",
    "miami", "orlando", "aruba", "colombia"
    ]

    if cleaned in travel_keywords:
        return True

    return False


# =========================================
# MAIN MESSAGE HANDLER
# =========================================

def handle_user_message(user_message, packages_df=None, business_info=None, memory=None):
    if memory is None:
        memory = {}

    message = user_message.lower().strip()
    memory["last_user_message"] = user_message
    lang = get_language(memory, user_message)

    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    
    # -------------------------------------
    # HUMAN HANDOFF ANYTIME
    # -------------------------------------

    if message in [
        "agent", "advisor", "human", "person", "asesor", "persona",
        "talk to an advisor", "talk to someone", "speak to someone",
        "representative", "help", "ayuda", "hablar con asesor",
        "hablar con una persona", "quiero un asesor"
    ]:
        memory["handoff_requested"] = True
        memory["last_intent"] = "human_handoff"
        memory["step"] = "handoff"
        memory["collecting"] = ""

        lead_data = {
            "customer_phone": memory.get("customer_phone", ""),
            "customer_name": memory.get("customer_name", ""),
            "last_search": memory.get("last_search", ""),
            "interested_packages": memory.get("interested_packages", []),
            "last_message": memory.get("last_user_message", ""),
            "handoff_requested": True,
            "lead_type": memory.get("lead_type", "general"),
            "status": "new"
        }

        try:
            if sheet_id:
                save_lead_to_google_sheet(sheet_id, lead_data)
        except Exception as e:
            print("[HANDOFF LEAD SAVE ERROR]", e)

        if lang == "es":
            return (
                "Claro 😊 Te conectaré con un asesor de viajes.\n\n"
                "📞 Nuestro equipo te contactará pronto por WhatsApp."
            ), memory

        return (
            "Of course 😊 I’ll connect you with a travel advisor.\n\n"
            "📞 Our team will contact you shortly via WhatsApp."
        ), memory

    # -------------------------------------
    # PACKAGE BOOKING CUSTOMER DETAILS
    # -------------------------------------

    if memory.get("collecting") == "customer_name":
        memory["customer_name"] = user_message.strip()
        memory["collecting"] = "customer_phone"

        if lang == "es":
            return (
                f"Gracias, {memory['customer_name']} 😊\n"
                "¿Cuál es tu número de teléfono?"
            ), memory

        return (
            f"Thanks, {memory['customer_name']} 😊\n"
            "What is your phone number?"
        ), memory

    if memory.get("collecting") == "customer_phone":
        phone_input = user_message.strip()

        if not is_valid_phone(phone_input):
            if lang == "es":
                return (
                    "Ese número no parece válido 📱\n\n"
                    "Por favor escribe un número válido, incluyendo el código del país si es posible.\n"
                    "Ejemplo: +57 300 123 4567"
                ), memory

            return (
                "That doesn’t look like a valid phone number 📱\n\n"
                "Please enter a valid number, including country code if possible.\n"
                "Example: +57 300 123 4567"
            ), memory

        memory["customer_phone"] = phone_input
        memory["collecting"] = ""
        memory["handoff_requested"] = True
        memory["lead_type"] = memory.get("lead_type", "package")

        lead_data = {
            "customer_phone": memory.get("customer_phone", ""),
            "customer_name": memory.get("customer_name", ""),
            "last_search": memory.get("last_search", ""),
            "interested_packages": memory.get("interested_packages", []),
            "last_message": memory.get("last_user_message", ""),
            "handoff_requested": True,
            "lead_type": memory.get("lead_type", "package"),
            "status": "new"
        }

        try:
            if sheet_id:
                save_lead_to_google_sheet(sheet_id, lead_data)
        except Exception as e:
            print("[LEAD SAVE ERROR]", e)

        if lang == "es":
            return (
                "Gracias 😊 Ya compartí tu solicitud con un asesor de viajes.\n\n"
                "📞 Nuestro equipo te contactará pronto por WhatsApp."
            ), memory

        return (
            "Thank you 😊 I’ve shared your request with a travel advisor.\n\n"
            "📞 Our team will contact you shortly via WhatsApp."
        ), memory

    # -------------------------------------
    # FLIGHT REQUEST FLOW
    # -------------------------------------

    if memory.get("step") in [None, "", "start"] and (
        message in [
            "2", "flight", "flights", "quote", "cotizacion", "cotización",
            "vuelo", "vuelos", "book a flight", "book flight", "flight quote",
            "request a flight", "i need a flight", "quiero un vuelo",
            "reservar vuelo", "cotizar vuelo"
        ]
        or "flight" in message
        or "vuelo" in message
    ):
        memory["step"] = "flight_name"
        memory["lead_type"] = "flight"
        memory["flight"] = {}

        if lang == "es":
            return (
                "✈️ Perfecto. Puedo ayudarte a recopilar tu solicitud de vuelo.\n\n"
                "Puedes escribir 'asesor' en cualquier momento para hablar con un asesor.\n\n"
                "¿Cuál es tu nombre completo?"
            ), memory

        return (
            "✈️ Great! I can help collect your flight request.\n\n"
            "You can type 'agent' at any time to talk to a travel advisor.\n\n"
            "What is your full name?"
        ), memory

    if memory.get("step") == "flight_name":
        memory["flight"]["name"] = user_message.strip()
        memory["customer_name"] = user_message.strip()
        memory["step"] = "flight_phone"

        if lang == "es":
            return "📱 ¿Cuál es tu número de celular?", memory

        return "📱 What is your mobile number?", memory

    if memory.get("step") == "flight_phone":
        phone_input = user_message.strip()

        if not is_valid_phone(phone_input):
            if lang == "es":
                return (
                    "Ese número no parece válido 📱\n\n"
                    "Por favor escribe un número válido, incluyendo el código del país si es posible.\n"
                    "Ejemplo: +57 300 123 4567"
                ), memory

            return (
                "That doesn’t look like a valid phone number 📱\n\n"
                "Please enter a valid number, including country code if possible.\n"
                "Example: +57 300 123 4567"
            ), memory

        memory["flight"]["phone"] = phone_input
        memory["customer_phone"] = phone_input
        memory["step"] = "flight_email"

        if lang == "es":
            return "📧 ¿Cuál es tu correo electrónico?", memory

        return "📧 What is your email address?", memory

    if memory.get("step") == "flight_email":
        memory["flight"]["email"] = user_message.strip()
        memory["step"] = "flight_type"

        if lang == "es":
            return "✈️ ¿El vuelo es solo ida, ida y vuelta, o multidestino?", memory

        return "✈️ Is this one-way, round trip, or multi-destination?", memory

    if memory.get("step") == "flight_type":
        memory["flight"]["trip_type"] = user_message.strip()
        memory["step"] = "flight_origin"

        if lang == "es":
            return "🛫 ¿Desde qué ciudad viajas?", memory

        return "🛫 What city are you flying FROM?", memory

    if memory.get("step") == "flight_origin":
        memory["flight"]["origin"] = user_message.strip()
        memory["step"] = "flight_destination"

        if lang == "es":
            return "🛬 ¿Cuál es tu destino?", memory

        return "🛬 What is your destination?", memory

    if memory.get("step") == "flight_destination":
        memory["flight"]["destination"] = user_message.strip()
        memory["step"] = "flight_departure_date"

        if lang == "es":
            return "📅 ¿Cuál es tu fecha de salida?", memory

        return "📅 What is your departure date?", memory

    if memory.get("step") == "flight_departure_date":
        memory["flight"]["departure_date"] = user_message.strip()

        trip_type = memory["flight"].get("trip_type", "").lower()

        if "round" in trip_type or "return" in trip_type or "ida y vuelta" in trip_type:
            memory["step"] = "flight_return_date"

            if lang == "es":
                return "📅 ¿Cuál es tu fecha de regreso?", memory

            return "📅 What is your return date?", memory

        memory["flight"]["return_date"] = ""
        memory["step"] = "flight_passengers"

        if lang == "es":
            return "👨‍👩‍👧 ¿Cuántos pasajeros viajan?", memory

        return "👨‍👩‍👧 How many passengers?", memory

    if memory.get("step") == "flight_return_date":
        memory["flight"]["return_date"] = user_message.strip()
        memory["step"] = "flight_passengers"

        if lang == "es":
            return "👨‍👩‍👧 ¿Cuántos pasajeros viajan?", memory

        return "👨‍👩‍👧 How many passengers?", memory

    if memory.get("step") == "flight_passengers":
        memory["flight"]["passengers"] = user_message.strip()
        memory["step"] = "flight_preferences"

        if lang == "es":
            return (
                "🎒 ¿Tienes alguna preferencia?\n\n"
                "Por ejemplo: equipaje, selección de asiento, clase, aerolínea preferida, tarifa reembolsable o notas especiales."
            ), memory

        return (
            "🎒 Any preferences?\n\n"
            "For example: baggage, seat selection, class, preferred airline, refundable fare, or special notes."
        ), memory

    if memory.get("step") == "flight_preferences":
        memory["flight"]["preferences"] = user_message.strip()
        memory["flight"]["status"] = "new"

        flight = memory["flight"]

        try:
            if sheet_id:
                save_flight_request_to_google_sheet(sheet_id, flight)
        except Exception as e:
            print("[FLIGHT SAVE ERROR]", e)

        memory["step"] = "handoff"
        memory["handoff_requested"] = True

        if lang == "es":
            summary = (
                "✈️ Resumen de solicitud de vuelo:\n\n"
                f"Nombre: {flight.get('name', '')}\n"
                f"Teléfono: {flight.get('phone', '')}\n"
                f"Correo: {flight.get('email', '')}\n"
                f"Tipo de viaje: {flight.get('trip_type', '')}\n"
                f"Desde: {flight.get('origin', '')}\n"
                f"Hacia: {flight.get('destination', '')}\n"
                f"Fecha de salida: {flight.get('departure_date', '')}\n"
                f"Fecha de regreso: {flight.get('return_date', '')}\n"
                f"Pasajeros: {flight.get('passengers', '')}\n"
                f"Preferencias: {flight.get('preferences', '')}"
            )

            return (
                "Gracias 😊 Ya recopilé tu solicitud de vuelo.\n\n"
                f"{summary}\n\n"
                "✅ Te conectaré con un asesor que revisará disponibilidad y precios.\n\n"
                "📞 Nuestro equipo te contactará pronto por WhatsApp."
            ), memory

        summary = (
            "✈️ Flight Request Summary:\n\n"
            f"Name: {flight.get('name', '')}\n"
            f"Phone: {flight.get('phone', '')}\n"
            f"Email: {flight.get('email', '')}\n"
            f"Trip Type: {flight.get('trip_type', '')}\n"
            f"From: {flight.get('origin', '')}\n"
            f"To: {flight.get('destination', '')}\n"
            f"Departure Date: {flight.get('departure_date', '')}\n"
            f"Return Date: {flight.get('return_date', '')}\n"
            f"Passengers: {flight.get('passengers', '')}\n"
            f"Preferences: {flight.get('preferences', '')}"
        )

        return (
            "Thank you 😊 I’ve collected your flight request.\n\n"
            f"{summary}\n\n"
            "✅ I’ll connect you with a travel advisor who will check availability and pricing.\n\n"
            "📞 Our team will contact you shortly via WhatsApp."
        ), memory

    # -------------------------------------
    # MAIN MENU
    # -------------------------------------

    if message in ["hi", "hello", "hola", "menu", "start", "inicio"]:
        return get_main_menu(lang), memory

    # -------------------------------------
    # VACATION PACKAGE BROWSING
    # -------------------------------------

    if memory.get("step") in [None, "", "start"] and message in [
        "1", "packages", "vacation packages", "paquetes", "viajes"
    ]:
        if lang == "es":
            return (
                "Perfecto ✈️ ¿Qué tipo de paquete estás buscando?\n\n"
                "Puedes escribir cosas como:\n"
                "- Aruba\n"
                "- Caribe\n"
                "- Colombia\n"
                "- Familia\n"
                "- Naturaleza\n"
                "- Oferta\n"
                "- Un lugar con calor\n"
                "- Un viaje económico\n"
                "- Un lugar para descansar"
            ), memory

        return (
            "Great ✈️ What kind of package are you looking for?\n\n"
            "You can type things like:\n"
            "- Aruba\n"
            "- Caribbean\n"
            "- Colombia\n"
            "- Family\n"
            "- Nature\n"
            "- Hot sale\n"
            "- Somewhere hot\n"
            "- Cheap vacation\n"
            "- Relaxing place"
        ), memory

    # -------------------------------------
    # BOOK PACKAGE AFTER VIEWING RESULTS
    # -------------------------------------

    if message in [
        "book", "book this package", "reserve", "reservation", "booking",
        "reservar", "reserva", "quiero reservar", "quiero este paquete"
    ]:
        memory["last_intent"] = "booking_request"
        memory["lead_type"] = "package"
        memory["collecting"] = "customer_name"

        if lang == "es":
            return (
                "Perfecto 😊 Un asesor de viajes te ayudará con este paquete.\n\n"
                "¿Cuál es tu nombre?"
            ), memory

        return (
            "Great 😊 I’ll ask a travel advisor to help with this package.\n\n"
            "What is your name?"
        ), memory

    # -------------------------------------
    # MORE OPTIONS
    # -------------------------------------

    if message in ["more", "more options", "see more", "show more", "other options", "más", "mas", "otras opciones", "ver más", "ver mas"]:
        if lang == "es":
            return (
                "Claro 😊 Puedes buscar por:\n\n"
                "- Destino: Aruba, Colombia, Panamá\n"
                "- Región: Caribe, Centroamérica\n"
                "- Categoría: familia, naturaleza, aventura, oferta, descanso\n"
                "- Ideas flexibles: un lugar con calor, viaje económico, lugar para descansar"
            ), memory

        return (
            "Sure 😊 You can search by:\n\n"
            "- Destination: Aruba, Colombia, Panama\n"
            "- Region: Caribbean, Central America\n"
            "- Category: family, nature, adventure, hot sale, relaxation\n"
            "- Flexible ideas: somewhere hot, cheap vacation, relaxing place"
        ), memory

    # -------------------------------------
    # BUSINESS INFO
    # -------------------------------------

    if message in ["4", "info", "business info", "business information",
        "informacion", "información", "información de la agencia",
        "agency info", "agency information",
        "address", "location", "where are you", "where are you located",
        "where is the agency", "hours", "opening hours", "phone", "contact",
        "direccion", "dirección", "ubicacion", "ubicación",
        "donde estan", "dónde están", "donde están", "dónde estan",
        "horario", "horarios", "telefono", "teléfono", "contacto"
    ]:
        if business_info:
            name = business_info.get("business_name", "")
            phone = business_info.get("phone", "")
            whatsapp = business_info.get("whatsapp", "")
            email_sales = business_info.get("email_sales", "")
            email_support = business_info.get("email_support", "")
            address = business_info.get("address", "")
            hours = business_info.get("hours", "")
            website = business_info.get("website", "")
            instagram = business_info.get("instagram", "")
            payment_methods = business_info.get("payment_methods", "")
            payment_qr = business_info.get("payment_qr_link", "")

            if lang == "es":
                return (
                    f"📍 {name}\n"
                    f"📞 Teléfono: {phone}\n"
                    f"💬 WhatsApp: {whatsapp}\n"
                    f"📧 Ventas: {email_sales}\n"
                    f"📧 Soporte: {email_support}\n"
                    f"📍 Dirección: {address}\n"
                    f"🕒 Horario: {hours}\n"
                    f"🌐 Sitio web: {website}\n"
                    f"📸 Instagram: {instagram}\n\n"
                    f"💳 Métodos de pago:\n{payment_methods}\n\n"
                    f"🔗 Link de pago:\n{payment_qr}"
                ), memory

            return (
                f"📍 {name}\n"
                f"📞 Phone: {phone}\n"
                f"💬 WhatsApp: {whatsapp}\n"
                f"📧 Sales: {email_sales}\n"
                f"📧 Support: {email_support}\n"
                f"📍 Address: {address}\n"
                f"🕒 Hours: {hours}\n"
                f"🌐 Website: {website}\n"
                f"📸 Instagram: {instagram}\n\n"
                f"💳 Payment methods:\n{payment_methods}\n\n"
                f"🔗 Payment link:\n{payment_qr}"
            ), memory

        if lang == "es":
            return (
                "Lo siento, no pude cargar la información de la agencia en este momento 😊\n\n"
                "Igualmente puedes pedir hablar con un asesor."
            ), memory

        return (
            "Sorry, I couldn’t load the business information right now 😊\n\n"
            "You can still ask to speak with an advisor."
        ), memory

    # -------------------------------------
    # PACKAGE SEARCH AND REFINEMENT
    # -------------------------------------

    if packages_df is not None:
        from google_sheets_reader import filter_packages, format_packages_for_whatsapp

        refined_query = build_refined_query(user_message, memory)

        if refined_query:
            smart_query = refined_query
            intro = refinement_intro(lang)
        else:
            gpt_query = gpt_interpret_travel_request(user_message, lang=lang)

            if gpt_query:
                smart_query = gpt_query
            else:
                smart_query = interpret_package_query(user_message)

            intro = (
                "Excelente elección 😊 Aquí tienes algunas opciones que coinciden con lo que estás buscando:\n\n"
                if lang == "es"
                else "Great choice 😊 Here are some options that match what you’re looking for:\n\n"
            )

        results = filter_packages(packages_df, smart_query)

        if not results.empty:
            memory["last_search"] = smart_query
            memory["last_intent"] = "package_search"
            memory["lead_type"] = "package"
            memory["interested_packages"] = results["package_name"].head(3).tolist()

            if lang == "es":
                return (
                    intro
                    + format_packages_for_whatsapp(results, lang=lang)
                    + "\n\n¿Qué te gustaría hacer?\n"
                    "➡️ Escribe 'reservar' para solicitar este paquete\n"
                    "➡️ Escribe 'más' para ver otras opciones\n"
                    "➡️ Escribe 'asesor' para hablar con un asesor"
                ), memory

            return (
                intro
                + format_packages_for_whatsapp(results, lang=lang)
                + "\n\nWould you like:\n"
                "➡️ Type 'book' to request this package\n"
                "➡️ Type 'more' to see other options\n"
                "➡️ Type 'agent' to talk to an advisor"
            ), memory

        if looks_like_destination_request(user_message):
            memory["no_package_count"] = memory.get("no_package_count", 0) + 1
            print("[NO PACKAGE COUNT]", memory.get("no_package_count"), flush=True)

            if memory["no_package_count"] >= 3:
                memory["last_intent"] = "fallback_handoff_collecting"
                memory["handoff_requested"] = False
                memory["lead_type"] = "general"
                memory["collecting"] = "customer_name"
                memory["step"] = "no_package_handoff_name"

                if lang == "es":
                    return (
                        "Veo que sigues interesado en ese destino 😊\n\n"
                        "Te voy a conectar con un asesor para ayudarte a cotizarlo.\n\n"
                        "¿Cuál es tu nombre?"
                    ), memory

                return (
                    "I see you’re still interested in that destination 😊\n\n"
                    "I’ll connect you with a travel advisor to help quote it.\n\n"
                    "What is your name?"
                ), memory

            if lang == "es":
                return (
                    "Entiendo 😊 Parece que estás buscando ese destino, "
                    "pero en este momento no tengo paquetes disponibles para esa opción.\n\n"
                    "¿Te gustaría que un asesor te ayude a cotizarlo?\n\n"
                    "➡️ Escribe 'asesor' para hablar con un asesor\n"
                    "➡️ Escribe 'vuelos' para solicitar un vuelo\n"
                    "➡️ Escribe 'paquetes' para ver otros paquetes"
                ), memory

            return (
                "I understand 😊 It looks like you’re searching for that destination, "
                "but I don’t currently have packages available for it.\n\n"
                "Would you like a travel advisor to help quote it?\n\n"
                "➡️ Type 'agent' to speak with an advisor\n"
                "➡️ Type 'flights' to request a flight\n"
                "➡️ Type 'packages' to browse other packages"
            ), memory


    memory["fallback_count"] = memory.get("fallback_count", 0) + 1

    if memory["fallback_count"] >= 3:
        memory["last_intent"] = "human_handoff"
        memory["handoff_requested"] = True
        memory["lead_type"] = memory.get("lead_type", "general")
        memory["collecting"] = "customer_name"
        memory["step"] = "fallback_handoff_name"

        if lang == "es":
            return (
                "Lo siento 😊 Estoy teniendo dificultad para entender tu solicitud.\n\n"
                "Te voy a conectar con un asesor para ayudarte mejor.\n\n"
                "¿Cuál es tu nombre?"
            ), memory

        return (
            "I’m sorry 😊 I’m having trouble understanding your request.\n\n"
            "I’ll connect you with a travel advisor so they can help you better.\n\n"
            "What is your name?"
        ), memory

 

    if lang == "es":
        return (
            "No estoy seguro de haber entendido 😊\n\n"
            "Puedes escribir:\n"
            "- Un destino, como Aruba o Colombia\n"
            "- Una categoría, como familia, playa o naturaleza\n"
            "- Una solicitud flexible, como lugar con calor, viaje económico o lugar para descansar\n\n"
            "O elegir:\n"
            "1️⃣ Paquetes de vacaciones\n"
            "2️⃣ Cotización de vuelos\n"
            "3️⃣ Hablar con un asesor\n"
            "4️⃣ Información de la agencia"
        ), memory

    return (
        "I’m not sure I understood 😊\n\n"
        "You can type:\n"
        "- A destination, like Aruba or Colombia\n"
        "- A category, like family, beach, or nature\n"
        "- A flexible request, like hot weather, cheap vacation, or relaxing place\n\n"
        "Or choose:\n"
        "1️⃣ Vacation packages\n"
        "2️⃣ Flight quote\n"
        "3️⃣ Talk to an advisor\n"
        "4️⃣ Business information"
    ), memory


# =========================================
# SMART PACKAGE INTERPRETATION
# =========================================

def interpret_package_query(message):
    msg = message.lower().strip()

    keyword_map = {
        "calor": "hot warm sunny tropical beach desert playa sol caliente",
        "caliente": "hot warm sunny tropical beach desert playa sol",
        "soleado": "sunny warm beach tropical sol playa",
        "sol": "sunny warm beach tropical playa",
        "clima caliente": "hot warm sunny tropical beach desert playa",

        "hot": "hot warm sunny tropical beach desert",
        "hot weather": "hot warm sunny tropical beach desert",
        "sun": "sunny warm beach tropical",
        "sunny": "sunny warm beach tropical",
        "warm": "warm sunny tropical beach",

        "playa": "beach ocean sea island coastal resort mar isla tropical",
        "mar": "beach ocean sea coastal island playa",
        "isla": "island beach tropical playa",

        "beach": "beach ocean sea island coastal resort",
        "sea": "beach ocean sea coastal island",
        "ocean": "beach ocean sea coastal island",
        "island": "island beach tropical",

        "barato": "budget affordable sale discount hot sale económico oferta promocion",
        "económico": "budget affordable sale discount económico oferta",
        "economico": "budget affordable sale discount económico oferta",
        "oferta": "sale discount hot sale offer promotion oferta promocion",
        "promoción": "sale discount hot sale offer promotion oferta promocion",
        "promocion": "sale discount hot sale offer promotion oferta promocion",
        "mejor precio": "budget affordable sale discount hot sale mejor precio",

        "cheap": "budget affordable sale discount hot sale",
        "affordable": "budget affordable sale discount",
        "low cost": "budget affordable sale discount",
        "not expensive": "budget affordable sale discount",
        "best price": "budget affordable sale discount hot sale",
        "sale": "sale discount hot sale offer promotion",

        "familia": "family kids children resort group familia niños",
        "niños": "family kids children resort niños familia",
        "ninos": "family kids children resort niños familia",

        "family": "family kids children resort group",
        "kids": "family kids children resort",
        "children": "family kids children resort",

        "descansar": "relaxing quiet resort spa beach nature descanso relajacion",
        "descanso": "relaxing quiet resort spa beach nature descanso",
        "relajar": "relaxing quiet resort spa beach nature relajacion",
        "relajante": "relaxing quiet resort spa beach nature",

        "relax": "relaxing quiet resort spa beach nature",
        "relaxing": "relaxing quiet resort spa beach nature",
        "rest": "relaxing quiet resort spa",
        "quiet": "quiet relaxing resort nature",

        "lujo": "luxury premium deluxe resort hotel lujo",
        "luna de miel": "romantic luxury honeymoon resort luna de miel",

        "luxury": "luxury premium deluxe resort hotel",
        "deluxe": "luxury premium deluxe resort hotel",
        "honeymoon": "romantic luxury honeymoon resort",

        "naturaleza": "nature outdoors mountains countryside eco naturaleza montaña",
        "aventura": "adventure outdoors nature activities aventura",
        "montañas": "mountains nature countryside hiking montaña",
        "montanas": "mountains nature countryside hiking montaña",

        "nature": "nature outdoors mountains countryside eco",
        "outdoors": "nature outdoors adventure eco",
        "adventure": "adventure outdoors nature activities",
        "mountains": "mountains nature countryside hiking",

        "ciudad": "city shopping culture hotel ciudad",
        "compras": "shopping city luxury hotel compras",
        "cultura": "culture city history tours cultura",

        "city": "city shopping culture hotel",
        "shopping": "shopping city luxury hotel",
        "culture": "culture city history tours",

        "hotel": "hotel resort accommodation stay",
        "hotels": "hotel resort accommodation stay",
    }

    smart_terms = []

    for phrase, keywords in keyword_map.items():
        if phrase in msg:
            smart_terms.append(keywords)

    if not smart_terms:
        return message

    return message + " " + " ".join(smart_terms)