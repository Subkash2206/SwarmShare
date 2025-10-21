# SwarmShare: A Resilient P2P File Sharing Application

![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

SwarmShare is a sophisticated peer-to-peer (P2P) file sharing application built from the ground up in Python. It demonstrates a robust, multi-threaded architecture that allows peers to efficiently and securely transfer files directly between each other. The system is designed for performance and reliability, featuring parallel chunk-based downloads with SHA-256 integrity verification and the ability to resume interrupted transfers.

---

##  Core Features

This project is more than a simple file transfer script; it's a complete protocol implementation with modern features:

* **Tracker-based P2P Architecture:** A central tracker facilitates peer discovery, but all file transfers occur directly between peers, distributing the network load.
* **File Chunking & Parallel Downloads:** Large files are broken into 1MB chunks. A multi-threaded download manager downloads multiple chunks in parallel from the network swarm, maximizing transfer speed.
* **SHA-256 Hash Verification:** Every chunk is verified against a SHA-256 hash upon download. A final integrity check is performed on the fully reassembled file to guarantee it is free of corruption.
* **Resumable Downloads:** Download progress is saved to a local file. If a transfer is interrupted, the application can resume exactly where it left off, only downloading the missing chunks.
* **Custom Networking Protocol:** The application uses a custom, JSON-based protocol for all communication between the tracker and peers.
* **Concurrent & Thread-Safe:** The application is built to handle multiple simultaneous uploads and downloads safely using Python's `threading` module and locks.

---

##  System Architecture

The system uses a hybrid P2P topology. The tracker maintains the state of the network (which peers have which file chunks), while the peers form a mesh for the actual data transfer.

---

##  Setup & Usage

To run this project locally, follow these steps.

### Prerequisites

* Python 3.9 or higher
* pip package manager

### Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Subkash2206/SwarmShare.git](https://github.com/Subkash2206/SwarmShare.git)
    cd SwarmShare
    ```

2.  **Install dependencies:**
    The project requires the `cryptography` library for its (optional) encryption layer.
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

1.  **Start the Tracker:**
    The tracker must be running before any peers can connect. Open a terminal and run:
    ```bash
    python tracker.py
    ```

2.  **Start the Peers:**
    For each peer, open a **new terminal**. You must provide a unique port for each peer to listen on.

    * **Terminal 2 (Peer 1):**
        ```bash
        # Make sure this peer has a file in its 'shared/' directory
        python peer.py 9999
        ```

    * **Terminal 3 (Peer 2):**
        ```bash
        python peer.py 9998
        ```

3.  **Use the Application:**
    Follow the on-screen menu in any peer terminal to search for and download files from the network.

---

##  License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
