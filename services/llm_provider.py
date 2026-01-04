from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class LLMProvider(ABC):
    """
    Abstract Base Class for LLM Providers (Gemini, OpenAI, Anthropic, etc.)
    """

    @abstractmethod
    async def generate_response(self, prompt: str, context: str, history: List[Dict[str, str]] = []) -> str:
        """
        Generates a text response based on the prompt, context, and chat history.
        """
        pass

    @abstractmethod
    async def get_embedding(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        """
        Generates an embedding vector for the given text.
        """
        pass

    @abstractmethod
    async def describe_image(self, image_bytes: bytes) -> str:
        """
        Generates a text description for an image.
        """
        pass
