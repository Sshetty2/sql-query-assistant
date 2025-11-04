"""
One-off script to convert table metadata Excel to domain-specific-table-metadata.json
"""

import pandas as pd
import json

# Read the Excel file
excel_file = "CWPr db metadata Table Mapping.xlsx"
df = pd.read_excel(excel_file)

print(f"Reading {excel_file}...")
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print("\nFirst few rows:")
print(df.head())

# Convert to the expected JSON format
output = []

for _, row in df.iterrows():
    # Skip rows with missing table name
    # Note: Excel column has trailing space: 'Table Name '
    table_name_col = "Table Name " if "Table Name " in df.columns else "Table Name"

    if pd.isna(row[table_name_col]):
        continue

    # Use the actual column names from the Excel
    table_name = str(row[table_name_col]).strip()

    # Get description
    description = (
        str(row["Description"]).strip() if not pd.isna(row["Description"]) else ""
    )

    # Get primary key
    primary_key = ""
    if "Primary Key" in df.columns and not pd.isna(row["Primary Key"]):
        primary_key = str(row["Primary Key"]).strip()

    output.append(
        {
            "table_name": table_name,
            "description": description,
            "primary_key": primary_key,
        }
    )

# Save to JSON
output_file = "domain_specific_guidance/domain-specific-table-metadata.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[SUCCESS] Converted {len(output)} tables")
print(f"[OUTPUT] Saved to: {output_file}")

# Print summary
tables_with_descriptions = sum(1 for table in output if table["description"])
tables_with_primary_keys = sum(1 for table in output if table["primary_key"])

print("\n[SUMMARY]")
print(f"   - Total tables: {len(output)}")
print(f"   - Tables with descriptions: {tables_with_descriptions}")
print(f"   - Tables with primary keys: {tables_with_primary_keys}")

# Show first few entries
print("\n[PREVIEW] First 3 tables:")
for table in output[:3]:
    print(f"   {table['table_name']}")
    print(
        f"      Description: {table['description'][:60]}..."
        if len(table["description"]) > 60
        else f"      Description: {table['description']}"
    )
    if table["primary_key"]:
        print(f"      Primary Key: {table['primary_key']}")
