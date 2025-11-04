"""
One-off script to convert FK mappings Excel to domain-specific-foreign-keys.json
"""

import pandas as pd
import json
from collections import defaultdict

# Read the Excel file
excel_file = "fk_mappings_CWPR_11-03-25.xlsx"
df = pd.read_excel(excel_file)

print(f"Reading {excel_file}...")
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print("\nFirst few rows:")
print(df.head())

# Group foreign keys by table
fk_by_table = defaultdict(list)

for _, row in df.iterrows():
    # Skip rows with missing data
    if (
        pd.isna(row["table_name"])
        or pd.isna(row["fk_column"])
        or pd.isna(row["chosen_table"])
    ):
        continue

    # Use the actual column names from the Excel
    table_name = str(row["table_name"]).strip()
    fk_column = str(row["fk_column"]).strip()
    ref_table = str(row["chosen_table"]).strip()

    fk_by_table[table_name].append(
        {"foreign_key": fk_column, "primary_key_table": ref_table}
    )

# Convert to the expected JSON format
output = []
for table_name, foreign_keys in sorted(fk_by_table.items()):
    output.append({"table_name": table_name, "foreign_keys": foreign_keys})

# Save to JSON
output_file = "domain_specific_guidance/domain-specific-foreign-keys.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[SUCCESS] Converted {len(output)} tables with foreign keys")
print(f"[OUTPUT] Saved to: {output_file}")

# Print summary
total_fks = sum(len(table["foreign_keys"]) for table in output)
print("\n[SUMMARY]")
print(f"   - Total tables: {len(output)}")
print(f"   - Total foreign keys: {total_fks}")

# Show first few entries
print("\n[PREVIEW] First 3 tables:")
for table in output[:3]:
    print(f"   {table['table_name']}: {len(table['foreign_keys'])} foreign keys")
