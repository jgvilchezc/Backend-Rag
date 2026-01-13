import os
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from services.gemini_service import GeminiService
from services.openai_service import OpenAIService
from services.api_key_service import ApiKeyService
from typing import Optional, List
from fastapi import Header

# Cargar variables de entorno
load_dotenv()

# --- CONFIGURACIÓN ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET") # We need this to verify tokens
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan las credenciales de Supabase en el archivo .env")

# Inicializar Supabase
# Note: We use the server-side key (Service Role potentially) so we can enforce our own RLS logic via logic or passing user_id
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inicializar Servicios LLM
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY es obligatoria para el funcionamiento base (Embeddings).")

gemini_service = GeminiService(GEMINI_API_KEY)
openai_service = OpenAIService(OPENAI_API_KEY) if OPENAI_API_KEY else None
api_key_service = ApiKeyService(supabase)

def get_provider(provider_name: str):
    if provider_name == "openai":
        if not openai_service:
            raise HTTPException(status_code=400, detail="OpenAI no está configurado (falta API Key).")
        return openai_service
    # Default to Gemini
    return gemini_service

app = FastAPI()

# Auth Security Scheme
# Auth Security Scheme
security = HTTPBearer(auto_error=False)

async def get_current_user_or_api_key(
    creds: Optional[HTTPAuthorizationCredentials] = Security(security),
    x_api_key: Optional[str] = Header(None)
):
    """
    Authenticates via JWT (Bearer) OR API Key (X-API-Key header).
    Returns user_id.
    """
    # 1. Try API Key
    if x_api_key:
        user_id = await api_key_service.validate_api_key(x_api_key)
        if user_id:
            return user_id
        # If API key provided but invalid, fail strictly? Or fallthrough?
        # Typically fail strictly if header is present.
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # 2. Try JWT
    if creds:
        token = creds.credentials
        try:
            if SUPABASE_JWT_SECRET:
                 payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
            else:
                 # Fallback (Unsafe) - Dev only
                 payload = jwt.decode(token, options={"verify_signature": False})
            
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Token invalido: falta 'sub'")
            return user_id
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expirado")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Token invalido: {str(e)}")

    # 3. No credentials
    raise HTTPException(status_code=401, detail="Authentication required (Bearer Token or X-API-Key)")

# Alias for backward compatibility if needed, though we will replace usage
get_current_user = get_current_user_or_api_key

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS ---
class DocumentText(BaseModel):
    content: str
    filename: str

class ChatSession(BaseModel):
    id: str
    title: str
    created_at: str

class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str

class CreateSessionRequest(BaseModel):
    title: str = "New Chat"

class Query(BaseModel):
    question: str
    provider: Optional[str] = "gemini" # 'gemini' or 'openai' or 'anthropic'
    session_id: Optional[str] = None # Optional session ID for history

class CreateApiKeyRequest(BaseModel):
    name: str

@app.get("/")
def read_root():
    return {
        "status": "ok", 
        "message": "Cerebro RAG Activo (Multi-Provider + Auth + API Keys)", 
        "providers": {
            "gemini": True,
            "openai": openai_service is not None
        }
    }

# --- ENDPOINT: API KEY MANAGEMENT ---
@app.post("/auth/api-keys")
async def create_api_key(req: CreateApiKeyRequest, user_id: str = Depends(get_current_user_or_api_key)):
    try:
        return await api_key_service.create_api_key(user_id, req.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/api-keys")
async def list_api_keys(user_id: str = Depends(get_current_user_or_api_key)):
    try:
        # We query the DB directly here for list
        res = supabase.table("api_keys").select("id, name, created_at, last_used_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/auth/api-keys/{key_id}")
async def delete_api_key(key_id: str, user_id: str = Depends(get_current_user_or_api_key)):
    try:
        supabase.table("api_keys").delete().eq("id", key_id).eq("user_id", user_id).execute()
        return {"status": "success"}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT 1: INGESTA (SIEMPRE GEMINI PARA EMBEDDINGS) ---
@app.post("/ingest-text")
async def ingest_text(doc: DocumentText, user_id: str = Depends(get_current_user_or_api_key)):
    try:
        print(f"DEBUG: Ingestando {doc.filename} para usuario {user_id}")
        # 1. Embedding (Gemini)
        vector = await gemini_service.get_embedding(doc.content)
        
        # 2. Guardar DB con user_id
        padre = supabase.table("documents").insert({
            "content": doc.content, 
            "filename": doc.filename,
            "user_id": user_id
        }).execute()
        padre_id = padre.data[0]['id']
        
        supabase.table("documents_chunks").insert({
            "document_id": padre_id,
            "content": doc.content,
            "embedding_gemini": vector,
            "user_id": user_id
        }).execute()
        
        return {"status": "success", "id": padre_id, "provider": "gemini"}
    except Exception as e:
        print(f"ERROR ingest-text: {e}")
        return {"status": "error", "message": f"Error ingesta: {str(e)}"}

@app.post("/ingest-file")
async def ingest_file(file: UploadFile = File(...), user_id: str = Depends(get_current_user_or_api_key)):
    try:
        print(f"DEBUG: Procesando archivo {file.filename} ({file.content_type}) para usuario {user_id}")
        content_text = ""
        
        if file.content_type == "application/pdf":
            import io
            from pypdf import PdfReader
            content = await file.read()
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages:
                content_text += page.extract_text() + "\n"
                
        elif file.content_type.startswith("image/"):
            # Usamos Gemini Vision por defecto
            content_text = await gemini_service.describe_image(await file.read())
            
        elif file.content_type in ["text/plain", "text/markdown", "text/csv"]:
            content_text = (await file.read()).decode("utf-8")
        else:
             raise HTTPException(status_code=400, detail="Tipo de archivo no soportado")

        if not content_text.strip():
             raise HTTPException(status_code=400, detail="No se pudo extraer texto")

        # Ingesta (Embedding Gemini)
        vector = await gemini_service.get_embedding(content_text)
        
        padre = supabase.table("documents").insert({
            "content": content_text, 
            "filename": file.filename,
            "user_id": user_id
        }).execute()
        padre_id = padre.data[0]['id']
        
        supabase.table("documents_chunks").insert({
            "document_id": padre_id,
            "content": content_text,
            "embedding_gemini": vector,
            "user_id": user_id
        }).execute()
        
        return {"status": "success", "id": padre_id}

    except Exception as e:
        error_msg = str(e)
        print(f"ERROR ingest-file: {error_msg}")
        if "429" in error_msg:
             return {"status": "error", "message": "⚠️ Cuota excedida (Gemini)."}
        return {"status": "error", "message": str(e)}

# --- ENDPOINT 2: CHAT (MULTI-PROVIDER) ---
# --- ENDPOINT 3: CHAT HISTORY & SESSIONS ---

@app.get("/chat/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_or_api_key)):
    """List all chat sessions for the user"""
    try:
        response = supabase.table("chat_sessions") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/sessions")
async def create_session(req: CreateSessionRequest, user_id: str = Depends(get_current_user_or_api_key)):
    """Create a new chat session explicitly"""
    try:
        response = supabase.table("chat_sessions").insert({
            "user_id": user_id,
            "title": req.title
        }).execute()
        
        if not response.data:
             raise HTTPException(status_code=500, detail="Failed to create session")
             
        return response.data[0]
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/sessions/{session_id}/messages")
async def get_session_history(session_id: str, user_id: str = Depends(get_current_user_or_api_key)):
    """Get full history for a session"""
    try:
        # Verify ownership (RLS handles it, but good to be explicit/safe)
        # We just query filtering by session_id. RLS should filter by user_id implicitly/explicitly.
        response = supabase.table("chat_messages") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("created_at", desc=False) \
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(get_current_user_or_api_key)):
    """Delete a session"""
    try:
        # RLS should ensure user only deletes their own
        supabase.table("chat_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
        return {"status": "success"}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))


# --- MODIFIED CHAT ENDPOINT ---
@app.post("/chat")
async def chat(query: Query, user_id: str = Depends(get_current_user_or_api_key)):
    try:
        provider_name = query.provider or "gemini"
        session_id = query.session_id
        
        print(f"DEBUG: Chat request - Pregunta: '{query.question}' - Provider: {provider_name} - User: {user_id} - Session: {session_id}")
        
        # 0. Gestionar Sesión
        # Si no hay session_id, creamos una nueva
        if not session_id:
            # Create a title based on first few words? Or just "New Chat"
            title_snippet = (query.question[:30] + '...') if len(query.question) > 30 else query.question
            new_session = supabase.table("chat_sessions").insert({
                "user_id": user_id,
                "title": title_snippet
            }).execute()
            if new_session.data:
                session_id = new_session.data[0]['id']
                print(f"DEBUG: Created new session {session_id}")
        
        # Guardar mensaje del usuario
        if session_id:
             supabase.table("chat_messages").insert({
                "session_id": session_id,
                "role": "user",
                "content": query.question,
                "user_id": user_id
            }).execute()

        # 1. Búsqueda Semántica
        query_vector = await gemini_service.get_embedding(query.question, task_type="retrieval_query")
        
        # Llamamos al RPC con el filtro de user_id
        rpc_response = supabase.rpc("match_documents_gemini", {
            "query_embedding": query_vector,
            "match_threshold": 0.1, 
            "match_count": 5,
            "filter_user_id": user_id 
        }).execute()
        
        contexto_chunks = rpc_response.data
        
        # Enriquecer con filename 
        if contexto_chunks:
            doc_ids = list(set([c['document_id'] for c in contexto_chunks]))
            docs_info = supabase.table("documents").select("id, filename").in_("id", doc_ids).execute()
            map_files = {d['id']: d['filename'] for d in docs_info.data}
            for c in contexto_chunks:
                c['filename'] = map_files.get(c['document_id'], "Unknown")

        contexto_str = "\n\n".join([f"Fuente ({c.get('filename')}): {c['content']}" for c in contexto_chunks])
        
        # 2. Generación
        selected_service = get_provider(provider_name)
        
        # Fetch recent history for context (last 6 messages)
        chat_history = []
        if session_id:
            try:
                hist_response = supabase.table("chat_messages") \
                    .select("role, content") \
                    .eq("session_id", session_id) \
                    .order("created_at", desc=True) \
                    .limit(6) \
                    .execute()
                # Reverse to chronological order for LLM
                if hist_response.data:
                    chat_history = hist_response.data[::-1]
            except Exception as e:
                print(f"WARN: Could not fetch history: {e}")

        print(f"DEBUG: Generando respuesta con {provider_name.upper()}...")
        respuesta = await selected_service.generate_response(query.question, contexto_str, history=chat_history)
        
        # Guardar respuesta de la IA
        if session_id:
             supabase.table("chat_messages").insert({
                "session_id": session_id,
                "role": "assistant",
                "content": respuesta,
                "provider": provider_name,
                "user_id": user_id
            }).execute()

        return {
            "respuesta_ia": respuesta,
            "fuentes": contexto_chunks,
            "provider": provider_name,
            "session_id": session_id
        }

    except Exception as e:
        print(f"ERROR chat: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/documents")
async def list_documents(user_id: str = Depends(get_current_user_or_api_key)):
    # Filtrar documentos por usuario
    return supabase.table("documents").select("id, filename, created_at").eq("user_id", user_id).order("id", desc=True).execute().data

@app.get("/documents/{doc_id}")
async def get_document_content(doc_id: str, user_id: str = Depends(get_current_user_or_api_key)):
    try:
        # Check ownership and get content
        response = supabase.table("documents").select("*").eq("id", doc_id).eq("user_id", user_id).execute()
        if not response.data:
             raise HTTPException(status_code=404, detail="Document not found or access denied")
        return response.data[0]
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))