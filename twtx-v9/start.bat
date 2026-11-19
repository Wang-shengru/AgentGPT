@echo off
REM TWTX V9 一鍵啟動（Windows）
chcp 65001 >nul
cd /d "%~dp0"

if not exist .env (
  copy .env.example .env >nul
  echo 已建立 .env（預設 Mock 模式）
)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
  for /f "tokens=1" %%v in ("%%b") do set "%%a=%%v"
)

if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
set REQ=backend\requirements.txt
if not "%SJ_API_KEY%"=="" if /I not "%TWTX_MODE%"=="mock" set REQ=backend\requirements-live.txt
pip install -q -r %REQ%

if not exist frontend\dist\index.html (
  where npm >nul 2>nul || (echo 需要 Node.js 18+ 以建置前端 & pause & exit /b 1)
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)

if "%API_PORT%"=="" set API_PORT=8001
echo 開啟 http://127.0.0.1:%API_PORT%
cd backend
python -m twtx
