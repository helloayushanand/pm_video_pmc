"""Launch the PM Video Pipeline web UI."""

import sys
import uvicorn


def main():
    # Verify critical deps before starting
    for mod in ("openai", "pydantic", "tenacity", "fastapi"):
        try:
            __import__(mod)
        except ImportError:
            print(f"FATAL: '{mod}' not installed. Run: pip install -r requirements.txt")
            sys.exit(1)

    uvicorn.run(
        "app.web.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["app/web"],
    )


if __name__ == "__main__":
    main()
