import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GSM Agent Kit device API.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    args = parser.parse_args()
    uvicorn.run("gsm_agent_server.runtime.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
