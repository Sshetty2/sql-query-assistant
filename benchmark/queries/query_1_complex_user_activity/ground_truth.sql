SELECT TOP 20
    u.[Email] AS UserEmail,
    c.[Name] AS CompanyName,
    ul.[CreatedOn] AS LoginDateTime,
    ul.[UserIP] AS LoginIP,
    ul.[UserName],
    ul.[UserDevice],
    ul.[UserLocation]
FROM [tb_UserLoginInfo] ul
    INNER JOIN [tb_Users] u ON ul.[UserID] = u.[ID]
    INNER JOIN [tb_Company] c ON u.[CompanyID] = c.[ID]
WHERE ul.[CreatedOn] >= DATEADD(DAY, -90, GETDATE())
ORDER BY ul.[CreatedOn] DESC
