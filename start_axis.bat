@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   AXIS Personal OS 3.0  -  本地一键启动
echo   （双击本文件即可运行，不要关闭弹出的黑窗口）
echo ============================================================

REM ---- 1. 检查 Python 是否安装 ----
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [错误] 本机没找到 Python。
    echo 请先安装：https://www.python.org/downloads/
    echo 安装时务必勾选 "Add python.exe to PATH"（添加到 PATH）。
    echo 装好后重新双击本文件即可。
    echo.
    pause
    exit /b 1
)

REM ---- 2. 创建虚拟环境（仅首次） ----
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] 首次运行：创建隔离环境...
    python -m venv venv
)

REM ---- 3. 安装依赖（仅首次较慢） ----
call venv\Scripts\activate.bat
echo [2/3] 安装依赖...
pip install -q -r requirements.txt

REM ---- 4. 启动并打开浏览器 ----
echo [3/3] 启动 AXIS，正在打开浏览器...
start "" http://localhost:5000
set HOST=0.0.0.0
set PORT=5000
python app.py

echo.
echo AXIS 已停止。如需再次使用，双击本文件即可。
pause
