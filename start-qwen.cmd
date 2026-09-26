@echo off
rem ============================================================
rem  CLI2API 启动脚本（Qoder CN / qwen3.8-flash）
rem  由编排者创建 2026-09-26。
rem
rem  为什么需要"等待 + 补探"：
rem    cli2api 只在启动时跑一次健康探测（app.go:121 `go manager.RefreshAll`），
rem    而 Qoder worker 的 pure-wasm boot 需要约 20 秒才监听端口。
rem    启动探测撞在 boot 窗口内会拿到 connection refused，账号被永久标记
rem    auth_failed，之后**没有任何周期性重探**（RunMaintenanceLoop 只做签到/
rem    保活，不含健康探测）⇒ 表现为 "no worker accounts configured"。
rem    本脚本在 worker 就绪后补发一次探测（POST /api/accounts/{id}/refresh）。
rem ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist "bin\cli2api.exe" (
  echo [ERROR] 缺少 bin\cli2api.exe，请先构建
  exit /b 1
)

echo [1/3] 启动 cli2api...
start "" /B bin\cli2api.exe
timeout /t 30 /nobreak >nul

echo [2/3] 读取管理员密钥（首次启动会打印并存入 SQLite）...
rem 密钥来源：首次启动时它会打印一次并存进 SQLite 的 app_secrets 表；
rem 之后每次启动都不再打印，所以这里直接查数据库（而不是读日志）。
for /f "tokens=*" %%L in ('python "%~dp0get-key.py" 2^>nul') do set "ADMINKEY=%%L"
if "%ADMINKEY%"=="" (
  echo [WARN] 未能读到管理员密钥，请手动运行: python get-key.py
  goto :eof
)
echo      admin key: %ADMINKEY%

echo [3/3] 补发健康探测（修启动时序缺陷）...
for /f "tokens=*" %%A in ('powershell -NoProfile -Command "(Invoke-RestMethod -Uri 'http://127.0.0.1:3010/api/accounts' -Headers @{Authorization='Bearer %ADMINKEY%'}).data | Select-Object -First 1 -ExpandProperty id"') do set "ACCID=%%A"
if "%ACCID%"=="" (
  echo [WARN] 未找到账号，请先在控制台 http://127.0.0.1:3010 添加并登录 Qoder CN 账号。
  goto :eof
)
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:3010/api/accounts/%ACCID%/refresh') -Headers @{Authorization='Bearer %ADMINKEY%'}; Write-Output ('  account=%ACCID% ready=' + $r.ready + ' status=' + $r.status) } catch { Write-Output ('  探测失败: ' + $_.Exception.Message) }"

echo.
echo 完成。端点: http://127.0.0.1:3010/v1   模型: qwen3.8-flash
endlocal
