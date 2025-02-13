from websockets.sync.client import connect
import random
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.compiler import transpile
from qiskit.qasm2 import dumps
from hashlib import sha256
import argparse
from selenium import webdriver

def initializeConnection(qkdIP, url, username):
    addr = "ws://" + qkdIP + ":8765"
    with connect(addr) as websocket:
        while True:
            print("Initialising quantum key exchange with BB84 protocol")
            serverQubits = []
            for i in range(256):
                serverQubits.append(websocket.recv())
            
            bits = []
            simulator = AerSimulator()
            clientBasis = [random.choice(['X', 'Z']) for _ in range(256)]
            for i in range(256):
                qc = QuantumCircuit.from_qasm_str(serverQubits[i])
                if clientBasis[i] == 'X':
                    qc.h(0)
                qc.measure(0,0)
                job = simulator.run(qc, shots=1)
                result = job.result()
                counts = result.get_counts()
                measured_bit = int(max(counts, key=counts.get))    
                bits.append(measured_bit)
            
            #sending basis to server then receive server basis
            websocket.send(" ".join(clientBasis))
            serverBasis = websocket.recv().split(" ")

            #basis reconciliation
            siftkey = ""
            for i in range(256):
                if serverBasis[i] == clientBasis[i]:
                    siftkey += str(bits[i])

            if len(siftkey) < 128:
                continue
            
            #error checking
            startingbit, endingbit = [int(i) for i in websocket.recv().split()]
            serverSubsetHash = websocket.recv()
            
            if endingbit < startingbit:
                toHash = siftkey[startingbit:] + siftkey[:endingbit]
            else:
                toHash = siftkey[startingbit:endingbit]
            
            clientSubsetHash = sha256(toHash.encode()).hexdigest()
            if clientSubsetHash == serverSubsetHash:
                print("No interception occurred")
                websocket.send("0")
                break
            else:
                print("[ALERT] interception occurred")
                websocket.send("1")
                return
        siftkey = siftkey[:128]
        sharedKey = int(siftkey, 2).to_bytes((len(siftkey) + 7) // 8, 'big')
        
        print(f"Authenticated with shared key hash: {sha256(sharedKey).hexdigest()}") 
        websocket.send(url)
        websocket.send(username)
        res = websocket.recv()
        if res == "1":
            raise Exception("Something unexpected happened to the web server, maybe it's down...?")
        return sharedKey
    


def main():
    parser = parser = argparse.ArgumentParser()
    parser.add_argument('username', help='The username the client wants to register for the chat system')
    parser.add_argument('qkd', help='The IP address of the QKD server')
    parser.add_argument('url', help='The URL of the Secure Chat Webserver')
    parser.add_argument("--browser", help='Automatically opens Chrome Browser after initializing the quantum key exchange')
    args = parser.parse_args()
    sharedKey = initializeConnection(args.qkd, args.url, args.username)

    if args.browser:
        from selenium.webdriver.chrome.options import Options
        
        #OPEN BROWSER
        chrome_options = Options()
        chrome_options.add_experimental_option("detach", True)
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        driver.get(args.url)
    
if __name__ == "__main__":
    main()