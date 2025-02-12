import socket
import argparse
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ip", help="Server IP address")
    parser.add_argument("port", type=int, help="Server port")
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((args.ip, args.port))
        try:
            while True:
                data = b'I am Bob'
                client.sendall(data)
                print(f"Sent: {data}")
                time.sleep(1)
        except:
            pass
        finally:
            client.close()

if __name__ == "__main__":
    main()
