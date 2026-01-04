import google.generativeai as genai
from typing import List, Dict
from .llm_provider import LLMProvider
import os
from PIL import Image
import io
import asyncio
import time

class GeminiService(LLMProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API Key is required")
        genai.configure(api_key=api_key)
        self.embedding_model = "models/text-embedding-004"
        # Changed to stable model with better free tier quotas
        self.generation_model = "models/gemini-flash-latest"

    async def _execute_with_retry(self, func, *args, **kwargs):

        retries = 3
        base_delay = 2
        
        last_error = None
        for attempt in range(retries):
            try:
                # We assume func is an async function or we await it result if it's a coroutine
                # But here we are calling library methods.
                # Let's wrap the library call in a lambda/partial.
                if asyncio.iscoroutinefunction(func):
                   return await func(*args, **kwargs)
                else:
                   # If it's a sync function make sure to run it in thread if blocking, 
                   # but here we just want to catch the exception.
                   return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "resource_exhausted" in error_msg:
                    if attempt < retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        print(f"⚠️ Gemini Quota Limit (429). Retrying in {sleep_time}s...")
                        await asyncio.sleep(sleep_time)
                        continue
                raise e
        raise last_error

    async def generate_response(self, prompt: str, context: str, history: List[Dict[str, str]] = []) -> str:
        model = genai.GenerativeModel(self.generation_model)
        
        # Format history for the prompt
        history_text = ""
        if history:
            history_text = "Historial de conversación reciente:\n"
            for msg in history:
                role = "Usuario" if msg.get("role") == "user" else "Asistente"
                content = msg.get("content", "")
                history_text += f"{role}: {content}\n"
            history_text += "\n"

        full_prompt = f"""
        Eres Nexus RAG, un asistente IA amigable, profesional y colaborativo.
        Tu objetivo es ayudar al usuario respondiendo preguntas basándote PRINCIPALMENTE en la información de contexto proporcionada.
        
        Reglas:
        1. Usa un tono conversacional y cercano, pero mantén la profesionalidad.
        2. Si la respuesta está en el contexto, explícala claramente.
        3. Si la respuesta NO está en el contexto pero es una pregunta general de saludo o conversación (ej. "Hola", "¿Cómo estás?"), responde amablemente sin inventar datos del contexto.
        4. Si te preguntan algo específico sobre documentos que NO está en el contexto, di honestamente que no encuentras esa información en los documentos disponibles.
        5. Cita las fuentes implícitamente si es relevante (ej. "Según el documento X...").
        
        {history_text}
        Contexto (Información Recuperada):
        {context}
        
        Pregunta actual:
        {prompt}
        
        Respuesta:
        """
        
        async def _call_api():
            # Try to use async version if available, otherwise sync
            if hasattr(model, 'generate_content_async'):
                response = await model.generate_content_async(full_prompt)
            else:
                response = model.generate_content(full_prompt)
            return response

        try:
            response = await self._execute_with_retry(_call_api)
            return response.text if response.candidates else "No se pudo generar respuesta."
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                raise Exception("⚠️ Has excedido tu cuota gratuita de Gemini (revisa tu plan o límites).")
            raise e

    async def get_embedding(self, text: str, task_type: str = "retrieval_document") -> List[float]:

        try:
            # Run in thread to avoid blocking + retry
            # Run in thread to avoid blocking + retry
            # We wrap the sync call in to_thread inside the retry wrapper, or just use sync call in retry
            # Let's define the wrapper to handle sync calls by just calling them
            # But technically we should await asyncio.to_thread(_call_embed) to not block loop
            # But for simplicity of this fix and to ensure retry works:
            
            result = await self._execute_with_retry(lambda: genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type=task_type
            ))
            return result['embedding']
        except Exception as e:
             if "429" in str(e) or "quota" in str(e).lower():
                raise Exception("⚠️ Cuota de API excedida al generar embedding.")
             raise e

    async def describe_image(self, image_bytes: bytes) -> str:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            model = genai.GenerativeModel(self.generation_model)
            
            async def _call_vision():
                if hasattr(model, 'generate_content_async'):
                    return await model.generate_content_async([
                        "Describe esta imagen con mucho detalle para que pueda ser indexada en una base de conocimientos. Incluye todo el texto visible y detalles visuales importantes.", 
                        image
                    ])
                else:
                    return model.generate_content([
                        "Describe esta imagen con mucho detalle para que pueda ser indexada en una base de conocimientos. Incluye todo el texto visible y detalles visuales importantes.", 
                        image
                    ])

            response = await self._execute_with_retry(_call_vision)
            return f"[DESCRIPCIÓN DE IMAGEN GENERADA POR IA]\n{response.text}" if response.text else "No se pudo generar descripción."
        except Exception as e:
             raise Exception(f"Error procesando imagen con Gemini: {str(e)}")
