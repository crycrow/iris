import argparse
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def create_environment(path: Path) -> bool:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as target:
            password = secrets.token_hex(24)
            target.write(
                "POSTGRES_DB=risk_system_vkr\nPOSTGRES_USER=risk_app\nPOSTGRES_PASSWORD="
                + password
                + "\nSECRET_KEY="
                + secrets.token_hex(32)
                + "\nDATABASE_URL=postgresql+psycopg://risk_app:"
                + password
                + "@localhost:5433/risk_system_vkr\nAPP_TIMEZONE=Europe/Moscow\nSEED_DEMO=true\nSCHEDULER_ENABLED=true\nBACKUP_KEEP=14\n"
            )
    except FileExistsError:
        return False
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Создать настройки PostgreSQL для Docker")
    parser.add_argument(
        "--output", type=Path, default=Path(".env.docker"),
        help="Файл настроек; относительный путь считается от корня проекта (по умолчанию .env.docker)",
    )
    args = parser.parse_args(argv)
    path = args.output if args.output.is_absolute() else ROOT / args.output
    if create_environment(path):
        print(f"Создан {path.name} со случайными секретами")
    else:
        print(f"Файл {path.name} уже существует и сохранён без изменений")


if __name__ == "__main__":
    main()
