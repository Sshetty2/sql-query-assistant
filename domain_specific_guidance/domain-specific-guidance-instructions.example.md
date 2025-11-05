# Domain-Specific Guidance: [Your Domain Name]

Example: Healthcare, E-Commerce, Finance, Cyber Security

## Terminology Mappings

### [Term 1]
- **Primary Table**: `table_name`
- **Refers To**: What this term means in your domain
- **Related Tables**: `related_table1`, `related_table2`
- **User Terms**: alternate names, synonyms, common phrases

Description of when users use this term and how it relates to your database.

### [Term 2]
- **Primary Table**: `another_table`
- **Refers To**: Another domain-specific concept
- **Related Tables**: `junction_table`, `reference_table`
- **User Terms**: other ways users might refer to this

More context about this terminology.

---

## Important Fields Reference

### [Field Category 1]

| Field Name | Table | Description | Format/Values | User Terms |
|------------|-------|-------------|---------------|------------|
| `FieldName1` | `tb_Table1` | What this field represents | Valid values or format | how users refer to it |
| `FieldName2` | `tb_Table1` | Another important field | Numeric, Text, Date, etc. | alternative names |

**Example Queries**:
- "Show me records with [condition]" → `FieldName1 = 'value'`
- "Filter by [user term]" → `FieldName2 > threshold`

### [Field Category 2]

| Code | Full Name | Description | User Terms |
|------|-----------|-------------|------------|
| **A** | Active | Description of what A means | active, enabled, live |
| **I** | Inactive | Description of what I means | inactive, disabled, offline |

---

## Common Query Patterns

### Pattern 1: [Query Type Name]
When users ask "[example user question]":
- **Tables Needed**: `tb_Table1`, `tb_Table2`
- **Join**: `tb_Table1.ID = tb_Table2.ForeignKey`
- **Filter**: `FieldName = 'value'`
- **User Terms**: common phrases, alternative wordings

### Pattern 2: Aggregation Queries
When users ask "how many [items]" or "count [things]":
- **Aggregation**: `COUNT(UniqueID)`
- **Group By**: Dimension columns
- **Important**: Always group by display columns to avoid SQL errors

### Pattern 3: Time-Based Queries
When users mention "recent", "last month", or time-related terms:
- **Field**: `DateField`
- **Default Window**: Last 30/60/90 days if not specified
- **Format**: `DateField >= DATEADD(day, -90, GETDATE())`

---

## Important Database Concepts

### Junction Tables
`tb_JunctionTable` connects `tb_Table1` to `tb_Table2`:
- Always use for queries involving both entities
- Contains foreign keys: `Table1ID`, `Table2ID`

### Status Fields
Common status values in your domain:
- `A` = Active
- `I` = Inactive
- `P` = Pending
- `D` = Deleted

### Special Considerations
- Field X must always be filtered by Y
- Table Z requires joining through intermediate table W
- Date fields use specific timezone or format

---

## Default Behaviors

### Implicit Assumptions
- When users don't specify [parameter], assume [default value]
- "Recent" means last [N] days
- Include/exclude [certain records] by default

### Common Filters
- Exclude soft-deleted records: `IsDeleted = 0`
- Only show active items: `Status = 'A'`
- Default date range: Last 90 days

### Result Limits
- Limit large queries to 500 rows unless specified
- Warn if query would return > 10,000 rows

---

## Query Optimization Hints

### Frequently Combined Filters
Users often ask for combinations:
- "[Condition A] AND [Condition B]" → `Field1 = 'X' AND Field2 > Y`
- "[User term for complex condition]" → Multiple filters combined

### COUNT vs LIST Distinction
- "Show me [items]" → List individual rows with columns
- "How many [items]" → COUNT aggregation, no individual rows

### Performance Tips
- Index fields: `Field1`, `Field2`, `DateField`
- Avoid full table scans on `LargeTable`
- Use date range filters when possible

---

## Examples

### Example Query 1
**User Ask**: "[Natural language question]"
**Interpretation**: What the user actually wants
**Tables**: `tb_Table1`, `tb_Table2`
**Filters**: `Field1 = 'value'`
**Expected Output**: Description of results

### Example Query 2
**User Ask**: "[Another question]"
**Interpretation**: What this means in database terms
**Aggregation**: `COUNT(ID) GROUP BY Category`
**Sorting**: Order by count descending
**Expected Output**: Summary statistics
