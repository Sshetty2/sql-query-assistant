# Domain-Specific Guidance

This directory contains domain-specific configuration files that customize the SQL Query Assistant for your particular database and use case. **These files are not committed to version control** (they are gitignored) to keep your domain-specific information private and separate from the core codebase.

## Overview

To use the SQL Query Assistant with your database, you'll need to provide domain-specific configuration files that help the LLM understand your schema, terminology, and query patterns. This directory contains:

1. **Example files** (`.example.json`) - Templates showing the required structure
2. **Your actual configuration files** (gitignored) - Your domain-specific data

The `combine_json_schema.py` utility automatically looks for these files when enriching the database schema for LLM processing.

## Required Configuration Files

### 1. `domain-specific-guidance-instructions.json`

This file provides semantic guidance to help the LLM understand domain-specific terminology and query patterns.

**Purpose:**
- Maps common terms in your domain to actual database tables
- Defines default behaviors for ambiguous queries
- Provides context about important fields and their meanings

**Example:**
```json
{
  "domain": "Cyber Security",
  "terminology_mappings": {
    "vulnerabilities": {
      "refers_to": "CVEs (Common Vulnerabilities and Exposures)",
      "primary_table": "tb_CVE",
      "description": "When users ask for 'vulnerabilities', they are referring to CVE records",
      "related_tables": ["tb_CVEAffectedProduct", "tb_CVEMetric"]
    }
  },
  "common_queries": {
    "vulnerability_by_severity": "Filter on CVE severity/CVSS score fields"
  },
  "important_fields": {
    "CVSS_Score": "Common Vulnerability Scoring System score (0-10 scale)"
  },
  "default_behaviors": {
    "severity_threshold": "Prioritize Critical and High severity by default"
  }
}
```

**Template:** See `domain-specific-guidance-instructions.example.json`

### 2. `domain-specific-table-metadata.json`

This file provides rich metadata about your database tables to improve query generation accuracy. You'll typically generate this from your database schema or documentation.

**Purpose:**
- Describes what each table stores and its purpose
- Documents primary keys and important columns
- Provides row count estimates and query patterns
- Indicates data sensitivity and update frequency

**Example:**
```json
[
  {
    "table_name": "tb_Users",
    "description": "Stores user account information and access credentials",
    "primary_key": "ID",
    "primary_key_description": "Uniquely identifies each user",
    "row_count_estimate": 1000,
    "key_columns": "Email\nUserID\nCompanyID",
    "data_sensitivity": "Contains PII",
    "update_frequency": "Real-time"
  }
]
```

**Template:** See `domain-specific-table-metadata.example.json`

### 3. `domain-specific-foreign-keys.json`

This file explicitly defines foreign key relationships to enable accurate JOIN generation. This is especially important if your database doesn't have explicit foreign key constraints defined.

**Purpose:**
- Maps foreign key columns to their referenced tables
- Enables the query generator to create correct multi-table queries
- Supplements database schema information

**Example:**
```json
[
  {
    "table_name": "tb_Orders",
    "foreign_keys": [
      {
        "foreign_key": "CustomerID",
        "primary_key_table": "tb_Customers"
      },
      {
        "foreign_key": "ProductID",
        "primary_key_table": "tb_Products"
      }
    ]
  }
]
```

**Template:** See `domain-specific-foreign-keys.example.json`

### 4. `domain-specific-sample-queries.json` (Optional)

This file contains example queries for your domain that can be used for testing and validation.

**Example:**
```json
[
  {
    "question": "Show me all active users",
    "sql": "SELECT * FROM users WHERE status = 'active'",
    "description": "Basic user filtering query"
  }
]
```

**Template:** See `domain-specific-sample-queries.example.json`

## Setup Instructions

### First-Time Setup

1. **Navigate to the domain_specific_guidance directory:**
   ```bash
   cd domain_specific_guidance
   ```

2. **Copy the example files and rename them:**
   ```bash
   cp domain-specific-guidance-instructions.example.json domain-specific-guidance-instructions.json
   cp domain-specific-table-metadata.example.json domain-specific-table-metadata.json
   cp domain-specific-foreign-keys.example.json domain-specific-foreign-keys.json
   cp domain-specific-sample-queries.example.json domain-specific-sample-queries.json
   ```

3. **Customize each file for your database:**
   - **domain-specific-guidance-instructions.json**: Add your domain terminology and query patterns
   - **domain-specific-table-metadata.json**: Document your tables with descriptions and metadata
   - **domain-specific-foreign-keys.json**: Define all foreign key relationships
   - **domain-specific-sample-queries.json**: Add example queries for testing (optional)

4. **Verify the files are gitignored:**
   ```bash
   git status
   # Your domain-specific-*.json files should NOT appear in the status
   # Only the .example.json files should be tracked
   ```

### Generating Configuration from Your Database

Most users will have their database schema documented in spreadsheets or data dictionaries. You'll need to:

1. **Extract table metadata** from your database documentation or schema
2. **Convert it to JSON** format matching the structure in the example files
3. **Document foreign key relationships** if they're not explicitly defined in your database

**Tip:** You may find it easier to use a script or tool to generate these JSON files from your existing documentation rather than creating them manually.

### Updating Configuration

When your database schema changes:

1. Update `domain-specific-table-metadata.json` with new/changed tables
2. Update `domain-specific-foreign-keys.json` with new relationships
3. Update `domain-specific-guidance-instructions.json` if new terminology or patterns emerge
4. Restart the application to load the new configuration

## How These Files Are Used

### Schema Enrichment (`combine_json_schema.py`)

The `combine_schema()` function automatically looks for domain-specific files and merges them with your database schema:

```python
from domain_specific_guidance.combine_json_schema import combine_schema

# Automatically looks for domain-specific-table-metadata.json and
# domain-specific-foreign-keys.json in the domain_specific_guidance directory
enriched_schema = combine_schema(json_schema)
```

**How it works:**
1. Fetches the raw database schema (table and column names, data types)
2. Looks for `domain-specific-table-metadata.json` in the `domain_specific_guidance/` directory
3. Looks for `domain-specific-foreign-keys.json` in the `domain_specific_guidance/` directory
4. If found, enriches tables with descriptions, metadata, and relationship information
5. If neither file exists, returns the original schema unchanged
6. The enriched schema is passed to the LLM for query generation

This enriched schema provides context that dramatically improves query generation accuracy.

### Domain Guidance (`planner.py`)

The planner loads `domain-specific-guidance-instructions.json` and includes it in the LLM prompt to help interpret user questions in domain-specific ways.

## File Location in Codebase

These files should be located at:
```
sql-query-assistant/
└── domain_specific_guidance/
    ├── __init__.py
    ├── README.md (this file)
    ├── combine_json_schema.py (utility for schema enrichment)
    ├── domain-specific-guidance-instructions.json (gitignored - your config)
    ├── domain-specific-table-metadata.json (gitignored - your config)
    ├── domain-specific-foreign-keys.json (gitignored - your config)
    ├── domain-specific-sample-queries.json (gitignored - your config)
    ├── domain-specific-guidance-instructions.example.json (committed - template)
    ├── domain-specific-table-metadata.example.json (committed - template)
    ├── domain-specific-foreign-keys.example.json (committed - template)
    └── domain-specific-sample-queries.example.json (committed - template)
```

## Testing Your Configuration

After setting up your configuration files:

1. Run the Streamlit app: `streamlit run streamlit_app.py`
2. Ask domain-specific questions to verify terminology mappings work
3. Check `debug/combined_schema_with_metadata.json` to verify metadata is loaded
4. Test queries that require JOINs to verify foreign key relationships are recognized

## Troubleshooting

**Files not being loaded:**
- Check file names match exactly (case-sensitive)
- Verify JSON syntax is valid (use a JSON validator)
- Check logs for file loading errors

**Foreign keys not recognized:**
- Ensure `foreign_key` field exactly matches column name in your database
- Verify `primary_key_table` references actual table names

**Domain guidance not applied:**
- Restart the application after making changes
- Check that terminology in the JSON matches how users actually phrase questions
- Review generated queries in debug output to see if guidance is being applied
