"""LLM factory for creating OpenAI or Ollama chat instances based on configuration."""

import os
import asyncio
from typing import Any
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()


def is_using_ollama():
    """Check if the system is configured to use Ollama."""
    return os.getenv("USE_LOCAL_LLM", "false").lower() == "true"


def get_chat_llm(model_name: str = None, temperature: float = 0.3, timeout: int = None):
    """
    Returns ChatOpenAI or ChatOllama based on USE_LOCAL_LLM environment variable.

    This factory function allows seamless switching between OpenAI and Ollama
    LLM providers without changing any calling code.

    Args:
        model_name: Model to use (e.g., "gpt-4o-mini" or "qwen3:8b").
                   If None, defaults to AI_MODEL from environment.
        temperature: Temperature for generation (0.0 = deterministic, 1.0 = creative).
                    Default is 0.3.
        timeout: Request timeout in seconds. If None, no timeout is set.

    Returns:
        LLM instance (ChatOpenAI or ChatOllama) with identical API.

    Environment Variables:
        USE_LOCAL_LLM: Set to "true" to use Ollama, "false" for OpenAI (default: false)
        OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
        OPENAI_API_KEY: Required when using OpenAI
        AI_MODEL: Default model name if model_name not provided

    Example:
        >>> llm = get_chat_llm(model_name="gpt-4o-mini", temperature=0.3, timeout=60)
        >>> response = llm.invoke("What is 2+2?")
        >>> print(response.content)

        >>> # With structured output
        >>> structured_llm = get_structured_llm(MyPydanticModel, temperature=0.3, timeout=60)
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

        kwargs = {
            "model": model_name,
            "temperature": temperature,
            "base_url": base_url,
        }

        if timeout is not None:
            kwargs["timeout"] = timeout

        return ChatOllama(**kwargs)
    else:
        # Use OpenAI (cloud API)
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }

        if timeout is not None:
            kwargs["request_timeout"] = timeout

        return ChatOpenAI(**kwargs)


def get_structured_llm(
    schema, model_name: str = None, temperature: float = 0.3, timeout: int = 120
):
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
        timeout: Request timeout in seconds. If None, no timeout is set.

    Returns:
        LLM instance configured for structured output

    Example:
        >>> from pydantic import BaseModel
        >>> class Answer(BaseModel):
        ...     result: int
        ...     reasoning: str

        >>> structured_llm = get_structured_llm(Answer, temperature=0.3, timeout=60)
        >>> response = structured_llm.invoke("What is 2+2?")
        >>> print(response.result)  # 4
    """
    llm = get_chat_llm(model_name=model_name, temperature=temperature, timeout=timeout)

    # Ollama requires method="json_schema" for structured output
    if is_using_ollama():
        return llm.with_structured_output(schema, method="json_schema")
    else:
        return llm.with_structured_output(schema)


def invoke_with_timeout(
    llm: Any, prompt: str, timeout: int = 75, max_retries: int = 2
) -> Any:
    """
    Invoke LLM with timeout protection, specifically for local LLMs.

    For Ollama (local), wraps the call with asyncio.wait_for() to enforce hard timeout.
    For OpenAI (remote), uses normal invoke (their timeout handling works).

    Args:
        llm: The LLM instance (from get_chat_llm or get_structured_llm)
        prompt: The prompt to send to the LLM
        timeout: Timeout in seconds (default: 75s)
        max_retries: Maximum retry attempts on timeout (default: 2)

    Returns:
        LLM response object

    Raises:
        TimeoutError: If all retry attempts timeout
        Exception: Any other LLM errors

    Example:
        >>> llm = get_chat_llm()
        >>> result = invoke_with_timeout(llm, "What is 2+2?", timeout=60)
        >>> print(result.content)
    """
    use_ollama = is_using_ollama()

    # For OpenAI, just use normal invoke (timeout parameter works)
    if not use_ollama:
        return llm.invoke(prompt)

    # For Ollama, wrap with async timeout
    async def async_invoke_with_timeout():
        """Async wrapper to enable timeout for Ollama."""
        try:
            result = await asyncio.wait_for(llm.ainvoke(prompt), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM call exceeded {timeout}s timeout")

    # Retry logic
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            # Run async function in sync context
            return asyncio.run(async_invoke_with_timeout())

        except TimeoutError as e:
            last_exception = e
            if attempt < max_retries:
                # Log retry attempt (optional - could use logger here)
                print(
                    f"[WARNING] LLM timeout on attempt {attempt}/{max_retries}, retrying..."
                )
                continue
            else:
                # Max retries reached
                raise TimeoutError(
                    f"LLM call timed out after {max_retries} attempts (timeout={timeout}s each)"
                ) from e

        except Exception as e:
            # Non-timeout errors - don't retry, just raise
            logger.error(f"Error in invoke_with_timeout: {str(e)}", exc_info=True)
            raise

    # Should never reach here, but just in case
    raise last_exception or Exception("Unexpected error in invoke_with_timeout")
