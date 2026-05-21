from dotenv import load_dotenv
import os

from google_sheets_reader import (
    load_packages_from_google_sheet,
    load_business_info_from_google_sheet
)

from bot_logic import handle_user_message

load_dotenv("env.env")

sheet_id = os.getenv("GOOGLE_SHEET_ID")
worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME")

df = load_packages_from_google_sheet(sheet_id, worksheet_name)
business_info = load_business_info_from_google_sheet(sheet_id)

memory = {
    "last_user_message": "",
    "last_search": "",
    "last_intent": "",
    "interested_packages": [],
    "handoff_requested": False,
    "customer_name": "",
    "customer_phone": "",
    "collecting": ""
}

print("TravelBot is ready. Type 'hi' to start.")
print("Type 'exit' to stop.\n")

while True:
    user_message = input("You: ")

    if user_message.lower().strip() == "exit":
        print("Bot: Goodbye 👋")
        break

    bot_reply = handle_user_message(
        user_message,
        packages_df=df,
        business_info=business_info,
        memory=memory
    )

    print("\nBot:")
    print(bot_reply)
    print("\nMemory:")
    print(memory)
    print("\n" + "-" * 40 + "\n")