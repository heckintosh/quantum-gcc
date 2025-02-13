import socket
import random
import sys
from hashlib import sha256
import requests

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.qasm2 import dumps

HOST = "0.0.0.0"   # Listen on all interfaces
PORT = 8765

def send_message(conn, msg_bytes: bytes):
    """
    Send length + message over the socket.
    8 bytes for length in big-endian, followed by the raw data.
    """
    length = len(msg_bytes)
    conn.sendall(length.to_bytes(8, byteorder='big'))
    conn.sendall(msg_bytes)

def recv_message(conn) -> bytes:
    """
    Receive a length-framed message: first 8 bytes for length,
    then read exactly that many bytes. Returns None if there's a socket error.
    """
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

def updateWebServer(serverURL, key, username):
    """
    Example of updating a remote web server with the newly established quantum key.
    """
    try:
        data = {'quantkey': key, 'username': username}
        headers = {'Authorization': 'qkdadmin'}
        res = requests.post(serverURL + "/update", data=data, headers=headers)
        if res.status_code == 200:
            print("[Server] Successfully updated the server with the session quant key.")
            return 0
        else:
            print(f"[Server] Webserver responded with status code {res.status_code}.")
            return 1
    except Exception as e:
        print("[Server] Error contacting the web server:", e)
        return 1

def handle_client(conn, addr):
    """
    Core QKD logic from your original websockets-based approach, adapted to raw sockets.
    """
    print(f"[Server] Handling new connection from {addr}")
    num_qubits = 256
    simulator = AerSimulator()
    
    while True:
        print("[Server] Initialising quantum key exchange with BB84 protocol.")
        
        # 1. Prepare bits and basis
        bits = [random.randint(0, 1) for _ in range(num_qubits)]
        serverBasis = [random.choice(['X', 'Z']) for _ in range(num_qubits)]
        
        # 2. Send the QASM circuits to the client
        for i in range(num_qubits):
            qc = QuantumCircuit(1, 1)
            if bits[i] == 1:
                qc.x(0)
            if serverBasis[i] == "X":
                qc.h(0)
            
            qasm_str = dumps(qc)    # Convert to QASM
            send_message(conn, qasm_str.encode('utf-8'))
        
        # 3. Receive the client's basis
        data = recv_message(conn)
        if data is None:
            print("[Server] Client disconnected unexpectedly.")
            return
        clientBasis = data.decode('utf-8').split()

        # 4. Send our (server) basis to the client
        send_message(conn, " ".join(serverBasis).encode('utf-8'))
        
        # 5. Basis reconciliation
        siftkey = ""
        for i in range(num_qubits):
            if serverBasis[i] == clientBasis[i]:
                siftkey += str(bits[i])

        # If there's not enough bits to form the 16-byte (128-bit) key, start over
        if len(siftkey) < 128:
            continue
        
        # 6. Error checking subset
        startingbit = random.randint(0, len(siftkey) - 1)
        subsetSize = random.randint(64, 96)
        endingbit = (startingbit + subsetSize) % len(siftkey)
        
        if endingbit < startingbit:
            toHash = siftkey[startingbit:] + siftkey[:endingbit]
        else:
            toHash = siftkey[startingbit:endingbit]
        
        subsetHash = sha256(toHash.encode()).hexdigest()

        # 7. Send the subset index + hash
        send_message(conn, f"{startingbit} {endingbit}".encode('utf-8'))
        send_message(conn, subsetHash.encode('utf-8'))
        
        # 8. Receive validation from client
        data = recv_message(conn)
        if data is None:
            print("[Server] Client disconnected before sending validation.")
            return
        res = data.decode('utf-8')
        
        # If client says "0", no eavesdrop detected -> break
        # If client says "1", eavesdrop detected -> close the connection
        if res == "0":
            break
        else:
            print("[ALERT] Detected Eavesdropper on the Quantum Channel. Terminating.")
            conn.close()
            sys.exit(0)   # or just return
    
    # 9. Derive the final 128-bit key
    siftkey = siftkey[:128]
    sharedKey = int(siftkey, 2).to_bytes((len(siftkey) + 7) // 8, 'big')
    
    # 10. Receive final data from client: URL and username
    data = recv_message(conn)
    if data is None:
        print("[Server] Client disconnected.")
        return
    url = data.decode('utf-8').rstrip('/')
    
    data = recv_message(conn)
    if data is None:
        print("[Server] Client disconnected.")
        return
    username = data.decode('utf-8')
    
    print(f"[Server] Authenticated user {username} with shared key.")
    
    # 11. Update Web Server
    result = updateWebServer(url, bytes.hex(sharedKey), username)
    # 12. Send the result back to client
    send_message(conn, str(result).encode('utf-8'))
    
    print("[Server] Done. Closing connection.")
    conn.close()


def main():
    print("[Server] QKD Server listening on port", PORT)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(5)
        
        while True:
            conn, addr = sock.accept()
            handle_client(conn, addr)

if __name__ == "__main__":
    main()