import requests
import json

BASE_URL = "http://127.0.0.1:8002"

def test_ingest():
    print("\n--- Test 1: Ingesta de Documento ---")
    url = f"{BASE_URL}/ingest-text"
    payload = {
        "content": "Supabase es una alternativa de código abierto a Firebase. Proporciona una base de datos Postgres, autenticación, APIs instantáneas, funciones Edge, suscripciones en tiempo real y almacenamiento.",
        "filename": "que_es_supabase.txt"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Ingesta exitosa:", response.json())
        else:
            print("❌ Error en ingesta:", response.text)
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

def test_chat():
    print("\n--- Test 2: Chat RAG ---")
    url = f"{BASE_URL}/chat"
    payload = {
        "question": "¿Qué es Supabase y qué características tiene?"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "respuesta_ia" in data:
                print("✅ Respuesta del Chat:")
                print(f"🤖 IA: {data.get('respuesta_ia')}")
                print(f"📄 Fuentes encontradas: {len(data.get('fuentes', []))}")
            else:
                print("⚠️ Respuesta inesperada (posible error capturado):")
                print(json.dumps(data, indent=2))
        else:
            print("❌ Error en chat:", response.text)
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    # Primero probamos la ingesta
    test_ingest()
    
    # Luego probamos el chat
    test_chat()
