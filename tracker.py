# tracker.py (Phase 4: Hashing and Chunking)
import socket
import threading
import json

# New Database Structure:
# {
#   "filename": {
#     "filesize": 10240,
#     "chunks": ["hash1", "hash2", ...],
#     "peers": {
#       "peer_addr1": [0, 1, 2, ...], # List of chunk indices this peer has
#       "peer_addr2": [0, 1, 2, ...]
#     }
#   }
# }
file_db = {}
db_lock = threading.Lock()


def handle_peer_connection(conn, addr):
    print(f"[TRACKER] Accepted connection from {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            request = json.loads(data.decode())
            command = request.get("command")

            with db_lock:
                if command == "share":
                    filename = request.get("filename")
                    filesize = request.get("filesize")
                    chunks = request.get("chunks")
                    peer_address = request.get("address")

                    if filename not in file_db:
                        file_db[filename] = {
                            "filesize": filesize,
                            "chunks": chunks,
                            "peers": {}
                        }
                    # Announce that this peer has all chunks
                    file_db[filename]["peers"][peer_address] = list(range(len(chunks)))

                    response = {"status": "success", "message": f"'{filename}' is now shared."}
                    conn.sendall(json.dumps(response).encode())
                    print(f"[TRACKER] Peer {peer_address} shared {filename}")

                elif command == "get":
                    filename = request.get("filename")
                    file_info = file_db.get(filename)
                    if file_info:
                        conn.sendall(json.dumps(file_info).encode())
                        print(f"[TRACKER] Sent info for '{filename}'")
                    else:
                        conn.sendall(json.dumps({"error": "File not found"}).encode())

                elif command == "update":
                    # When a peer downloads a new chunk, they tell the tracker
                    filename = request.get("filename")
                    chunk_index = request.get("chunk_index")
                    peer_address = request.get("address")
                    if filename in file_db and peer_address in file_db[filename]["peers"]:
                        if chunk_index not in file_db[filename]["peers"][peer_address]:
                            file_db[filename]["peers"][peer_address].append(chunk_index)
                        conn.sendall(json.dumps({"status": "success"}).encode())

    except Exception as e:
        print(f"[TRACKER] Error with {addr}: {e}")
    finally:
        # A more robust tracker would remove the peer from the DB on disconnect
        print(f"[TRACKER] Connection from {addr} closed.")
        conn.close()


def main():
    HOST = '127.0.0.1'
    PORT = 8888

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[*] Tracker server listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_peer_connection, args=(conn, addr))
        thread.start()


if __name__ == "__main__":
    main()