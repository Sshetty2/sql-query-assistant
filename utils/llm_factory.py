"""LLM factory for creating OpenAI or Ollama chat instances based on configuration."""

import os
import asyncio
from typing import Any
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger()


# Model registry mapping aliases to (provider, actual_model_name)
# Allows mixing models from different providers when REMOTE_LLM_PROVIDER=auto
MODEL_REGISTRY = {
    # Anthropic models
    "claude-sonnet-4-5": ("anthropic", "claude-sonnet-4-5-20250929"),
    "claude-haiku-4-5": ("anthropic", "claude-haiku-4-5-20251001"),
    "claude-opus-4-1": ("anthropic", "claude-opus-4-1-20250805"),
    # OpenAI models
    "gpt-5": ("openai", "gpt-5"),
    "gpt-5-mini": ("openai", "gpt-5-mini"),
    "gpt-5-nano": ("openai", "gpt-5-nano"),
    "gpt-4o": ("openai", "gpt-4o"),
    "gpt-4o-mini": ("openai", "gpt-4o-mini"),
    "o3": ("openai", "o3"),
    "o3-mini": ("openai", "o3-mini"),
    "o1-mini": ("openai", "o1-mini"),
}


def is_using_ollama():
    """Check if the system is configured to use Ollama."""
    return os.getenv("USE_LOCAL_LLM", "false").lower() == "true"


def get_provider_for_model(model_name: str) -> tuple[str, str]:
    """
    Determine provider and actual model name from model alias or name.

    Used when REMOTE_LLM_PROVIDER=auto to automatically route models
    to the correct provider based on the model name.

    Args:
        model_name: Model alias (e.g., "claude-sonnet-4-5") or full name

    Returns:
        (provider, actual_model_name) tuple
        - provider: "openai" or "anthropic"
        - actual_model_name: The full model identifier for the API

    Examples:
        >>> get_provider_for_model("claude-sonnet-4-5")
        ("anthropic", "claude-3-5-sonnet-20241022")

        >>> get_provider_for_model("gpt-4o-mini")
        ("openai", "gpt-4o-mini")

        >>> get_provider_for_model("claude-3-5-sonnet-20241022")
        ("anthropic", "claude-3-5-sonnet-20241022")
    """
    # Check if model is in registry (alias mapping)
    if model_name in MODEL_REGISTRY:
        provider, actual_model_name = MODEL_REGISTRY[model_name]
        logger.debug(
            f"Model alias '{model_name}' resolved to {provider}/{actual_model_name}"
        )
        return (provider, actual_model_name)

    # If not in registry, infer provider from model name prefix
    if model_name.startswith("claude"):
        logger.debug(f"Inferred Anthropic provider for model '{model_name}'")
        return ("anthropic", model_name)
    elif (
        model_name.startswith("gpt")
        or model_name.startswith("o1")
        or model_name.startswith("o3")
    ):
        logger.debug(f"Inferred OpenAI provider for model '{model_name}'")
        return ("openai", model_name)

    # Default to openai if unable to determine
    logger.warning(
        f"Unknown model '{model_name}', defaulting to OpenAI provider. "
        f"Add to MODEL_REGISTRY for explicit mapping."
    )
    return ("openai", model_name)


def get_remote_provider():
    """
    Get the remote LLM provider (when USE_LOCAL_LLM=false).

    Returns:
        "openai", "anthropic", or "auto" (defaults to "openai" if not set)

    Environment Variables:
        REMOTE_LLM_PROVIDER: "openai", "anthropic", or "auto" (default: "openai")
        - "openai": Use OpenAI for all models
        - "anthropic": Use Anthropic for all models
        - "auto": Automatically determine provider based on model name
    """
    provider = os.getenv("REMOTE_LLM_PROVIDER", "openai").lower()
    if provider not in ["openai", "anthropic", "auto"]:
        logger.warning(
            f"Invalid REMOTE_LLM_PROVIDER='{provider}', defaulting to 'openai'. "
            f"Valid options: openai, anthropic, auto"
        )
        return "openai"
    return provider


def get_model_for_stage(stage: str) -> str:
    """
    Get the appropriate model for a specific workflow stage.

    Supports separate models for local and remote providers (provider-agnostic naming).
    Falls back to AI_MODEL if stage-specific model not configured.

    Args:
        stage: Workflow stage name:
            - "strategy" - Pre-planner (strategic analysis, text-based planning)
            - "planning" - Planner (converts strategy to structured JSON)
            - "filtering" - Schema filtering (if using LLM)
            - "error_correction" - SQL error correction
            - "refinement" - Query refinement when results are empty

    Returns:
        Model name to use for this stage

    Environment Variables:
        For Local LLMs (when USE_LOCAL_LLM=true):
            - LOCAL_MODEL_STRATEGY - Strategy generation (default: AI_MODEL)
            - LOCAL_MODEL_PLANNING - Planning stage (default: AI_MODEL)
            - LOCAL_MODEL_FILTERING - Schema filtering (default: AI_MODEL)
            - LOCAL_MODEL_ERROR_CORRECTION - Error correction (default: AI_MODEL)
            - LOCAL_MODEL_REFINEMENT - Refinement stage (default: AI_MODEL_REFINE or AI_MODEL)

        For Remote LLMs (when USE_LOCAL_LLM=false):
            - REMOTE_MODEL_STRATEGY - Strategy generation (default: AI_MODEL)
            - REMOTE_MODEL_PLANNING - Planning stage (default: AI_MODEL)
            - REMOTE_MODEL_FILTERING - Schema filtering (default: AI_MODEL)
            - REMOTE_MODEL_ERROR_CORRECTION - Error correction (default: AI_MODEL)
            - REMOTE_MODEL_REFINEMENT - Refinement stage (default: AI_MODEL_REFINE or AI_MODEL)

        Fallbacks (used if stage-specific not set):
            - AI_MODEL - Primary model (used for all stages by default)
            - AI_MODEL_REFINE - Refinement model (legacy, used for refinement if stage-specific not set)

    Example:
        >>> # Remote setup (USE_LOCAL_LLM=false)
        >>> # REMOTE_MODEL_STRATEGY=gpt-4o
        >>> # REMOTE_MODEL_PLANNING=gpt-4o-mini
        >>> # REMOTE_MODEL_REFINEMENT=gpt-4o-mini
        >>> # AI_MODEL=gpt-4o-mini  (fallback)
        >>> get_model_for_stage("strategy")    # Returns "gpt-4o"
        >>> get_model_for_stage("planning")    # Returns "gpt-4o-mini"
        >>> get_model_for_stage("error_correction")  # Returns "gpt-4o-mini" (fallback to AI_MODEL)

        >>> # Local setup (USE_LOCAL_LLM=true)
        >>> # LOCAL_MODEL_STRATEGY=qwen3:14b
        >>> # LOCAL_MODEL_PLANNING=qwen3:8b
        >>> # LOCAL_MODEL_ERROR_CORRECTION=qwen3:8b
        >>> # AI_MODEL=qwen3:8b  (fallback)
        >>> get_model_for_stage("strategy")    # Returns "qwen3:14b"
        >>> get_model_for_stage("planning")    # Returns "qwen3:8b"
    """
    use_local = is_using_ollama()

    # Define stage-specific env var names based on provider type (local vs remote)
    if use_local:
        env_var_map = {
            "strategy": "LOCAL_MODEL_STRATEGY",
            "planning": "LOCAL_MODEL_PLANNING",
            "filtering": "LOCAL_MODEL_FILTERING",
            "error_correction": "LOCAL_MODEL_ERROR_CORRECTION",
            "refinement": "LOCAL_MODEL_REFINEMENT",
        }
    else:
        env_var_map = {
            "strategy": "REMOTE_MODEL_STRATEGY",
            "planning": "REMOTE_MODEL_PLANNING",
            "filtering": "REMOTE_MODEL_FILTERING",
            "error_correction": "REMOTE_MODEL_ERROR_CORRECTION",
            "refinement": "REMOTE_MODEL_REFINEMENT",
        }

    # Get stage-specific model
    stage_env_var = env_var_map.get(stage)
    if stage_env_var:
        model = os.getenv(stage_env_var)
        if model:
            logger.debug(
                f"Using stage-specific model for {stage}: {model} (from {stage_env_var})"
            )
            return model

    # Final fallback to AI_MODEL
    fallback_model = os.getenv("AI_MODEL")
    logger.debug(f"Using fallback model for {stage}: {fallback_model} (from AI_MODEL)")
    return fallback_model


def get_chat_llm(model_name: str = None, temperature: float = 0.3, timeout: int = None):
    """
    Returns ChatOpenAI, ChatAnthropic, or ChatOllama based on configuration.

    This factory function allows seamless switching between LLM providers
    without changing any calling code.

    Args:
        model_name: Model to use (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022", or "qwen3:8b").
                   If None, defaults to AI_MODEL from environment.
        temperature: Temperature for generation (0.0 = deterministic, 1.0 = creative).
                    Default is 0.3 for balanced determinism and variation.
        timeout: Request timeout in seconds. If None, no timeout is set.

    Returns:
        LLM instance (ChatOpenAI, ChatAnthropic, or ChatOllama) with identical API.

    Environment Variables:
        USE_LOCAL_LLM: Set to "true" to use Ollama, "false" for remote (default: false)
        REMOTE_LLM_PROVIDER: "openai", "anthropic", or "auto" (default: "openai", only used when USE_LOCAL_LLM=false)
            - "openai": Use OpenAI for all models
            - "anthropic": Use Anthropic for all models
            - "auto": Auto-detect provider from model name/alias
        OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
        OPENAI_API_KEY: Required when using OpenAI
        ANTHROPIC_API_KEY: Required when using Anthropic
        AI_MODEL: Default model name if model_name not provided

    Example:
        >>> # OpenAI
        >>> llm = get_chat_llm(model_name="gpt-4o-mini", temperature=0.3)
        >>> response = llm.invoke("What is 2+2?")

        >>> # Anthropic
        >>> llm = get_chat_llm(model_name="claude-3-5-sonnet-20241022", temperature=0.3)
        >>> response = llm.invoke("What is 2+2?")

        >>> # Ollama
        >>> llm = get_chat_llm(model_name="qwen3:8b", temperature=0.3)
        >>> response = llm.invoke("What is 2+2?")

        >>> # Auto mode with model aliases (REMOTE_LLM_PROVIDER=auto)
        >>> llm = get_chat_llm(model_name="claude-sonnet-4-5", temperature=0.3)
        >>> # Automatically uses Anthropic with claude-3-5-sonnet-20241022

        >>> llm = get_chat_llm(model_name="gpt-4o-mini", temperature=0.3)
        >>> # Automatically uses OpenAI with gpt-4o-mini
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
        # Use remote provider (OpenAI or Anthropic)
        provider = get_remote_provider()

        # Auto mode: determine provider from model name
        if provider == "auto":
            detected_provider, actual_model_name = get_provider_for_model(model_name)
            provider = detected_provider
            model_name = actual_model_name
            logger.info(f"Auto-detected provider '{provider}' for model '{model_name}'")

        if provider == "anthropic":
            # Use Anthropic Claude
            from langchain_anthropic import ChatAnthropic

            kwargs = {
                "model": model_name,
                "temperature": temperature,
                "max_tokens": 8192,  # Anthropic requires max_tokens
            }

            if timeout is not None:
                kwargs["timeout"] = timeout

            return ChatAnthropic(**kwargs)
        else:
            # Use OpenAI (default)
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
    - OpenAI and Anthropic work without it

    Args:
        schema: Pydantic model class for structured output
        model_name: Model to use (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022", or "qwen3:8b").
                   If None, defaults to AI_MODEL from environment.
        temperature: Temperature for generation (0.0 = deterministic, 1.0 = creative).
                    Default is 0.3 for balanced determinism and variation.
        timeout: Request timeout in seconds. If None, no timeout is set.

    Returns:
        LLM instance configured for structured output

    Example:
        >>> from pydantic import BaseModel
        >>> class Answer(BaseModel):
        ...     result: int
        ...     reasoning: str

        >>> # OpenAI
        >>> structured_llm = get_structured_llm(Answer, model_name="gpt-4o-mini")
        >>> response = structured_llm.invoke("What is 2+2?")
        >>> print(response.result)  # 4

        >>> # Anthropic
        >>> structured_llm = get_structured_llm(Answer, model_name="claude-3-5-sonnet-20241022")
        >>> response = structured_llm.invoke("What is 2+2?")
        >>> print(response.result)  # 4
    """
    llm = get_chat_llm(model_name=model_name, temperature=temperature, timeout=timeout)

    # Ollama requires method="json_schema" for structured output
    # OpenAI and Anthropic work with default method
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
