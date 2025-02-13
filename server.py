import socket
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ip", help="Server IP address")
    parser.add_argument("port", type=int, help="Server port")
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((args.ip, args.port))
        server.listen()

        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    while True:
                        data = conn.recv(8)
                        if not data:
                            break
                        print(f"Received: {data}")
                except:
                    pass
                finally:
                    conn.close()

if __name__ == "__main__":
    main()