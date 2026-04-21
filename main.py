from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import os
import requests
from anthropic import Anthropic
from typing import Dict, List

app = FastAPI(title="Agente Claude WhatsApp")

# Variables de entorno (se configuran en Railway)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")  # Elige uno fuerte, ej: MiTokenSecreto2026!
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")  # Cambia por el modelo más reciente

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Memoria simple de conversaciones (en producción usa Redis o PostgreSQL)
conversation_history: Dict[str, List[dict]] = {}

SYSTEM_PROMPT = """Eres un asistente virtual profesional, amigable y eficiente para [NOMBRE DE TU NEGOCIO]. 
Responde siempre en español de Colombia, de forma clara, concisa y útil. 
Sé empático, resuelve dudas rápidamente y ofrece ayuda adicional cuando sea necesario."""

def get_claude_response(wa_id: str, user_message: str) -> str:
    if wa_id not in conversation_history:
        conversation_history[wa_id] = []
    
    conversation_history[wa_id].append({"role": "user", "content": user_message})
    
    # Mantén solo los últimos 20 mensajes
    if len(conversation_history[wa_id]) > 20:
        conversation_history[wa_id] = conversation_history[wa_id][-20:]
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=conversation_history[wa_id]
        )
        assistant_message = response.content[0].text
        conversation_history[wa_id].append({"role": "assistant", "content": assistant_message})
        return assistant_message
    except Exception as e:
        print(f"Error con Claude: {e}")
        return "Lo siento, tuve un problema técnico. ¿Puedes intentarlo de nuevo?"

def send_whatsapp_message(to: str, text: str):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"  # Versión actual 2026
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"Error enviando mensaje: {resp.text}")

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verificación fallida")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message = value["messages"][0]
            if message.get("type") == "text":
                from_number = message["from"]  # ID de WhatsApp
                text = message["text"]["body"]
                
                print(f"📨 Mensaje recibido de {from_number}: {text}")
                
                response_text = get_claude_response(from_number, text)
                send_whatsapp_message(from_number, response_text)
                
    except Exception as e:
        print(f"Error procesando webhook: {e}")
    
    return {"status": "ok"}  # Siempre responde 200 rápido