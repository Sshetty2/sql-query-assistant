# Control-to-CVE Join Issue - Investigation Summary

**Date:** 2025-11-05
**Status:** UNRESOLVED - Deferred for future investigation

## Problem Statement

Queries attempting to relate security controls (`tb_Control`) to vulnerabilities (`tb_CVE`) are producing incorrect CVE counts. All controls show either exactly **4 CVEs** or exactly **1712 CVEs**, which does not match the expected distribution.

## Database Actual Totals

- **Total CVEs with CVSSScore >= 7.0:** 91,500 unique CVEs
- **Total CVEs (all scores):** 286,000 unique CVEs
- **Controls showing count of 4:** 641 controls
- **Controls showing count of 1712:** 201 controls

## The Join Path Discovered

After extensive debugging, we discovered the correct (but non-standard) join path:

```sql
FROM tb_Control
JOIN tb_ControlCDAMap ON tb_Control.CWPControlID = tb_ControlCDAMap.ControlID  -- Non-standard!
JOIN tb_CDA ON tb_ControlCDAMap.CDAID = tb_CDA.CWPCDAID  -- Non-standard!
JOIN tb_CVECDAConfigurationMap ON tb_CDA.CDAID = tb_CVECDAConfigurationMap.CDAID
JOIN tb_CVE ON tb_CVECDAConfigurationMap.CVEID = tb_CVE.CVEID
```

### Key Non-Standard Relationships

1. **tb_Control → tb_ControlCDAMap:**
   - WRONG: `tb_Control.ControlID = tb_ControlCDAMap.ControlID`
   - **CORRECT:** `tb_Control.CWPControlID = tb_ControlCDAMap.ControlID`

2. **tb_ControlCDAMap → tb_CDA:**
   - WRONG: `tb_ControlCDAMap.CDAID = tb_CDA.CDAID`
   - **CORRECT:** `tb_ControlCDAMap.CDAID = tb_CDA.CWPCDAID`

The "CWP" prefix appears to be an internal system identifier that creates non-intuitive join paths.

## Investigation Findings

### What We Confirmed

✅ **Join path is correct** - The non-standard CWP joins work and return data
✅ **CWPCDAID values are unique** - No duplicate CWPCDAID in tb_CDA
✅ **Control names are unique** - No duplicate control records
✅ **Some variation exists** - Diagnostic queries show controls should have varying CVE counts (e.g., 16, 7223)

### What's Causing the Issue

❌ **Duplicate CDAID/CVEID pairs in tb_CVECDAConfigurationMap** - This table contains duplicate mappings
❌ **Uniform CVE counts (4 or 1712)** - Despite using `COUNT(DISTINCT ...)`, all controls show only two possible values
❌ **Grouping by description doesn't affect results** - Removing Description from GROUP BY didn't change counts

### Attempted Fixes That Didn't Work

1. ❌ Grouping by `CWPControlID` instead of `ControlName`
2. ❌ Removing `Description` from GROUP BY
3. ❌ Using DISTINCT subquery on tb_CVECDAConfigurationMap:
   ```sql
   JOIN (SELECT DISTINCT CDAID, CVEID FROM tb_CVECDAConfigurationMap) AS ccm
   ```

## Diagnostic Queries Run

```sql
-- Confirmed varying CVE counts SHOULD exist
SELECT
  c.ControlName,
  COUNT(DISTINCT cda.CDAID) AS CDAsFromControl,
  COUNT(DISTINCT ccm.CVEID) AS CVEsFromThoseCDAs
FROM tb_Control c
JOIN tb_ControlCDAMap cm ON c.CWPControlID = cm.ControlID
JOIN tb_CDA cda ON cm.CDAID = cda.CWPCDAID
LEFT JOIN tb_CVECDAConfigurationMap ccm ON cda.CDAID = ccm.CDAID
GROUP BY c.ControlName
HAVING COUNT(DISTINCT ccm.CVEID) > 0;
-- Results: Some controls have 16 CVEs, others have 7223, etc.
```

```sql
-- Confirmed duplicates exist in CVE mapping table
SELECT
  CDAID,
  CVEID,
  COUNT(*) AS DuplicateCount
FROM tb_CVECDAConfigurationMap
GROUP BY CDAID, CVEID
HAVING COUNT(*) > 1;
-- Results: Multiple duplicate CDAID/CVEID combinations found
```

## Possible Root Causes (Hypotheses)

### Hypothesis 1: Data Quality Issue
The tb_CVECDAConfigurationMap table may have:
- Duplicate entries that shouldn't exist
- Historical data that needs cleanup
- Multiple "versions" of the same mapping (e.g., different assessment dates)

**Next Step:** Investigate table schema and understand business logic for duplicates

### Hypothesis 2: Missing Join Table
There may be an intermediate mapping table between controls and CDAs that we haven't discovered yet.

**Next Step:** Check for tables like:
- `tb_ControlCWPCDAMap`
- `tb_CWPControlCDAMap`
- Other tables with "CWP" prefix

### Hypothesis 3: Hierarchical CDA Relationship
The CWPCDAID might represent a parent-child hierarchy where:
- Controls apply at one level (e.g., portfolio)
- CVEs are tracked at another level (e.g., individual assets)
- The join needs to traverse multiple levels

**Next Step:** Analyze tb_CDA table structure and CWPCDAID relationships more deeply

### Hypothesis 4: Temporal Dimension
The CVECDAConfigurationMap duplicates might represent different time periods or assessment states.

**Next Step:** Check for timestamp/status columns in tb_CVECDAConfigurationMap

## Recommended Next Steps

### Immediate Actions (Data Analysis)

1. **Examine tb_CVECDAConfigurationMap schema:**
   ```sql
   EXEC sp_help 'tb_CVECDAConfigurationMap';
   ```
   Look for: Primary key, indexes, timestamp columns, status columns

2. **Analyze duplicate patterns:**
   ```sql
   SELECT TOP 100
     CDAID,
     CVEID,
     COUNT(*) AS DuplicateCount,
     -- Add all other columns to see what varies
     *
   FROM tb_CVECDAConfigurationMap
   GROUP BY CDAID, CVEID
   HAVING COUNT(*) > 1
   ORDER BY DuplicateCount DESC;
   ```

3. **Check for additional CWP-prefixed tables:**
   ```sql
   SELECT TABLE_NAME
   FROM INFORMATION_SCHEMA.TABLES
   WHERE TABLE_NAME LIKE '%CWP%'
     OR TABLE_NAME LIKE '%Control%';
   ```

### Medium-Term Actions (Business Logic)

4. **Consult with database/application owner** to understand:
   - What does "CWP" stand for?
   - Why are there duplicate CDAID/CVEID pairs?
   - Is there a "current" vs "historical" distinction?
   - Are controls meant to roll up to a portfolio level?

5. **Review application code** that writes to tb_CVECDAConfigurationMap to understand duplicate logic

### Long-Term Actions (Fix Implementation)

6. **Once root cause is understood, implement proper query:**
   - Add appropriate filters (e.g., WHERE IsActive = 1)
   - Add appropriate deduplication logic
   - Update domain guidance with correct pattern

7. **Add to domain-specific-foreign-keys.json:**
   ```json
   {
     "table_name": "tb_ControlCDAMap",
     "foreign_keys": [
       {
         "foreign_key": "ControlID",
         "primary_key_table": "tb_Control",
         "to_column": "CWPControlID",
         "notes": "Non-standard: Maps to CWPControlID, not ControlID"
       }
     ]
   }
   ```

## Workaround for Users

**For now, advise users that control-to-CVE queries are not reliable.**

Alternative approaches:
1. Query controls separately from CVEs
2. Use CDA-level queries (controls → CDAs, CVEs → CDAs separately)
3. Wait for data team to clarify the correct join logic

## Files Modified During Investigation

- ✅ Added reverse FK expansion to `agent/filter_schema.py` (lines 296-353)
- ✅ Fixed type inference bug in `agent/generate_query.py` (lines 616-623)
- ⚠️ Temporarily added control guidance to `domain_specific_guidance/domain-specific-guidance-instructions.md` (TO BE REMOVED)

## Related Issues Fixed During Investigation

1. **Reverse FK Expansion** - Junction tables now included when parent entities are selected
2. **Type Mismatch Bug** - Numeric-looking strings (e.g., "2012") no longer incorrectly treated as numbers
3. **ORDER BY + GROUP BY Guidance** - Added comprehensive guidance to prevent aggregate column errors

---

**Conclusion:** The control-to-CVE relationship requires deeper understanding of the business logic and data model before reliable queries can be generated. The technical join path is known, but data quality or missing business rules prevent accurate results.
