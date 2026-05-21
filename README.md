# WhatsApp TravelBot AI

A multilingual WhatsApp chatbot prototype for travel agencies, built with Python, Flask, Meta WhatsApp Cloud API, Google Sheets, and optional Azure OpenAI.

The chatbot supports both English and Spanish customer interactions and was designed as a business-ready prototype for small and medium travel agencies using WhatsApp as a primary customer communication channel.

## Features

- WhatsApp chatbot integration
- Multilingual support (English & Spanish)
- Vacation package search
- Flight quote requests
- Human handoff workflow
- Lead tracking and customer interaction memory
- Google Sheets integration
- Optional GPT-powered query interpretation
- Operational workflow automation
- Structured customer inquiry handling
- Context-aware conversational flows

## Technologies Used

- Python
- Flask
- Meta WhatsApp Cloud API
- Google Sheets API
- Azure OpenAI
- pandas
- gspread
- ngrok
- python-dotenv

## Business Problem

Many small travel agencies receive customer inquiries through WhatsApp but struggle to respond quickly, organize leads, and provide consistent customer support. This chatbot helps automate common customer interactions while allowing human agents to step in when needed.

## Example Use Cases

- Customer asks for beach vacation packages
- Customer requests family-friendly destinations
- Customer asks questions in Spanish
- Customer requests a flight quote
- Customer asks to speak with an advisor
- Travel agency receives structured lead summaries

## AI Features

The chatbot includes an optional Azure OpenAI interpreter that converts natural language customer requests into searchable keywords for improved package recommendations and conversational flexibility.

Example:

> “I’m looking for somewhere warm for my family, maybe all-inclusive.”

The AI interpreter converts flexible requests into searchable travel-related tags and keywords.

## Spanish Language Support

The chatbot automatically detects and handles both English and Spanish customer interactions, including:

- Spanish travel package searches
- Spanish flight quote workflows
- Spanish business information requests
- Spanish human handoff requests

## Architecture

WhatsApp User  
→ Meta WhatsApp Cloud API  
→ Flask Webhook  
→ Bot Logic Engine  
→ Google Sheets Knowledge Base  
→ Optional Azure OpenAI Interpreter  
→ WhatsApp Response / Human Handoff

## Security

This repository does not include API keys, tokens, service account files, or customer data. Environment variables are managed locally and excluded from version control.

## Future Improvements

- Cloud deployment on Azure or AWS
- Multi-client SaaS support
- Analytics dashboard for agencies
- Automated reporting and insights
- Improved recommendation ranking
- Enhanced media and flyer support

## Author

Kelly Aliasgar