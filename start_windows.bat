@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   SE Workflow Studio
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖 Flask ...
    python -m pip install -r requirements.txt
)

echo 启动服务：http://127.0.0.1:5000
echo 按 Ctrl+C 停止。
echo.
python app.py
pause
