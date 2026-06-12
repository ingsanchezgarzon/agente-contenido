import sys
from datetime import datetime
from rich.console import Console
from rich.theme import Theme

_theme = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "bold red",
    "agent": "bold magenta",
})

# Use no_color mode on Windows to avoid encoding issues with rich/cp1252
console = Console(theme=_theme, no_color=False if sys.platform != "win32" else False, legacy_windows=True)


def log(level: str, agent: str, message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    style = {"INFO": "info", "OK": "success", "WARN": "warning", "ERROR": "error"}.get(level, "info")
    console.print(f"[dim]{ts}[/dim] [[agent]{agent}[/agent]] [{style}]{level}[/{style}] {message}")


def info(agent: str, message: str) -> None:
    log("INFO", agent, message)


def success(agent: str, message: str) -> None:
    log("OK", agent, message)


def warning(agent: str, message: str) -> None:
    log("WARN", agent, message)


def error(agent: str, message: str) -> None:
    log("ERROR", agent, message)


if __name__ == "__main__":
    info("test", "Logger initialized successfully")
    success("test", "This is a success message")
    warning("test", "This is a warning")
    error("test", "This is an error")
