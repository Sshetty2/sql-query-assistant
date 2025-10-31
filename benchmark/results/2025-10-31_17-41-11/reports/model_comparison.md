# Model Comparison Report

## query_1_complex_user_activity

### gpt-4o

**Quality Score:** 80/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
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
  *
FROM [tb_UserLoginInfo]
JOIN [tb_Users]
  ON [tb_UserLoginInfo].[UserID] = [tb_Users].[ID]
JOIN [tb_Company]
  ON [tb_UserLoginInfo].[CompanyID] = [tb_Company].[ID]
```

### SQL Comparison Summary

**Tables **

**Joins **
- Ground truth: 2 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5

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

### gpt-5-mini

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
JOIN [tb_CVEConfigurationMap]
  ON [tb_SaasComputerCVEMap].[ID] = [tb_CVEConfigurationMap].[CVEConfigurationMapID]
JOIN [tb_SaasComputers]
  ON [tb_SaasComputerCVEMap].[ComputerID] = [tb_SaasComputers].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_CVE, TB_SAASPENDINGPATCH, TB_COMPANY
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
- Missing: TB_CVE, TB_SAASPENDINGPATCH, TB_SAASCOMPUTERS
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

*No SQL comparison available*

---

### llama3-8b

**Quality Score:** 50/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_ApplicationTagMap]
JOIN [tb_SoftwareTagsAndColors]
  ON [tb_ApplicationTagMap].[ID] = [tb_SoftwareTagsAndColors].[ID]
WHERE
  [tb_ApplicationTagMap].[TagID] IN (
    SELECT
      [ID]
    FROM [tb_SoftwareTagsAndColors]
  )
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASPENDINGPATCH, TB_COMPANY, TB_SAASCOMPUTERCVEMAP, TB_SAASCOMPUTERS, TB_CVE
- Extra: TB_SOFTWARETAGSANDCOLORS, TB_APPLICATIONTAGMAP

**Joins X**
- Ground truth: 4 joins
- Generated: 1 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### llama3.1-8b

*No SQL comparison available*

---

### qwen3-4b

**Quality Score:** 35/100

**Generated SQL:**
```sql
SELECT
TOP 10
  *
FROM [tb_SaasInstalledAppsTemp]
JOIN [tb_SaasScan]
  ON [tb_SaasInstalledAppsTemp].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASPENDINGPATCH, TB_COMPANY, TB_SAASCOMPUTERCVEMAP, TB_SAASCOMPUTERS, TB_CVE
- Extra: TB_SAASSCAN, TB_SAASINSTALLEDAPPSTEMP

**Joins X**
- Ground truth: 4 joins
- Generated: 1 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

### qwen3-8b

**Quality Score:** 48/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputerCVEMap]
JOIN [tb_Company]
  ON [tb_SaasComputerCVEMap].[CompanyID] = [tb_Company].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputerCVEMap].[ScanID] = [tb_SaasScan].[ID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_CVE, TB_SAASPENDINGPATCH, TB_SAASCOMPUTERS
- Extra: TB_SAASSCAN

**Joins X**
- Ground truth: 4 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp."ID"), COUNT(DISTINCT cve."CVEID")


---

## query_3_hardware_inventory

### gpt-4o

**Quality Score:** 51/100

**Generated SQL:**
```sql
SELECT
  [tb_SaasComputers].[Name],
  [tb_SaasComputers].[DiskSize],
  [tb_SaasNetworkDomain].[CompanyID],
  [tb_SaasNetworkDomain].[Name] AS [NetworkDomainName]
FROM [tb_SaasComputers]
JOIN [tb_SaasNetworkDomain]
  ON [tb_SaasComputers].[CompanyID] = [tb_SaasNetworkDomain].[CompanyID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS, TB_SAASSCAN, TB_COMPANY
- Extra: TB_SAASNETWORKDOMAIN

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations **


---

### gpt-4o-mini

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 10
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

### gpt-5

**Quality Score:** 70/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasNetworkDomain]
  ON [tb_SaasComputers].[ID] = [tb_SaasNetworkDomain].[ID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ScanID] = [tb_SaasScan].[ID]
JOIN [tb_SaasComputerOsDetails]
  ON [tb_SaasScan].[ID] = [tb_SaasComputerOsDetails].[ScanID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS, TB_COMPANY
- Extra: TB_SAASNETWORKDOMAIN, TB_SAASCOMPUTEROSDETAILS

**Joins **
- Ground truth: 3 joins
- Generated: 3 joins

**Aggregations **


---

### gpt-5-mini

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

### llama3-8b

**Quality Score:** 56/100

**Generated SQL:**
```sql
SELECT
TOP 1
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
ORDER BY
  [tb_SaasScan].[Schedule] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS, TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations **


---

### llama3.1-8b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
JOIN [tb_Company]
  ON [tb_SaasComputers].[CompanyID] = [tb_Company].[ID]
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
ORDER BY
  [tb_SaasScan].[Schedule] DESC,
  [tb_SaasComputers].[CreatedOn] ASC
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
TOP 1
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
ORDER BY
  [tb_SaasScan].[CreatedOn] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERDISKDRIVEDETAILS, TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations **


---

## query_4_cross_domain_analysis

### gpt-4o

*No SQL comparison available*

---

### gpt-4o-mini

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
  [tb_SaasComputers].[ID] >= DATEADD([year], -1, GETDATE())
  AND [tb_SaasScan].[Schedule] <= GETDATE()
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations **


---

### gpt-5

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ComputerID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputerUSBDeviceDetails].[ScanID] = [tb_SaasScan].[ID]
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

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ComputerID]
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_COMPANY

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
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ComputerID]
JOIN [tb_SaasScan]
  ON [tb_SaasComputerUSBDeviceDetails].[ScanID] = [tb_SaasScan].[ID]
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
TOP 500
  *
FROM [tb_SaasComputers]
JOIN [tb_SaasScan]
  ON [tb_SaasComputers].[ID] = [tb_SaasScan].[ID]
JOIN [tb_SaasComputerUSBDeviceDetails]
  ON [tb_SaasComputers].[ID] = [tb_SaasComputerUSBDeviceDetails].[ComputerID]
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

*No SQL comparison available*

---

### gpt-4o-mini

**Quality Score:** 53/100

**Generated SQL:**
```sql
SELECT
TOP 500
  [tb_CVEConfiguration].[ConfigurationsName],
  [tb_CVEConfiguration].[NVD_Version],
  [tb_SaasMasterInstalledApps].[Name],
  [tb_SaasMasterInstalledApps].[Versions],
  [tb_CVE].[CVEName],
  [tb_CVE].[CVSSScore]
FROM [tb_CVEConfiguration]
JOIN [tb_SaasMasterInstalledApps]
  ON [tb_CVEConfiguration].[CVEConfigurationID] = [tb_SaasMasterInstalledApps].[ID]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[ID] = [tb_CVE].[CVEID]
ORDER BY
  [tb_CVE].[CVSSScore] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERCVEMAP, TB_SAASCOMPUTERINSTALLEDAPPS
- Extra: TB_CVECONFIGURATION

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


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
- Missing: TB_SAASCOMPUTERCVEMAP, TB_SAASCOMPUTERINSTALLEDAPPS, TB_CVE, TB_SAASMASTERINSTALLEDAPPS
- Extra: TB_SAASSCAN, TB_SAASINSTALLEDAPPSTEMP

**Joins X**
- Ground truth: 3 joins
- Generated: 1 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### gpt-5-mini

*No SQL comparison available*

---

### llama3-8b

*No SQL comparison available*

---

### llama3.1-8b

*No SQL comparison available*

---

### qwen3-4b

**Quality Score:** 68/100

**Generated SQL:**
```sql
SELECT
  [tb_SaasMasterInstalledApps].[Name],
  [tb_SaasMasterInstalledApps].[Versions],
  [tb_CVE].[CVSSScore],
  [tb_CVEConfiguration].[CVEConfigurationID]
FROM [tb_SaasMasterInstalledApps]
JOIN [tb_CVE]
  ON [tb_SaasMasterInstalledApps].[CVEID] = [tb_CVE].[CVEID]
JOIN [tb_CVEConfiguration]
  ON [tb_SaasMasterInstalledApps].[CVEConfigurationID] = [tb_CVEConfiguration].[CVEConfigurationID]
WHERE
  [tb_CVEConfiguration].[ConfigurationsName] = '*'
ORDER BY
  [tb_CVE].[CVSSScore] DESC
```

### SQL Comparison Summary

**Tables X**
- Missing: TB_SAASCOMPUTERCVEMAP, TB_SAASCOMPUTERINSTALLEDAPPS
- Extra: TB_CVECONFIGURATION

**Joins X**
- Ground truth: 3 joins
- Generated: 2 joins

**Aggregations X**
- Ground truth: COUNT(DISTINCT comp_app."ComputerID"), COUNT(DISTINCT cve."CVEID"), AVG(CAST(cve."CVSSScore" AS FLOAT)), COUNT(DISTINCT cve."CVEID")


---

### qwen3-8b

*No SQL comparison available*

---

