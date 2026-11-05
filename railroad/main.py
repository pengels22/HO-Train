import argparse
import logging
from railroad.api.server import serve

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("simulation", "hardware"), default="simulation")
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger(__name__).info("starting in %s mode; outputs remain safe until explicitly initialized", args.mode)
    if args.dashboard: serve(args.host, args.port)

if __name__ == "__main__": main()
