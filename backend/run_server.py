import argparse
import asyncio

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the QW backend server.")
    parser.add_argument("--host", default="::")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--ssl-certfile", default="")
    parser.add_argument("--ssl-keyfile", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            ssl_certfile=args.ssl_certfile or None,
            ssl_keyfile=args.ssl_keyfile or None,
        )
    except KeyboardInterrupt:
        print("INFO: server stopped by user.")
        return 0
    except asyncio.CancelledError:
        print("INFO: server shutdown completed.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
