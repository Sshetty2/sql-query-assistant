# Model Comparison Report

## query_1_complex_user_activity

### gpt-4o

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-4o-mini

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5-mini

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### llama3-8b

**Quality Score:** 63/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 2 joins
- Generated: 1 joins

**Aggregations **


---

### llama3.1-8b

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-4b

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-8b

**Quality Score:** 63/100

**Generated SQL:**
```sql
SELECT
TOP 20
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
ORDER BY
  [tb_UserLoginInfo].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 2 joins
- Generated: 1 joins

**Aggregations **


---

## query_2_vulnerability_tracking

### gpt-4o

**Quality Score:** 48/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputerCVEMap]
JOIN [tb_Company]
  ON [tb_SaasComputerCVEMap].[CompanyID] = [tb_Company].[ID]
JOIN [tb_CVEConfigurationMap]
  ON [tb_SaasComputerCVEMap].[CVEConfigurationMapID] = [tb_CVEConfigurationMap].[CVEConfigurationMapID]
ORDER BY
  [tb_Company].[Name] ASC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_CVE, TB_SAASCOMPUTERS, TB_SAASPENDINGPATCH
- Extra: TB_CVECONFIGURATIONMAP

**Joins X**
- Ground truth: 4 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### gpt-4o-mini

**Quality Score:** 48/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerCVEMap]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerCVEMap].[ComputerID]
JOIN [tb_CVEConfigurationMap]
  ON [tb_SaasComputerCVEMap].[CVEConfigurationMapID] = [tb_CVEConfigurationMap].[CVEConfigurationMapID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY, TB_CVE, TB_SAASPENDINGPATCH
- Extra: TB_CVECONFIGURATIONMAP

**Joins X**
- Ground truth: 4 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### gpt-5

*No SQL comparison available*

---

### gpt-5-mini

**Quality Score:** 48/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerCVEMap]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerCVEMap].[ComputerID]
JOIN [tb_CVEConfigurationMap]
  ON [tb_SaasComputerCVEMap].[CVEConfigurationMapID] = [tb_CVEConfigurationMap].[CVEConfigurationMapID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY, TB_CVE, TB_SAASPENDINGPATCH
- Extra: TB_CVECONFIGURATIONMAP

**Joins X**
- Ground truth: 4 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### llama3-8b

**Quality Score:** 61/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_CVE]
JOIN [tb_SaasComputerCVEMap]
  ON [tb_CVE].[CVEID] = [tb_SaasComputerCVEMap].[CVEID]
JOIN [tb_Company]
  ON [tb_SaasComputerCVEMap].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasComputers]
  ON [tb_SaasComputerCVEMap].[ComputerID] = [tb_SaasComputers].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASPENDINGPATCH

**Joins X**
- Ground truth: 4 joins
- Generated: 3 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### llama3.1-8b

**Quality Score:** 52/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerCVEMap]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerCVEMap].[ComputerID]
JOIN [tb_CVE]
  ON [tb_SaasComputerCVEMap].[CVEID] = [tb_CVE].[CVEID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY, TB_SAASPENDINGPATCH

**Joins X**
- Ground truth: 4 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### qwen3-4b

**Quality Score:** 57/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerCVEMap]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerCVEMap].[ComputerID]
JOIN [tb_CVEConfigurationMap]
  ON [tb_SaasComputerCVEMap].[CVEConfigurationMapID] = [tb_CVEConfigurationMap].[CVEConfigurationMapID]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_CVE, TB_SAASPENDINGPATCH
- Extra: TB_CVECONFIGURATIONMAP

**Joins X**
- Ground truth: 4 joins
- Generated: 3 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### qwen3-8b

*No SQL comparison available*

---

## query_3_hardware_inventory

### gpt-4o

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-4o-mini

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5

*No SQL comparison available*

---

### gpt-5-mini

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### llama3-8b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 100
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
ORDER BY
  [tb_SaasScan].[Schedule] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### llama3.1-8b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  [tb_SaasComputers].[Name],
  [tb_SaasComputers].[DiskSize],
  [tb_Company].[Name] AS [CompanyName],
  [tb_SaasScan].[ID],
  [tb_SaasScan].[Schedule]
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
ORDER BY
  [tb_SaasScan].[Schedule] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-4b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-8b

**Quality Score:** 56/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS, TB_SAASSCAN

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations **


---

## query_4_cross_domain_analysis

### gpt-4o

**Quality Score:** 83/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[CompanyID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ComputerID]
WHERE
  (
    [tb_SaasComputers].[Name] = '%'
    AND [tb_SaasScan].[Schedule] >= CAST('2022-01-01' AS DATE)
  )
  AND [tb_SaasComputerUSBDeviceDetails].[ScanID] = 1
ORDER BY
  [tb_SaasComputers].[Name] ASC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-4o-mini

*No SQL comparison available*

---

### gpt-5

**Quality Score:** 83/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasScan].[ID] = [tb_SaasComputerUSBDeviceDetails].[ScanID]
WHERE
  [tb_SaasScan].[Schedule] >= CAST('2022-01-01' AS DATE)
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5-mini

*No SQL comparison available*

---

### llama3-8b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[CompanyID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasScan].[ID] = [tb_SaasComputerUSBDeviceDetails].[ScanID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### llama3.1-8b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  [tb_SaasComputers].[ID],
  [tb_SaasScan].[CompanyID],
  [tb_SaasScan].[Schedule],
  [tb_SaasComputerUSBDeviceDetails].[ScanID],
  [tb_SaasComputerUSBDeviceDetails].[Antecedent]
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[CompanyID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ScanID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-4b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[CompanyID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasScan].[ID] = [tb_SaasComputerUSBDeviceDetails].[ScanID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### qwen3-8b

*No SQL comparison available*

---

## query_5_application_risk

### gpt-4o

**Quality Score:** 53/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasMasterInstalledApps]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[CVEID] = [tb_CVE].[CVEID]
JOIN [tb_CVEConfiguration]
  ON [tb_SaasMasterInstalledApps].[CVEConfigurationID] = [tb_CVEConfiguration].[CVEConfigurationID]
ORDER BY
  [tb_SaasMasterInstalledApps].[Name] ASC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERINSTALLEDAPPS, TB_SAASCOMPUTERCVEMAP
- Extra: TB_CVECONFIGURATION

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### gpt-4o-mini

*No SQL comparison available*

---

### gpt-5

**Quality Score:** 36/100

**Generated SQL:**
```sql
SELECT
TOP 5
  *
FROM [tb_SaasInstalledAppsTemp]
JOIN [tb_SaasScan]
  ON [tb_SaasInstalledAppsTemp].[ScanID] = [tb_SaasScan].[ID]
ORDER BY
  [tb_SaasInstalledAppsTemp].[CVENames] DESC,
  [tb_SaasInstalledAppsTemp].[ApplicationName] ASC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERCVEMAP, TB_SAASMASTERINSTALLEDAPPS, TB_SAASCOMPUTERINSTALLEDAPPS, TB_CVE
- Extra: TB_SAASSCAN, TB_SAASINSTALLEDAPPSTEMP

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### gpt-5-mini

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasMasterInstalledApps]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[CVEID] = [tb_CVE].[CVEID]
JOIN [tb_CVEConfiguration]
  ON [tb_SaasMasterInstalledApps].[CVEConfigurationID] = [tb_CVEConfiguration].[CVEConfigurationID]
WHERE
  (
    (
      (
        (
          [tb_SaasMasterInstalledApps].[ID] >= 0
          AND [tb_SaasMasterInstalledApps].[Name] = NULL
        )
        AND [tb_CVE].[CVEID] = NULL
      )
      AND [tb_CVE].[CVSSScore] >= 0
    )
    AND [tb_CVEConfiguration].[CVEConfigurationID] = NULL
  )
  AND [tb_CVEConfiguration].[ConfigurationsName] = NULL
ORDER BY
  [tb_SaasMasterInstalledApps].[ID] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERINSTALLEDAPPS, TB_SAASCOMPUTERCVEMAP
- Extra: TB_CVECONFIGURATION

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### llama3-8b

*No SQL comparison available*

---

### llama3.1-8b

**Quality Score:** 61/100

**Generated SQL:**
```sql
SELECT
  [tb_SaasMasterInstalledApps].[Name],
  [tb_CVE].[CVEID],
  [tb_CVE].[CVSSScore]
FROM [tb_SaasMasterInstalledApps]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[CVEID] = [tb_CVE].[CVEID]
WHERE
  [tb_SaasMasterInstalledApps].[CVEID] = NULL AND [tb_CVE].[CVSSScore] >= 0
ORDER BY
  [tb_SaasMasterInstalledApps].[Name] ASC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERINSTALLEDAPPS, TB_SAASCOMPUTERCVEMAP

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### qwen3-4b

*No SQL comparison available*

---

### qwen3-8b

**Quality Score:** 53/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasMasterInstalledApps]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[CVEID] = [tb_CVE].[CVEID]
JOIN [tb_CVEConfiguration]
  ON [tb_SaasMasterInstalledApps].[CVEConfigurationID] = [tb_CVEConfiguration].[CVEConfigurationID]
ORDER BY
  [tb_CVE].[CVSSScore] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERINSTALLEDAPPS, TB_SAASCOMPUTERCVEMAP
- Extra: TB_CVECONFIGURATION

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

