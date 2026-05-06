"""
tcp_test_client.py
------------------
Simulates the LabVIEW TCP receiver.
Run this on ANY machine to verify gauge_reader.py is sending data correctly.

Usage:
    python tcp_test_client.py --host 127.0.0.1 --port 5005
"""

import socket
import json
import argparse
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port} …")
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((args.host, args.port))
            print("Connected! Receiving readings:\n")
            buf = ""
            while True:
                chunk = s.recv(1024).decode()
                if not chunk:
                    print("Server closed connection.")
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    try:
                        data = json.loads(line)
                        ts   = time.strftime("%H:%M:%S",
                               time.localtime(data["timestamp"]))
                        print(f"  [{ts}]  value = {data['value']:.3f}")
                    except json.JSONDecodeError:
                        print(f"  Raw: {line}")
        except ConnectionRefusedError:
            print("Connection refused — is gauge_reader.py running? Retrying in 2 s …")
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        finally:
            try:
                s.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
