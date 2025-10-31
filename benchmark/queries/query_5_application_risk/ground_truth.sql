SELECT TOP 5
    master_app.[Name] AS ApplicationName,
    COUNT(DISTINCT comp_app.[ComputerID]) AS AffectedComputerCount,
    COUNT(DISTINCT cve.[CVEID]) AS TotalCVECount,
    AVG(CAST(cve.[CVSSScore] AS FLOAT)) AS AvgCVSSScore
FROM [tb_SaasMasterInstalledApps] master_app
    INNER JOIN [tb_SaasComputerInstalledApps] comp_app
        ON master_app.[Name] = comp_app.[Name]
    INNER JOIN [tb_SaasComputerCVEMap] cve_map
        ON comp_app.[ID] = cve_map.[InstalledAppID]
    INNER JOIN [tb_CVE] cve
        ON cve_map.[CVEID] = cve.[CVEID]
WHERE master_app.[IsDeleted] = 0
    AND comp_app.[IsDeleted] = 0
    AND cve_map.[IsDeleted] = 0
    AND cve.[IsDeleted] = 0
    AND cve.[CVSSScore] IS NOT NULL
GROUP BY master_app.[ID], master_app.[Name]
HAVING COUNT(DISTINCT cve.[CVEID]) > 0
ORDER BY AvgCVSSScore DESC, TotalCVECount DESC
