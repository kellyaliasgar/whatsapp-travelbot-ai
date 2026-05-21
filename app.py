print("🔥 RUNNING UPDATED APP.PY WITH IMAGE SUPPORT + FIXED HANDOFF 🔥", flush=True)

import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from bot_logic import handle_user_message
from google_sheets_reader import load_packages_from_google_sheet

load_dotenv("env.env", override=True)

app = Flask(__name__)
user_states = {}

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "travelbot123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
AGENT_PHONE = os.getenv("AGENT_PHONE")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

packages_df = None

try:
    if GOOGLE_SHEET_ID:
        packages_df = load_packages_from_google_sheet(GOOGLE_SHEET_ID)
        print(f"[PACKAGES LOADED AT STARTUP] {len(packages_df)} packages loaded", flush=True)
    else:
        print("[PACKAGES NOT LOADED] GOOGLE_SHEET_ID missing in env.env", flush=True)
except Exception as e:
    print("[PACKAGES LOAD ERROR]", e, flush=True)


def get_default_state():
    return {
        "step": "start",
        "collected_data": {},
        "interested_packages": [],
        "last_search": None
    }


def reload_packages():
    global packages_df

    try:
        if GOOGLE_SHEET_ID:
            latest_packages_df = load_packages_from_google_sheet(GOOGLE_SHEET_ID)
            packages_df = latest_packages_df
            print(f"[PACKAGES RELOADED] {len(latest_packages_df)} packages loaded", flush=True)
            return latest_packages_df

        print("[PACKAGES NOT RELOADED] GOOGLE_SHEET_ID missing", flush=True)
        return packages_df

    except Exception as e:
        print("[PACKAGES RELOAD ERROR]", e, flush=True)
        return packages_df


def send_whatsapp_message(to_number, message_text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        print("SEND ERROR:", response.text, flush=True)

    print("----- SEND MESSAGE RESPONSE -----", flush=True)
    print(response.status_code, flush=True)
    print(response.text, flush=True)
    print("---------------------------------", flush=True)

    return response


def send_whatsapp_image(to_number, image_url, caption=""):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {
            "link": image_url,
            "caption": caption[:1024]
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        print("SEND IMAGE ERROR:", response.text, flush=True)

    print("----- SEND IMAGE RESPONSE -----", flush=True)
    print(response.status_code, flush=True)
    print(response.text, flush=True)
    print("--------------------------------", flush=True)

    return response


def is_valid_image_url(image_url):
    if not image_url:
        return False

    image_url = str(image_url).strip()

    if image_url == "":
        return False

    if image_url.lower() in ["image pending", "pending", "none", "nan"]:
        return False

    if not image_url.startswith("http"):
        return False

    return True


def send_package_images_if_available(to_number, state, latest_packages_df):
    if latest_packages_df is None or latest_packages_df.empty:
        return

    if "image_url" not in latest_packages_df.columns:
        return

    interested_packages = state.get("interested_packages", [])

    if not interested_packages:
        return

    lang = state.get("language", "en")
    price_label = "Desde" if lang == "es" else "From"

    for package_name in interested_packages[:3]:
        matches = latest_packages_df[
            latest_packages_df["package_name"].astype(str).str.strip() == str(package_name).strip()
        ]

        if matches.empty:
            continue

        row = matches.iloc[0]
        image_url = row.get("image_url", "")
        destination = row.get("destination", "")
        price = row.get("price_from", "")
        currency = row.get("currency", "")

        if not is_valid_image_url(image_url):
            continue

        caption = f"🌍 {package_name}"

        if destination:
            caption += f"\n📍 {destination}"

        if price and currency:
            caption += f"\n💰 {price_label}: {currency} ${price}"

        send_whatsapp_image(to_number, image_url, caption)


def build_agent_flight_message(customer_number, state):
    flight = state.get("flight", {})

    return (
        "📩 New Flight Request\n\n"
        f"Customer WhatsApp: {customer_number}\n\n"
        f"Name: {flight.get('name', '')}\n"
        f"Email: {flight.get('email', '')}\n"
        f"Trip Type: {flight.get('trip_type', '')}\n"
        f"From: {flight.get('origin', '')}\n"
        f"To: {flight.get('destination', '')}\n"
        f"Departure Date: {flight.get('departure_date', '')}\n"
        f"Return Date: {flight.get('return_date', '')}\n"
        f"Passengers: {flight.get('passengers', '')}\n"
        f"Preferences: {flight.get('preferences', '')}\n\n"
        "Status: new"
    )


def build_agent_package_message(customer_number, state):
    interested_packages = state.get("interested_packages", [])
    interested_text = ", ".join(interested_packages) if interested_packages else "Not specified"

    return (
        "📩 New Package Request\n\n"
        f"Customer WhatsApp: {customer_number}\n\n"
        f"Name: {state.get('customer_name', '')}\n"
        f"Last Search: {state.get('last_search', '')}\n"
        f"Interested Packages: {interested_text}\n\n"
        "Status: new"
    )


def build_agent_handoff_message(customer_number, state):
    interested_packages = state.get("interested_packages", [])
    interested_text = ", ".join(interested_packages) if interested_packages else "Not specified"

    flight = state.get("flight", {})

    flight_text = ""
    if flight:
        flight_text = (
            "\n\nPartial Flight Details:\n"
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
        "📩 New Human Handoff Request\n\n"
        f"Customer WhatsApp: {customer_number}\n\n"
        f"Current Step: {state.get('step', '')}\n"
        f"Lead Type: {state.get('lead_type', 'general')}\n"
        f"Language: {state.get('language', 'en')}\n\n"
        f"Name: {state.get('customer_name', 'Not collected')}\n"
        f"Last Search: {state.get('last_search', 'Not specified')}\n"
        f"Interested Packages: {interested_text}\n"
        f"Last Message: {state.get('last_user_message', '')}"
        f"{flight_text}\n\n"
        "Status: new"
    )


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        print("----- META VERIFY DEBUG -----", flush=True)
        print("Mode:", repr(mode), flush=True)
        print("Token:", repr(token), flush=True)
        print("Challenge:", repr(challenge), flush=True)

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return str(challenge), 200

        return "Verification failed", 403

    if request.method == "POST":
        data = request.get_json()

        print("----- INCOMING WHATSAPP POST -----", flush=True)
        print(data, flush=True)
        print("----------------------------------", flush=True)

        try:
            value = data["entry"][0]["changes"][0]["value"]

            if "messages" not in value:
                return jsonify({"status": "ignored"}), 200

            message = value["messages"][0]
            from_number = message["from"]

            if from_number not in user_states:
                user_states[from_number] = get_default_state()

            state = user_states[from_number]

            if message["type"] == "text":
                user_text = message["text"]["body"].strip()

                if user_text.lower() in ["reset", "restart", "nuevo", "reiniciar"]:
                    user_states[from_number] = get_default_state()

                    reply = (
                        "Conversación reiniciada. Ya puedes comenzar una nueva solicitud de viaje."
                        if user_text.lower() in ["nuevo", "reiniciar"]
                        else "Conversation reset. You can start a new trip request."
                    )

                    send_whatsapp_message(from_number, reply)
                    return jsonify({"status": "reset"}), 200

                latest_packages_df = reload_packages()

                if state.get("step") == "start" and user_text.lower() in ["hi", "hello", "hola"]:
                    if user_text.lower() == "hola":
                        state["language"] = "es"
                        reply = (
                            "Hola 👋 Soy tu asistente de viajes.\n\n"
                            "Puedo ayudarte a encontrar paquetes de viaje ✈️\n\n"
                            "Escribe:\n"
                            "1️⃣ Paquetes\n"
                            "2️⃣ Vuelos\n"
                            "3️⃣ Hablar con un asesor"
                        )
                    else:
                        reply = (
                            "Hi 👋 I'm your Travel Assistant!\n\n"
                            "I can help you find travel packages ✈️\n\n"
                            "Type:\n"
                            "1️⃣ Packages\n"
                            "2️⃣ Flights\n"
                            "3️⃣ Talk to an agent"
                        )

                    updated_state = state

                else:
                    previous_collecting = state.get("collecting")

                    reply, updated_state = handle_user_message(
                        user_text,
                        packages_df=latest_packages_df,
                        memory=state
                    )

                    if updated_state.get("last_intent") == "package_search":
                        send_package_images_if_available(
                            from_number,
                            updated_state,
                            latest_packages_df
                        )

                    # Universal human handoff notification
                    # Sends immediately using the customer's WhatsApp number
                    if (
                        updated_state.get("last_intent") == "human_handoff"
                        and not updated_state.get("agent_notified_handoff")
                    ):
                        if AGENT_PHONE:
                            agent_message = build_agent_handoff_message(from_number, updated_state)
                            send_whatsapp_message(AGENT_PHONE, agent_message)
                            updated_state["agent_notified_handoff"] = True
                        else:
                            print("[AGENT PHONE MISSING] Add AGENT_PHONE to env.env", flush=True)

                    # Completed flight request notification
                    if (
                        updated_state.get("lead_type") == "flight"
                        and updated_state.get("step") == "handoff"
                        and not updated_state.get("agent_notified_flight")
                        and updated_state.get("last_intent") != "human_handoff"
                    ):
                        if AGENT_PHONE:
                            agent_message = build_agent_flight_message(from_number, updated_state)
                            send_whatsapp_message(AGENT_PHONE, agent_message)
                            updated_state["agent_notified_flight"] = True
                        else:
                            print("[AGENT PHONE MISSING] Add AGENT_PHONE to env.env", flush=True)

                    # Completed package lead notification
                    if previous_collecting == "customer_phone" and updated_state.get("collecting") == "":
                        if updated_state.get("lead_type") == "package":
                            if AGENT_PHONE:
                                agent_message = build_agent_package_message(from_number, updated_state)
                                send_whatsapp_message(AGENT_PHONE, agent_message)
                            else:
                                print("[AGENT PHONE MISSING] Add AGENT_PHONE to env.env", flush=True)

                user_states[from_number] = updated_state

                print("[BOT REPLY]", flush=True)
                print(reply, flush=True)

                if not reply:
                    reply = "I received your message, but I could not generate a proper response. Please try again."

                send_whatsapp_message(from_number, reply)

            else:
                reply = "I received your message. For now, please send text messages while I finish connecting media support."
                send_whatsapp_message(from_number, reply)

        except Exception as e:
            print("ERROR:", e, flush=True)

        return jsonify({"status": "received"}), 200


@app.route("/", methods=["GET"])
def home():
    return "TravelBot Flask app is running", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)