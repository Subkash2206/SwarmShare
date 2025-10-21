# peer.py (Phase 4.6: Final Fix)
import socket
import threading
import json
import os
import sys
import hashlib
import time
import shutil
from queue import Queue

# --- Configuration & Utilities (NO CHANGES HERE) ---
TRACKER_ADDR = ('127.0.0.1', 8888)
if len(sys.argv) < 2:
    print("Usage: python peer.py <port>")
    sys.exit(1)
PEER_SERVER_PORT = int(sys.argv[1])
SHARED_FOLDER = 'shared'
CHUNK_SIZE = 1024 * 1024


def get_file_chunks(filepath):
    chunk_hashes = []
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk: break
            chunk_hashes.append(hashlib.sha256(chunk).hexdigest())
    return chunk_hashes


def read_chunk(filepath, chunk_index):
    with open(filepath, 'rb') as f:
        f.seek(chunk_index * CHUNK_SIZE)
        return f.read(CHUNK_SIZE)


# --- Peer Server (NO CHANGES HERE) ---
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
        request_data = conn.recv(1024)
        request = json.loads(request_data.decode())
        filepath = os.path.join(SHARED_FOLDER, request["filename"])
        if os.path.exists(filepath):
            chunk_data = read_chunk(filepath, request["chunk_index"])
            conn.sendall(chunk_data)
    except Exception as e:
        print(f"Error during upload: {e}")
    finally:
        conn.close()


# --- Peer Client (NO CHANGES HERE) ---
def talk_to_tracker(payload):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(TRACKER_ADDR)
        my_address = f"{socket.gethostbyname(socket.gethostname())}:{PEER_SERVER_PORT}"
        payload["address"] = my_address
        s.sendall(json.dumps(payload).encode())
        response_data = s.recv(4096)
        return json.loads(response_data.decode())


### --- FIXED DownloadManager --- ###
class DownloadManager:
    # We now pass our own address to prevent self-downloading
    def __init__(self, filename, file_info, my_address):
        self.filename = filename
        self.filesize = file_info["filesize"]
        self.chunk_hashes = file_info["chunks"]
        self.peers = file_info["peers"]
        self.num_chunks = len(self.chunk_hashes)
        self.my_address = my_address  ### NEW ### Store our own address

        self.temp_dir = os.path.join(SHARED_FOLDER, f"{self.filename}.tmp")
        self.progress_file = os.path.join(self.temp_dir, "progress.json")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.downloaded_chunk_indices = self.load_progress()
        self.chunks_to_download = Queue()
        for i in range(self.num_chunks):
            if i not in self.downloaded_chunk_indices:
                self.chunks_to_download.put(i)
        self.lock = threading.Lock()

    def load_progress(self):
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    progress = json.load(f)
                    if progress.get("chunk_hashes") == self.chunk_hashes:
                        print(f"[*] Resuming download for '{self.filename}'.")
                        return set(progress.get("downloaded_indices", []))
            except (IOError, json.JSONDecodeError):
                print("Could not read progress file. Starting fresh.")
        initial_progress = {"filesize": self.filesize, "chunk_hashes": self.chunk_hashes, "downloaded_indices": []}
        with open(self.progress_file, 'w') as f:
            json.dump(initial_progress, f)
        return set()

    def save_progress(self):
        progress = {"filesize": self.filesize, "chunk_hashes": self.chunk_hashes,
                    "downloaded_indices": list(self.downloaded_chunk_indices)}
        temp_filepath = self.progress_file + ".tmp"
        with open(temp_filepath, 'w') as f:
            json.dump(progress, f)
        os.replace(temp_filepath, self.progress_file)

    def download_worker(self):
        while not self.chunks_to_download.empty():
            try:
                chunk_index = self.chunks_to_download.get_nowait()
            except:
                return

            peer_address = self.find_peer_for_chunk(chunk_index)
            if not peer_address:
                time.sleep(1)  # Wait a moment for peers to update
                continue

            chunk_data = self.download_chunk_from_peer(peer_address, chunk_index)

            if chunk_data and hashlib.sha256(chunk_data).hexdigest() == self.chunk_hashes[chunk_index]:
                chunk_filepath = os.path.join(self.temp_dir, f"chunk_{chunk_index}")
                with open(chunk_filepath, 'wb') as f:
                    f.write(chunk_data)

                with self.lock:
                    self.downloaded_chunk_indices.add(chunk_index)
                    self.save_progress()
                    progress_percentage = (len(self.downloaded_chunk_indices) / self.num_chunks) * 100
                    print(f"Downloaded chunk {chunk_index + 1}/{self.num_chunks}. Progress: {progress_percentage:.2f}%")

                talk_to_tracker({"command": "update", "filename": self.filename, "chunk_index": chunk_index})
            else:
                ### FIX ### Don't re-queue a failed chunk, just let the worker move on.
                # This prevents the infinite loop. The download will be marked as incomplete
                # and can be retried by the user later.
                print(f"Chunk {chunk_index} download failed from peer {peer_address}.")

    def find_peer_for_chunk(self, chunk_index):
        for peer, chunks in self.peers.items():
            ### FIX ### Don't try to download from yourself!
            if peer == self.my_address:
                continue
            if chunk_index in chunks:
                return peer
        return None

    def download_chunk_from_peer(self, peer_address, chunk_index):
        # This function is unchanged
        host, port_str = peer_address.split(':')
        port = int(port_str)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((host, port))
                request = {"filename": self.filename, "chunk_index": chunk_index}
                s.sendall(json.dumps(request).encode())

                data = b""
                s.settimeout(10)
                # This logic is complex to handle the last chunk being smaller
                expected_size = CHUNK_SIZE if chunk_index < self.num_chunks - 1 else self.filesize % CHUNK_SIZE or CHUNK_SIZE
                while len(data) < expected_size:
                    packet = s.recv(expected_size - len(data))
                    if not packet:
                        return None
                    data += packet
                return data
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            # print(f"Error connecting to peer {peer_address}: {e}") # This can be noisy
            return None

    def start(self):
        # This function is unchanged
        print(
            f"[*] Starting download for '{self.filename}'. {len(self.downloaded_chunk_indices)} of {self.num_chunks} chunks already downloaded.")
        threads = []
        num_workers = min(10, self.chunks_to_download.qsize())
        if num_workers == 0 and len(self.downloaded_chunk_indices) < self.num_chunks:
            print("No chunks to download, but file is incomplete. Are peers available?")
            return

        for _ in range(num_workers):
            t = threading.Thread(target=self.download_worker)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if len(self.downloaded_chunk_indices) == self.num_chunks:
            self.assemble_file()
        else:
            print(
                f"\nDownload did not complete. {len(self.downloaded_chunk_indices)}/{self.num_chunks} chunks downloaded. Run again to resume.")

    def assemble_file(self):
        # This function is unchanged
        print("[*] Assembling final file...")
        output_path = os.path.join(SHARED_FOLDER, self.filename)
        try:
            with open(output_path, 'wb') as final_file:
                for i in range(self.num_chunks):
                    chunk_path = os.path.join(self.temp_dir, f"chunk_{i}")
                    with open(chunk_path, 'rb') as chunk_file:
                        final_file.write(chunk_file.read())

            print(f"[*] File assembly complete! Saved as {output_path}")

            final_hashes = get_file_chunks(output_path)
            if final_hashes == self.chunk_hashes:
                print("✅ Final file integrity check PASSED.")
                shutil.rmtree(self.temp_dir)
                print("[*] Temporary files cleaned up.")
            else:
                print("❌ Final file integrity check FAILED. File may be corrupt.")
        except IOError as e:
            print(f"Error assembling file: {e}")


### --- MODIFIED main() function --- ###
def main():
    if not os.path.exists(SHARED_FOLDER):
        os.makedirs(SHARED_FOLDER)

    server_thread = threading.Thread(target=peer_server_logic, daemon=True)
    server_thread.start()

    try:
        files_to_share = [f for f in os.listdir(SHARED_FOLDER) if os.path.isfile(os.path.join(SHARED_FOLDER, f))]
        for filename in files_to_share:
            filepath = os.path.join(SHARED_FOLDER, filename)
            filesize = os.path.getsize(filepath)
            chunks = get_file_chunks(filepath)
            payload = {"command": "share", "filename": filename, "filesize": filesize, "chunks": chunks}
            talk_to_tracker(payload)
    except ConnectionRefusedError:
        print("[ERROR] Could not connect to the tracker. Is it running?")
        sys.exit(1)

    while True:
        print("\n--- P2P File Sharing Client (Fixed) ---")
        print("1. Download a file")
        print("2. Exit")
        choice = input("> ")

        if choice == "1":
            filename = input("Enter filename to download: ")
            file_info = talk_to_tracker({"command": "get", "filename": filename})
            if file_info.get("error"):
                print(f"Error from tracker: {file_info['error']}")
                continue

            ### FIX ### Pass our own address to the manager
            my_address = f"{socket.gethostbyname(socket.gethostname())}:{PEER_SERVER_PORT}"
            manager = DownloadManager(filename, file_info, my_address)
            manager.start()
        elif choice == "2":
            break


if __name__ == "__main__":
    main()