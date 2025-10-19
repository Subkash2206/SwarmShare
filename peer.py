# peer.py (Phase 4: Hashing and Chunking)
import socket
import threading
import json
import os
import sys
import hashlib
import time
from queue import Queue

# --- Configuration ---
TRACKER_ADDR = ('127.0.0.1', 8888)
if len(sys.argv) < 2:
    print("Usage: python peer.py <port>")
    sys.exit(1)
PEER_SERVER_PORT = int(sys.argv[1])
SHARED_FOLDER = 'shared'
CHUNK_SIZE = 1024 * 1024  # 1 MB chunks


# --- Hashing and Chunking Utilities ---
def get_file_chunks(filepath):
    """Breaks a file into chunks and returns their SHA-256 hashes."""
    chunk_hashes = []
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            chunk_hashes.append(hashlib.sha256(chunk).hexdigest())
    return chunk_hashes


def read_chunk(filepath, chunk_index):
    """Reads a specific chunk from a file."""
    with open(filepath, 'rb') as f:
        f.seek(chunk_index * CHUNK_SIZE)
        return f.read(CHUNK_SIZE)


# --- Peer Server (Handles Uploads) ---
def peer_server_logic():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('', PEER_SERVER_PORT))
    server_socket.listen(5)
    print(f"[*] Peer server listening on port {PEER_SERVER_PORT}")
    while True:
        client_socket, addr = server_socket.accept()
        threading.Thread(target=handle_upload, args=(client_socket,)).start()


def handle_upload(conn):
    try:
        # Request format: {"filename": "str", "chunk_index": int}
        request_data = conn.recv(1024)
        request = json.loads(request_data.decode())
        filepath = os.path.join(SHARED_FOLDER, request["filename"])

        if os.path.exists(filepath):
            chunk_data = read_chunk(filepath, request["chunk_index"])
            conn.sendall(chunk_data)
        else:
            print(f"Upload request for non-existent file: {request['filename']}")
    except Exception as e:
        print(f"Error during upload: {e}")
    finally:
        conn.close()


# --- Peer Client (Handles User Interaction & Downloads) ---
def talk_to_tracker(payload):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(TRACKER_ADDR)
        my_address = f"{socket.gethostbyname(socket.gethostname())}:{PEER_SERVER_PORT}"
        payload["address"] = my_address
        s.sendall(json.dumps(payload).encode())
        response_data = s.recv(4096)  # Increased buffer for potentially large peer lists
        return json.loads(response_data.decode())


class DownloadManager:
    def __init__(self, filename, file_info):
        self.filename = filename
        self.filesize = file_info["filesize"]
        self.chunk_hashes = file_info["chunks"]
        self.peers = file_info["peers"]
        self.num_chunks = len(self.chunk_hashes)
        self.downloaded_chunks = [None] * self.num_chunks
        self.chunks_to_download = Queue()
        for i in range(self.num_chunks):
            self.chunks_to_download.put(i)
        self.lock = threading.Lock()

    def download_worker(self):
        while not self.chunks_to_download.empty():
            try:
                chunk_index = self.chunks_to_download.get_nowait()
            except:
                return  # Queue is empty

            # Find a peer who has this chunk
            peer_address = self.find_peer_for_chunk(chunk_index)
            if not peer_address:
                print(f"No peer found for chunk {chunk_index}, requeueing.")
                self.chunks_to_download.put(chunk_index)  # Re-add to queue
                time.sleep(1)
                continue

            # Download the chunk
            chunk_data = self.download_chunk_from_peer(peer_address, chunk_index)

            if chunk_data and hashlib.sha256(chunk_data).hexdigest() == self.chunk_hashes[chunk_index]:
                with self.lock:
                    self.downloaded_chunks[chunk_index] = chunk_data
                    print(f"Downloaded chunk {chunk_index + 1}/{self.num_chunks} successfully.")
                # Tell the tracker we now have this chunk
                talk_to_tracker({"command": "update", "filename": self.filename, "chunk_index": chunk_index})
            else:
                print(f"Chunk {chunk_index} download failed or hash mismatch. Requeueing.")
                self.chunks_to_download.put(chunk_index)

    def find_peer_for_chunk(self, chunk_index):
        # Simple strategy: just find the first peer that has the chunk
        for peer, chunks in self.peers.items():
            if chunk_index in chunks:
                return peer
        return None

    def download_chunk_from_peer(self, peer_address, chunk_index):
        host, port_str = peer_address.split(':')
        port = int(port_str)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
                request = {"filename": self.filename, "chunk_index": chunk_index}
                s.sendall(json.dumps(request).encode())

                # Read data for one full chunk
                data = b""
                while len(data) < CHUNK_SIZE:
                    packet = s.recv(CHUNK_SIZE - len(data))
                    if not packet:
                        break
                    data += packet
                return data
        except Exception as e:
            print(f"Error connecting to peer {peer_address}: {e}")
            return None

    def start(self):
        # Use multiple threads to download chunks in parallel
        threads = []
        num_workers = min(10, self.chunks_to_download.qsize())  # Cap at 10 workers
        for _ in range(num_workers):
            t = threading.Thread(target=self.download_worker)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()  # Wait for all workers to finish

        # Assemble the file
        if all(c is not None for c in self.downloaded_chunks):
            output_path = os.path.join(SHARED_FOLDER, f"received_{self.filename}")
            with open(output_path, 'wb') as f:
                for chunk in self.downloaded_chunks:
                    f.write(chunk)
            print(f"\nFile download complete! Saved as {output_path}")

            # Final integrity check on the full file
            final_hashes = get_file_chunks(output_path)
            if final_hashes == self.chunk_hashes:
                print("Final file integrity check PASSED.")
            else:
                print("Final file integrity check FAILED. File may be corrupt.")
        else:
            print("Download failed. Some chunks were not downloaded.")


def main():
    if not os.path.exists(SHARED_FOLDER):
        os.makedirs(SHARED_FOLDER)

    server_thread = threading.Thread(target=peer_server_logic, daemon=True)
    server_thread.start()

    # Share local files with the tracker
    for filename in os.listdir(SHARED_FOLDER):
        filepath = os.path.join(SHARED_FOLDER, filename)
        if os.path.isfile(filepath):
            filesize = os.path.getsize(filepath)
            chunks = get_file_chunks(filepath)
            payload = {
                "command": "share", "filename": filename,
                "filesize": filesize, "chunks": chunks
            }
            talk_to_tracker(payload)

    # --- Main User Interface Loop ---
    while True:
        print("\n--- P2P File Sharing (Chunked & Hashed) ---")
        print("1. Download a file")
        print("2. Exit")
        choice = input("> ")

        if choice == "1":
            filename = input("Enter filename to download: ")
            file_info = talk_to_tracker({"command": "get", "filename": filename})
            if file_info.get("error"):
                print(f"Error from tracker: {file_info['error']}")
                continue

            manager = DownloadManager(filename, file_info)
            manager.start()
        elif choice == "2":
            break


if __name__ == "__main__":
    main()