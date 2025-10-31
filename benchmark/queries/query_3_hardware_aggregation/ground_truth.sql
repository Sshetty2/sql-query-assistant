SELECT TOP 100
    c.[Name] AS CompanyName,
    comp.[Name] AS ComputerName,
    dd.[Name] AS DiskName,
    dd.[SerialNumber],
    CAST(dd.[Size] AS BIGINT) / (1024 * 1024 * 1024) AS DiskSizeGB,
    s.[CreatedOn] AS ScanDate
FROM [tb_SaasComputerDiskDriveDetails] dd
    INNER JOIN [tb_SaasComputers] comp ON dd.[ComputerID] = comp.[ID]
    INNER JOIN [tb_Company] c ON comp.[CompanyID] = c.[ID]
    INNER JOIN [tb_SaasScan] s ON dd.[ScanID] = s.[ID]
WHERE dd.[IsDeleted] = 0
    AND comp.[IsDeleted] = 0
    AND dd.[IsLatest] = 1
    AND dd.[Size] IS NOT NULL
ORDER BY s.[CreatedOn] DESC, c.[Name], comp.[Name]
