"""LLM factory for creating OpenAI or Ollama chat instances based on configuration."""

import os
from dotenv import load_dotenv

load_dotenv()


def is_using_ollama():
    """Check if the system is configured to use Ollama."""
    return os.getenv("USE_LOCAL_LLM", "false").lower() == "true"


def get_chat_llm(model_name: str = None, temperature: float = 0.3):
    """
    Returns ChatOpenAI or ChatOllama based on USE_LOCAL_LLM environment variable.

    This factory function allows seamless switching between OpenAI and Ollama
    LLM providers without changing any calling code.

    Args:
        model_name: Model to use (e.g., "gpt-4o-mini" or "qwen3:8b").
                   If None, defaults to AI_MODEL from environment.
        temperature: Temperature for generation (0.0 = deterministic, 1.0 = creative).
                    Default is 0.3.

    Returns:
        LLM instance (ChatOpenAI or ChatOllama) with identical API.

    Environment Variables:
        USE_LOCAL_LLM: Set to "true" to use Ollama, "false" for OpenAI (default: false)
        OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
        OPENAI_API_KEY: Required when using OpenAI
        AI_MODEL: Default model name if model_name not provided

    Example:
        >>> llm = get_chat_llm(model_name="gpt-4o-mini", temperature=0.3)
        >>> response = llm.invoke("What is 2+2?")
        >>> print(response.content)

        >>> # With structured output
        >>> structured_llm = get_structured_llm(MyPydanticModel, temperature=0.3)
        >>> result = structured_llm.invoke(prompt)
    """
    use_local = is_using_ollama()

    # Default to AI_MODEL from env if not provided
    if model_name is None:
        model_name = os.getenv("AI_MODEL")

    if use_local:
        # Use Ollama (local LLM)
        from langchain_ollama import ChatOllama

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
        )
    else:
        # Use OpenAI (cloud API)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
        )


def get_structured_llm(schema, model_name: str = None, temperature: float = 0.3):
    """
    Returns an LLM configured for structured output with the correct method for the provider.

    This is a convenience wrapper around get_chat_llm() that automatically configures
    structured output with the appropriate method based on the LLM provider:
    - Ollama requires method="json_schema"
    - OpenAI works without it

    Args:
        schema: Pydantic model class for structured output
        model_name: Model to use (e.g., "gpt-4o-mini" or "qwen3:8b").
                   If None, defaults to AI_MODEL from environment.
        temperature: Temperature for generation (0.0 = deterministic, 1.0 = creative).
                    Default is 0.3.

    Returns:
        LLM instance configured for structured output

    Example:
        >>> from pydantic import BaseModel
        >>> class Answer(BaseModel):
        ...     result: int
        ...     reasoning: str

        >>> structured_llm = get_structured_llm(Answer, temperature=0.3)
        >>> response = structured_llm.invoke("What is 2+2?")
        >>> print(response.result)  # 4
    """
    llm = get_chat_llm(model_name=model_name, temperature=temperature)

    # Ollama requires method="json_schema" for structured output
    if is_using_ollama():
        return llm.with_structured_output(schema, method="json_schema")
    else:
        return llm.with_structured_output(schema)
