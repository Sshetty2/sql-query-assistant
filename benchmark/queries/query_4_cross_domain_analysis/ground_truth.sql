SELECT TOP 100
    c.[Name] AS CompanyName,
    comp.[Name] AS ComputerName,
    usb.[Antecedent] AS USBDeviceAntecedent,
    usb.[Dependent] AS USBDeviceDependent,
    s.[CreatedOn] AS ScanDate,
    s.[ScanName]
FROM [tb_SaasComputerUSBDeviceDetails] usb
    INNER JOIN [tb_SaasComputers] comp ON usb.[ComputerID] = comp.[ID]
    INNER JOIN [tb_Company] c ON comp.[CompanyID] = c.[ID]
    INNER JOIN [tb_SaasScan] s ON comp.[ScanID] = s.[ID]
WHERE comp.[IsDeleted] = 0
    AND usb.[IsDeleted] = 0
    AND s.[CreatedOn] >= DATEADD(DAY, -60, GETDATE())
ORDER BY s.[CreatedOn] DESC, c.[Name], comp.[Name]
