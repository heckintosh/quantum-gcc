import socket
import sys
import random
import argparse

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.qasm2 import loads
from qiskit.compiler import transpile
from hashlib import sha256

def send_message(conn, msg_bytes: bytes):
    length = len(msg_bytes)
    conn.sendall(length.to_bytes(8, byteorder='big'))
    conn.sendall(msg_bytes)

def recv_message(conn) -> bytes:
    length_data = conn.recv(8)
    if not length_data or len(length_data) < 8:
        return None
    
    length = int.from_bytes(length_data, byteorder='big')
    data = b''
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def initializeConnection(qkdIP, url, username):
    """
    Replaces the websockets logic with a raw TCP socket approach.
    """
    addr = (qkdIP, 8765)
    simulator = AerSimulator()
    num_qubits = 256
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        print("[Client] Connecting to QKD server at", addr)
        sock.connect(addr)

        while True:
            print("[Client] Initialising quantum key exchange with BB84 protocol.")
            
            # 1. Receive the 256 QASM circuits from server
            serverQubits = []
            for _ in range(num_qubits):
                data = recv_message(sock)
                if data is None:
                    raise ConnectionError("[Client] Server closed connection unexpectedly.")
                serverQubits.append(data.decode('utf-8'))
            
            # 2. Random client basis + measure bits
            bits = []
            clientBasis = [random.choice(['X', 'Z']) for _ in range(num_qubits)]
            for qasm_str in serverQubits:
                qc = QuantumCircuit.from_qasm_str(qasm_str)
                # If our basis is X, apply Hadamard before measure
                if clientBasis[len(bits)] == 'X':
                    qc.h(0)
                qc.measure(0, 0)
                job = simulator.run(qc, shots=1)
                result = job.result()
                counts = result.get_counts()
                measured_bit = int(max(counts, key=counts.get))
                bits.append(measured_bit)
            
            # 3. Send client basis to server
            send_message(sock, " ".join(clientBasis).encode('utf-8'))
            
            # 4. Receive server basis
            data = recv_message(sock)
            if data is None:
                raise ConnectionError("[Client] Server closed connection unexpectedly.")
            serverBasis = data.decode('utf-8').split()
            
            # 5. Basis reconciliation -> Sifted Key
            siftkey = ""
            for i in range(num_qubits):
                if serverBasis[i] == clientBasis[i]:
                    siftkey += str(bits[i])
            
            # If not enough bits for 128, start again
            if len(siftkey) < 128:
                continue
            
            # 6. Error checking subset
            data = recv_message(sock)
            if data is None:
                raise ConnectionError("[Client] Server disconnected during error-check.")
            startingbit, endingbit = [int(i) for i in data.decode('utf-8').split()]
            
            data = recv_message(sock)
            if data is None:
                raise ConnectionError("[Client] Server disconnected during error-check.")
            serverSubsetHash = data.decode('utf-8')
            
            if endingbit < startingbit:
                toHash = siftkey[startingbit:] + siftkey[:endingbit]
            else:
                toHash = siftkey[startingbit:endingbit]
            
            clientSubsetHash = sha256(toHash.encode()).hexdigest()
            
            # 7. Compare subset hash to detect eavesdropping
            if clientSubsetHash == serverSubsetHash:
                print("[Client] No eavesdrop detected.")
                send_message(sock, b"0")  # 0 means all good
                break
            else:
                print("[Client] Eavesdrop detected!")
                send_message(sock, b"1")
                # Start entire QKD process again or exit. 
                # For the original code, it ended QKD entirely:
                sys.exit(1)
        
        # 8. Final 128-bit key
        siftkey = siftkey[:128]
        sharedKey = int(siftkey, 2).to_bytes((len(siftkey) + 7) // 8, 'big')
        print(f"[Client] Authenticated with shared key hash: {sha256(sharedKey).hexdigest()}")
        
        # 9. Send the final data: URL + username
        send_message(sock, url.encode('utf-8'))
        send_message(sock, username.encode('utf-8'))
        
        # 10. Receive final result from server (0=OK, 1=fail)
        data = recv_message(sock)
        if data is None:
            print("[Client] Server disconnected before final result.")
            sys.exit(1)
        res = data.decode('utf-8')
        if res == "1":
            raise Exception("[Client] The web server update failed or server returned error.")
        else:
            print("[Client] Successfully updated the web server.")
        
        return sharedKey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help='The username the client wants to register for the chat system')
    parser.add_argument('qkd', help='The IP address of the QKD server')
    parser.add_argument('url', help='The URL of the Secure Chat Webserver')
    parser.add_argument("--browser", help='Automatically open a local Chrome Browser after quantum key exchange',
                        action='store_true')
    args = parser.parse_args()

    sharedKey = initializeConnection(args.qkd, args.url.strip('/'), args.username)

    # Optionally open the browser if requested
    if args.browser:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        chrome_options.add_experimental_option("detach", True)
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        driver.get(args.url)


if __name__ == "__main__":
    main()