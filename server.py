import asyncio
from websockets.server import serve
import random
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.compiler import transpile
from qiskit.qasm2 import dumps
from hashlib import sha256
import requests
import argparse
import functools

async def server(websocket, path, intercept=False):
    num_qubits = 256 
    while True:
        print("Initialising quantum key exchange with BB84 protocol")
        bits = [random.randint(0, 1) for _ in range(num_qubits)]  
        serverBasis = [random.choice(['X', 'Z']) for _ in range(num_qubits)]  
        qubits = []  

        if intercept:
            interceptBasis = [random.choice(['X', 'Z']) for _ in range(num_qubits)]  
            simulator = AerSimulator()

        for i in range(num_qubits):
            qc = QuantumCircuit(1, 1)
            if bits[i] == 1:
                qc.x(0)
            if serverBasis[i] == "X":
                qc.h(0)

            if intercept:
                if interceptBasis[i] == 'X':
                    qc.h(0)
                qc.measure(0,0)
                job = simulator.run(qc, shots=1)
                result = job.result()
                counts = result.get_counts()

            qubits.append(qc)
            await websocket.send(dumps(qc)) #assume qubits sent to bob

        #receive client basis then send basis to client
        clientBasis = await websocket.recv()
        clientBasis = clientBasis.split(" ")
        await websocket.send(" ".join(serverBasis))
        
        #basis reconciliation
        siftkey = ""
        for i in range(256):
            if serverBasis[i] == clientBasis[i]:
                siftkey += str(bits[i])
        
        #restart initialisation since not enough for 16 bytes of key
        if len(siftkey) < 128:
            continue
        
        #error checking
        startingbit = random.randint(0,len(siftkey)-1)
        subsetSize = random.randint(64,96)
        endingbit = (startingbit + subsetSize) % len(siftkey)
        
        if endingbit < startingbit:
            toHash = siftkey[startingbit:] + siftkey[:endingbit]
        else:
            toHash = siftkey[startingbit:endingbit]
        subsetHash = sha256(toHash.encode()).hexdigest()

        await websocket.send(str(startingbit)+" "+str(endingbit))
        await websocket.send(subsetHash)
        
        #receive validation from client
        res = await websocket.recv()
        if int(res) == 0:
            break   #break QKD initialisation loop if authenticated
        else:
            print("[ALERT] Detected Eavesdropper on the Quantum Channel")
            # exit()
            return
            
    siftkey = siftkey[:128]
    sharedKey = int(siftkey, 2).to_bytes((len(siftkey) + 7) // 8, 'big')
      
    
    url = await websocket.recv()
    url = url.strip('/')
    username = await websocket.recv()
    print(f"Authenticated user {username} with shared key")  
    #print(f"key byte to hex server should receive = {bytes.hex(sharedKey)}")
    res = updateWebServer(url, bytes.hex(sharedKey), username)
    if res == 1:
        await websocket.send(str(res))
        raise Exception("Something unexpected happened to the web server, maybe it's down...?")
    else:
        await websocket.send(str(res))
        
def updateWebServer(serverURL, key, username):
    for i in range(1):
        print(f"[{i}] Updating quant key database...")
        data = {'quantkey': key, 'username': username}
        headers = {'Authorization': 'qkdadmin'}
        res = requests.post(serverURL+"/update", data=data, headers=headers)
        if res.status_code == 200:
            print("Successfully updated the server with the session quant key")
            return 0
    return 1

async def main():
    parser = parser = argparse.ArgumentParser()
    parser.add_argument("--intercept", action='store_true', help='Enables the interception of qubits by Eve between server & client')
    args = parser.parse_args()

    print("[ONLINE] QKD Server is up online")
    if args.intercept:
        print("[ONLINE] Interception mode on")
    ps = await serve(functools.partial(server, intercept=args.intercept), "localhost", 8765)
    await asyncio.get_running_loop().create_future()  # run forever
    await ps.wait_closed()
    
    
asyncio.run(main())