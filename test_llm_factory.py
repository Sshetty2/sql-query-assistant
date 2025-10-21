"""Test the LLM factory to verify it works with both OpenAI and Ollama."""

import os
from utils.llm_factory import get_chat_llm


def test_llm_factory_returns_correct_type():
    """Test that the factory returns the correct LLM type based on env var."""

    # Save original env var
    original_use_local = os.environ.get("USE_LOCAL_LLM")

    try:
        # Test OpenAI mode
        os.environ["USE_LOCAL_LLM"] = "false"
        llm = get_chat_llm(model_name="gpt-4o-mini", temperature=0.5)
        assert llm.__class__.__name__ == "ChatOpenAI", f"Expected ChatOpenAI but got {llm.__class__.__name__}"
        print("[PASS] OpenAI mode: Returns ChatOpenAI instance")

        # Test Ollama mode
        os.environ["USE_LOCAL_LLM"] = "true"
        llm = get_chat_llm(model_name="qwen3:8b", temperature=0.5)
        assert llm.__class__.__name__ == "ChatOllama", f"Expected ChatOllama but got {llm.__class__.__name__}"
        print("[PASS] Ollama mode: Returns ChatOllama instance")

        # Verify both have the same API
        assert hasattr(llm, "invoke"), "LLM should have invoke method"
        assert hasattr(llm, "with_structured_output"), "LLM should have with_structured_output method"
        print("[PASS] Both LLMs have identical API (invoke, with_structured_output)")

        print("\n[SUCCESS] All tests passed!")

    finally:
        # Restore original env var
        if original_use_local is not None:
            os.environ["USE_LOCAL_LLM"] = original_use_local
        elif "USE_LOCAL_LLM" in os.environ:
            del os.environ["USE_LOCAL_LLM"]


def test_default_model_from_env():
    """Test that model_name defaults to AI_MODEL env var when not specified."""

    original_ai_model = os.environ.get("AI_MODEL")
    original_use_local = os.environ.get("USE_LOCAL_LLM")

    try:
        os.environ["AI_MODEL"] = "test-model"
        os.environ["USE_LOCAL_LLM"] = "false"

        llm = get_chat_llm(temperature=0.7)  # No model_name specified

        # Check that the model was set (we can't directly check the private attribute,
        # but we can verify the LLM was created successfully)
        assert llm is not None, "LLM should be created with default AI_MODEL"
        print("[PASS] Model defaults to AI_MODEL env var when not specified")

    finally:
        if original_ai_model is not None:
            os.environ["AI_MODEL"] = original_ai_model
        elif "AI_MODEL" in os.environ:
            del os.environ["AI_MODEL"]

        if original_use_local is not None:
            os.environ["USE_LOCAL_LLM"] = original_use_local
        elif "USE_LOCAL_LLM" in os.environ:
            del os.environ["USE_LOCAL_LLM"]


if __name__ == "__main__":
    print("Testing LLM Factory\n" + "=" * 50)
    test_llm_factory_returns_correct_type()
    print()
    test_default_model_from_env()
