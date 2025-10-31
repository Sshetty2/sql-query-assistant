"""
LLM Model Configurations for Benchmarking

This module defines the 8 models to be tested:
- 4 remote models (OpenAI): gpt-5, gpt-5-mini, gpt-4o, gpt-4o-mini
- 4 local models (Ollama): llama3.1:8b, llama3:8b, qwen3:8b, qwen3:4b

All models use minimal planner complexity for fair comparison.
"""

# Model configurations for benchmarking
# All models use PLANNER_COMPLEXITY=minimal for fair comparison
MODELS = {
    # Remote models (OpenAI) - all using minimal complexity
    "gpt-5": {
        "USE_LOCAL_LLM": "false",
        "AI_MODEL": "gpt-5",
        "AI_MODEL_REFINE": "gpt-5",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "category": "remote",
        "description": "Latest GPT-5 model from OpenAI"
    },
    "gpt-5-mini": {
        "USE_LOCAL_LLM": "false",
        "AI_MODEL": "gpt-5-mini",
        "AI_MODEL_REFINE": "gpt-5-mini",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "category": "remote",
        "description": "Faster GPT-5 variant with larger context window"
    },
    "gpt-4o": {
        "USE_LOCAL_LLM": "false",
        "AI_MODEL": "gpt-4o",
        "AI_MODEL_REFINE": "gpt-4o",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "category": "remote",
        "description": "GPT-4 optimized model"
    },
    "gpt-4o-mini": {
        "USE_LOCAL_LLM": "false",
        "AI_MODEL": "gpt-4o-mini",
        "AI_MODEL_REFINE": "gpt-4o-mini",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "category": "remote",
        "description": "Smaller, faster GPT-4o variant"
    },

    # Local models (Ollama) - all using minimal complexity
    "llama3.1-8b": {
        "USE_LOCAL_LLM": "true",
        "AI_MODEL": "llama3.1:8b",
        "AI_MODEL_REFINE": "llama3.1:8b",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "category": "local",
        "description": "Meta's Llama 3.1 8B parameter model"
    },
    "llama3-8b": {
        "USE_LOCAL_LLM": "true",
        "AI_MODEL": "llama3:8b",
        "AI_MODEL_REFINE": "llama3:8b",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "category": "local",
        "description": "Meta's Llama 3 8B parameter model"
    },
    "qwen3-8b": {
        "USE_LOCAL_LLM": "true",
        "AI_MODEL": "qwen3:8b",
        "AI_MODEL_REFINE": "qwen3:8b",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "category": "local",
        "description": "Alibaba's Qwen 3 8B parameter model"
    },
    "qwen3-4b": {
        "USE_LOCAL_LLM": "true",
        "AI_MODEL": "qwen3:4b",
        "AI_MODEL_REFINE": "qwen3:4b",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "category": "local",
        "description": "Alibaba's Qwen 3 4B parameter model (smallest)"
    }
}

# Common environment variables that remain constant across all models
COMMON_CONFIG = {
    "USE_TEST_DB": "false",  # Use SQL Server for benchmarking
    "RETRY_COUNT": "2",
    "REFINE_COUNT": "1",
    "TOP_MOST_RELEVANT_TABLES": "6",
    "INFER_FOREIGN_KEYS": "false",
    "ENABLE_DEBUG_FILES": "true"
}

# Execution order: Remote models first (faster), then local models (slower)
EXECUTION_ORDER = [
    "gpt-5",
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "llama3.1-8b",
    "llama3-8b",
    "qwen3-8b",
    "qwen3-4b"
]


def get_model_config(model_name):
    """Get the full configuration for a specific model."""
    if model_name not in MODELS:
        raise ValueError(f"Unknown model: {model_name}")

    config = {**COMMON_CONFIG, **MODELS[model_name]}
    return config


def get_remote_models():
    """Get list of remote model names."""
    return [name for name, config in MODELS.items() if config["category"] == "remote"]


def get_local_models():
    """Get list of local model names."""
    return [name for name, config in MODELS.items() if config["category"] == "local"]
