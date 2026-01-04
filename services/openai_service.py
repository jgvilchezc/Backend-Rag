from .llm_provider import LLMProvider
from openai import OpenAI
from typing import List, Dict
import base64

class OpenAIService(LLMProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API Key is required")
        self.client = OpenAI(api_key=api_key)
        self.generation_model = "gpt-4o"
        self.embedding_model = "text-embedding-3-small"

    async def generate_response(self, prompt: str, context: str, history: List[Dict[str, str]] = []) -> str:
        full_system_prompt = f"""
        Eres un asistente inteligente. Usa la siguiente información de contexto para responder a la pregunta del usuario.
        Si la respuesta no está en el contexto, di que no tienes esa información.
        
        Contexto:
        {context}
        """

        messages = [{"role": "system", "content": full_system_prompt}]
        
        # Add history if needed (not yet strictly implemented in the interface call but ready)
        for msg in history:
            messages.append(msg)

        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.generation_model,
                messages=messages,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
             raise Exception(f"OpenAI Error: {str(e)}")

    async def get_embedding(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        # Task type is a Gemini concept, ignored for OpenAI
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"OpenAI Embedding Error: {str(e)}")

    async def describe_image(self, image_bytes: bytes) -> str:
        try:
            # Encode image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.chat.completions.create(
                model=self.generation_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe esta imagen con mucho detalle para que pueda ser indexada en una base de conocimientos. Incluye todo el texto visible y detalles visuales importantes."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            return f"[DESCRIPCIÓN DE IMAGEN GENERADA POR IA (OpenAI)]\n{response.choices[0].message.content}"
        except Exception as e:
            raise Exception(f"OpenAI Vision Error: {str(e)}")
