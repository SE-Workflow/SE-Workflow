@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   SE Workflow Studio · V5
echo   任务分解 + Agent 编排 → 一幅可编辑工作流程图
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖 ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行：python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

if not exist ".env" (
    echo [提示] 还没有 .env 文件。
    echo        接入真实大模型：copy .env.example .env，然后填入 LLM_API_KEY。
    echo        不配置也可以先用 Mock 演示完整流程。
    echo.
)

echo 启动服务：http://127.0.0.1:5000
echo 按 Ctrl+C 停止。
echo.
python app.py
pause
