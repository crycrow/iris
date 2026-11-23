from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"
HTTP = build_opener(ProxyHandler({}))


def prepare(root: Path = ROOT) -> Path:
    backend = (root.resolve() / "backend").resolve()
    environment = backend / ".venv"
    requirements = backend / "requirements.txt"
    if environment.resolve().parent != backend:
        raise RuntimeError("Окружение Python должно находиться внутри backend")
    if not requirements.is_file():
        raise RuntimeError(f"Не найден файл зависимостей: {requirements}")
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )

    def installed(code: str) -> bool:
        if not python.is_file():
            return False
        try:
            return subprocess.run(
                [str(python), "-B", "-c", code],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            ).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    if not installed("import sys; raise SystemExit(sys.version_info < (3, 12))"):
        if sys.version_info < (3, 12):
            raise RuntimeError("Установите Python 3.12 или новее")
        if environment.exists():
            backup = backend / (
                ".venv.broken-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            )
            environment.rename(backup)
            print(f"Предыдущее окружение сохранено: {backup}", flush=True)
        subprocess.run([sys.executable, "-B", "-m", "venv", str(environment)], check=True)

        for cache in environment.rglob("__pycache__"):
            if cache.is_dir() and not cache.is_symlink() and cache.resolve().is_relative_to(environment.resolve()):
                shutil.rmtree(cache)
    imports = (
        "import fastapi, uvicorn, sqlalchemy, psycopg, alembic, jwt, "
        "argon2, dotenv, apscheduler, xlsxwriter, reportlab"
    )
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / ".requirements.sha256"
    installed_digest = marker.read_text(encoding="ascii").strip() if marker.is_file() else ""
    if installed_digest != digest or not installed(imports):
        print("Установка зависимостей проекта...", flush=True)
        subprocess.run(
            [str(python), "-B", "-m", "pip", "install", "--no-compile",
             "--disable-pip-version-check", "-r", str(requirements)],
            check=True,
        )
        if not installed(imports):
            raise RuntimeError("Не удалось проверить установленные зависимости")
        marker.write_text(digest + "\n", encoding="ascii")
    print(f"Окружение готово: {python}", flush=True)
    return python


def runtime_dir() -> Path:
    if configured := os.environ.get("APP_RUNTIME_DIR"):
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        return base / "IrisRiskSystem/runtime"
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "IrisRiskSystem"


def launch_identity(mode: str) -> str:
    return hashlib.sha256((str(ROOT.resolve()) + mode).encode()).hexdigest()


def browser_url(port: int) -> str:

    build = hashlib.sha256((DIST / "index.html").read_bytes()).hexdigest()[:12]
    return f"http://127.0.0.1:{port}/?build={build}"


def probe(port: int, identity: str) -> bool:
    try:
        with HTTP.open(
            f"http://127.0.0.1:{port}/__local_launch__", timeout=0.5
        ) as response:
            marker = json.load(response)
        if marker.get("identity") != identity:
            return False
        with HTTP.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            return json.load(response).get("status") == "ok"
    except (OSError, URLError, ValueError, AttributeError):
        return False


def bind_available(preferred: int) -> tuple[socket.socket, int]:
    for port in range(preferred, min(preferred + 20, 65536)):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform == "win32":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", port))
            return listener, port
        except OSError:
            listener.close()
    raise RuntimeError("Нет доступного порта. Укажите другой через --port")


def attach_frontend(app, identity: str, mode: str, directory: Path = DIST) -> None:
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException
    from starlette.staticfiles import StaticFiles

    class WebsiteFiles(StaticFiles):
        def is_not_modified(self, response_headers, request_headers):

            if response_headers.get("content-type", "").startswith("text/html"):
                return False
            return super().is_not_modified(response_headers, request_headers)

        async def get_response(self, path: str, scope):
            parts = Path(path).parts
            if parts and (
                parts[0] in {"api", "assets"}
                or any(part.startswith(".") for part in parts)
            ):
                if parts[0] != "assets":
                    raise HTTPException(404)
            try:
                response = await super().get_response(path, scope)
            except HTTPException as error:
                if (
                    error.status_code != 404
                    or Path(path).suffix
                    or (parts and parts[0] in {"api", "assets"})
                ):
                    raise
                response = await super().get_response("index.html", scope)
            if response.headers.get("content-type", "").startswith("text/html"):
                response.headers["Cache-Control"] = "no-store"
            elif (
                parts
                and parts[0] == "assets"
                and re.fullmatch(
                    r".+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9.]+", Path(path).name
                )
            ):
                response.headers["Cache-Control"] = (
                    "public, max-age=31536000, immutable"
                )
            else:
                response.headers["Cache-Control"] = "no-cache"
            return response

    @app.get("/__local_launch__", include_in_schema=False)
    def marker():
        return JSONResponse(
            {"identity": identity, "mode": mode}, headers={"Cache-Control": "no-store"}
        )

    app.mount(
        "/", WebsiteFiles(directory=str(directory), html=True), name="local_frontend"
    )


def open_when_ready(port: int, identity: str, stopped: threading.Event) -> None:
    for _ in range(120):
        if stopped.wait(0.5):
            return
        if probe(port, identity):
            url = browser_url(port)
            print(f"Сайт готов. {url}", flush=True)
            webbrowser.open(url)
            return


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Подготовить окружение Python")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare:
        prepare()
        return 0
    if not 1024 <= args.port <= 65535:
        parser.error("Порт должен быть в диапазоне от 1024 до 65535")
    if not (DIST / "index.html").is_file():
        print(
            "Сначала соберите интерфейс. В папке frontend выполните pnpm install и pnpm build."
        )
        return 1
    try:
        from dotenv import load_dotenv
    except ImportError as error:
        print(
            f"Не установлены зависимости. Выполните backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt. {error}"
        )
        return 1
    load_dotenv(ROOT / ".env")
    mode = "postgres"
    identity = launch_identity(mode)
    runtime = runtime_dir()
    runtime.mkdir(parents=True, exist_ok=True)
    state_file = runtime / f"{mode}-launch.json"
    candidates = [args.port]
    if state_file.exists():
        try:
            candidates.insert(
                0, int(json.loads(state_file.read_text(encoding="utf-8"))["port"])
            )
        except (ValueError, KeyError, TypeError):
            pass
    for candidate in dict.fromkeys(candidates):
        if 1024 <= candidate <= 65535 and probe(candidate, identity):
            url = browser_url(candidate)
            print(f"Сайт уже работает. {url}")
            if not args.no_browser:
                webbrowser.open(url)
            return 0
    listener, port = bind_available(args.port)
    stopped = threading.Event()
    try:
        os.environ["LOG_DIR"] = str(runtime / "logs")
        os.chdir(BACKEND)
        sys.path.insert(0, str(BACKEND))
        try:
            import uvicorn
            from alembic import command
            from alembic.config import Config
        except ImportError as error:
            print(
                f"Не установлены зависимости. Выполните backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt. {error}"
            )
            return 1
        command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        from app.main import app

        attach_frontend(app, identity, mode)
        state_file.write_text(
            json.dumps({"port": port, "pid": os.getpid(), "mode": mode}),
            encoding="utf-8",
        )
        print("Подключение PostgreSQL из .env", flush=True)
        print(f"Адрес сайта http://127.0.0.1:{port}", flush=True)
        print(
            "Для остановки нажмите Shift+F5 в VS Code или Ctrl+C в терминале.",
            flush=True,
        )
        if not args.no_browser:
            threading.Thread(
                target=open_when_ready, args=(port, identity, stopped), daemon=True
            ).start()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="info", access_log=False
        )
        uvicorn.Server(config).run(sockets=[listener])
        return 0
    finally:
        stopped.set()
        listener.close()
        if state_file.exists():
            try:
                if (
                    json.loads(state_file.read_text(encoding="utf-8")).get("pid")
                    == os.getpid()
                ):
                    state_file.unlink()
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Не удалось запустить сайт. {error}", file=sys.stderr)
        raise SystemExit(1)
