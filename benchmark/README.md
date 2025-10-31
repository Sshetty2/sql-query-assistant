# LLM Benchmarking System

This directory contains a comprehensive benchmarking system for comparing different LLM models on SQL query generation tasks.

## Overview

The benchmark system tests 8 different LLM models (4 remote OpenAI models + 4 local Ollama models) across 5 semi-complex SQL queries, measuring:

- **Performance**: Execution time, token usage
- **Quality**: SQL correctness, structural similarity to ground truth
- **Cost**: Estimated API costs for remote models
- **Reliability**: Success rates, error handling

All models use **PLANNER_COMPLEXITY=minimal** for fair comparison.

## Directory Structure

```
benchmark/
├── README.md                    # This file
├── run_benchmark.py            # Main benchmark orchestrator
├── generate_reports.py         # Report generator
├── config/
│   ├── model_configs.py        # 8 model configurations
│   └── benchmark_settings.py   # Global settings
├── utilities/
│   ├── env_manager.py          # .env file management
│   ├── metrics_collector.py    # Metrics collection
│   ├── sql_comparator.py       # SQL comparison logic
│   └── ground_truth_generator.py # Ground truth SQL generator
├── queries/                     # 5 test queries
│   ├── query_1_complex_user_activity/
│   │   ├── query.json          # Query metadata
│   │   └── ground_truth.sql    # Optimal SQL (Claude-generated)
│   ├── query_2_vulnerability_tracking/
│   ├── query_3_hardware_aggregation/
│   ├── query_4_cross_domain_analysis/
│   └── query_5_application_risk/
└── results/                     # Timestamped results (generated)
    └── 2025-10-31_HH-MM-SS/
        ├── gpt-5/
        ├── gpt-5-mini/
        ├── gpt-4o/
        ├── gpt-4o-mini/
        ├── llama3.1-8b/
        ├── llama3-8b/
        ├── qwen3-8b/
        ├── qwen3-4b/
        ├── benchmark_summary.json
        └── reports/
            ├── benchmark_summary.md
            ├── model_comparison.md
            └── recommendations.md
```

## Models Tested

### Remote Models (OpenAI)
- **gpt-5**: Latest GPT-5 model
- **gpt-5-mini**: Faster GPT-5 variant with larger context window
- **gpt-4o**: GPT-4 optimized model
- **gpt-4o-mini**: Smaller, faster GPT-4o variant

### Local Models (Ollama)
- **llama3.1:8b**: Meta's Llama 3.1 8B
- **llama3:8b**: Meta's Llama 3 8B
- **qwen3:8b**: Alibaba's Qwen 3 8B
- **qwen3:4b**: Alibaba's Qwen 3 4B (smallest)

## Test Queries

1. **Complex User Activity Analysis** - Multi-table joins, time-based filtering, aggregation
2. **Vulnerability Tracking** - Complex joins, numeric filters (CVSS > 7.0), grouping
3. **Hardware Aggregation** - GROUP BY with HAVING, multiple aggregations
4. **Cross-Domain Asset Analysis** - 4+ table joins, temporal filters
5. **Application Risk Assessment** - Joins across vulnerabilities and applications, ranking

## Prerequisites

### For Remote Models
- Valid OpenAI API key in `.env`
- Sufficient API credits (~15k tokens total)

### For Local Models
- Ollama installed and running
- Models pulled: `ollama pull llama3.1:8b llama3:8b qwen3:8b qwen3:4b`
- Verify: `curl http://localhost:11434/api/tags`

### Database
- SQL Server accessible (USE_TEST_DB=false)
- Database credentials in `.env`

## Usage

### 1. Run Complete Benchmark

```bash
python -m benchmark.run_benchmark
```

This will:
1. Backup your current `.env` file
2. Run all 40 benchmarks (8 models × 5 queries)
3. Collect metrics and debug files
4. Compare SQL against ground truth
5. Restore original `.env`
6. Save results to timestamped directory

**Estimated time:** 2-3 hours

### 2. Generate Reports

After benchmark completes:

```bash
python -m benchmark.generate_reports benchmark/results/2025-10-31_HH-MM-SS
```

This generates:
- **benchmark_summary.md**: Overall performance table, key findings
- **model_comparison.md**: Side-by-side SQL comparisons
- **recommendations.md**: Best models for different use cases

### 3. View Results

Results are saved in `benchmark/results/TIMESTAMP/`:
- Each model/query combination has its own directory
- `metrics.json`: Performance and quality metrics
- `sql_comparison.json`: Detailed SQL comparison
- Debug files: Full workflow outputs (schema, planner output, etc.)

## Configuration

### Modify Models

Edit `benchmark/config/model_configs.py`:

```python
MODELS = {
    "your-model": {
        "USE_LOCAL_LLM": "true",
        "AI_MODEL": "your-model:tag",
        "PLANNER_COMPLEXITY": "minimal",
        "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "category": "local",
        "description": "Your custom model"
    }
}
```

### Modify Settings

Edit `benchmark/config/benchmark_settings.py`:

```python
DELAY_BETWEEN_RUNS = 5  # seconds
MAX_RETRIES_PER_RUN = 3
QUALITY_WEIGHTS = {
    "sql_executes": 30,
    "correct_tables": 20,
    "correct_joins": 20,
    "correct_filters": 15,
    "correct_aggregations": 10,
    "similar_results": 5
}
```

### Add Custom Queries

1. Create query directory: `benchmark/queries/query_N_description/`
2. Add `query.json` with metadata
3. Add `ground_truth.sql` with optimal SQL
4. Re-run benchmark

## Metrics Collected

### Performance
- Total execution time (end-to-end)
- Per-node execution time
- SQL generation time
- SQL execution time
- Retry/refinement counts

### Quality
- SQL correctness (executes without errors)
- Table selection accuracy
- Join accuracy
- Filter predicate accuracy
- Aggregation accuracy
- Result similarity (row count comparison)
- **Overall Quality Score** (0-100)

### Resource Usage
- Token usage (input/output)
- Total tokens per query
- Estimated API cost (remote models)

## Quality Scoring

The quality score (0-100) is calculated as:

- **SQL Executes** (30 points): Does the generated SQL run without errors?
- **Correct Tables** (20 points): Are the right tables selected?
- **Correct Joins** (20 points): Are the join relationships correct?
- **Correct Filters** (15 points): Are filter predicates accurate?
- **Correct Aggregations** (10 points): Are aggregations correct?
- **Similar Results** (5 points): Does row count match ground truth?

## Troubleshooting

### Remote Models Fail
- Check OpenAI API key: `echo $OPENAI_API_KEY`
- Verify API credits
- Check model names are valid

### Local Models Fail
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Pull missing models: `ollama pull model:tag`
- Check Ollama logs for errors

### Database Connection Issues
- Verify SQL Server is accessible
- Check credentials in `.env`
- Test connection manually

### Benchmark Hangs
- Check for prompts requiring user input
- Verify no interactive debuggers
- Review logs for stuck processes

## Advanced Usage

### Run Single Model/Query

Modify `run_benchmark.py` to filter:

```python
# Only test one model
EXECUTION_ORDER = ["gpt-4o-mini"]

# Only test one query
queries = [q for q in queries if q["query_id"] == "query_1_complex_user_activity"]
```

### Custom Ground Truth

Use the interactive generator:

```bash
python -m benchmark.utilities.ground_truth_generator interactive
```

This will:
1. Prompt for query details
2. Run workflow to get filtered schema
3. Display schema and workflow-generated SQL
4. Allow you to provide optimal SQL
5. Test and save to query directory

### Export Results

Results are in JSON format for easy processing:

```python
import json

with open("benchmark/results/TIMESTAMP/benchmark_summary.json") as f:
    summary = json.load(f)

# Analyze results programmatically
for result in summary["results"]:
    print(f"{result['model_name']}: {result['quality_score']}/100")
```

## Future Enhancements

- [ ] Support for standard/full planner complexity comparison
- [ ] Semantic SQL equivalence checking (beyond structural)
- [ ] Parallel benchmark execution
- [ ] Real-time progress dashboard
- [ ] Historical trend analysis
- [ ] Custom report templates

## References

- **Main Documentation**: `../README.md`
- **Workflow Diagram**: `../WORKFLOW_DIAGRAM.md`
- **Join Synthesizer**: `../JOIN_SYNTHESIZER.md`
- **CLAUDE.md**: `../CLAUDE.md`
