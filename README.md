# Web3 Video Streaming Service - Host

A decentralized video streaming service built on Web3 and Ethereum blockchain. This project allows users to upload videos to IPFS/EthStorage, register and deregister video streams, record view histories, and distribute earnings between content creators and providers. The frontend is built with **Next.js** and **ethers.js**, and the backend is powered by **FastAPI** and **Web3.py**.

## Features
- Upload videos to **EthStorage(IPFS)** and get a CID.
- Register and deregister video streams with metadata.
- Record view histories with blockchain transactions.
- (DePIN) Distribute earnings between creators and providers using Ethereum.

---

## Installation

## Prerequisites
- **Python 3.10+**
- **IPFS** and **EthStorage CLI** installed
- **Redis** for caching
- **SQLite** for metadata and logs

## Setup

1. Clone the repository:
```
bash
git clone https://github.com/yourusername/web3-video-streaming.git
cd web3-video-streaming
```

2. Create a virtual environment
```
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install Python dependencies
```
pip install -r requirements.txt
```

4. Set up environment variables : Create `.env` reference by `env.sample`

5. Start Redis server
```
docker run --name redis -p 6379:6379 -v /your/local/path:/data -d redis redis-server --appendonly yes

```

6. Start the FastAPI server
```
uvicorn gateway:app --reload --host 0.0.0.0 --port 8000

```

## Database Schema

SQLite Tables:

content_metadata: Stores video metadata.

cid, video_name, content_creator_wallet, creator_share, provider_share, price.
streaming_access_logs: Stores view history.

cid, blockchain_address, provider_wallet, creator_wallet, price, timestamp.


## RestAPI document
```
http://localhost:8000/docs
```


## API Documentation

1. Upload Content to IPFS
Endpoint: /upload-content
Method: POST
Description: Uploads video and saves metadata to IPFS and SQLite.

# Example Request:

```
curl -X POST "http://localhost:8000/upload-content" \
-H "Content-Type: multipart/form-data" \
-F "file=@./data/video.mp4" \
-F 'json_data={"video_name": "Sample Video", "content_creator_wallet": "0x1234", "creator_share": 70, "provider_share": 30, "price": 0.001}'

2. Register Video Stream
Endpoint: /register
Method: POST
Description: Registers a video stream to Redis.
```

# Payload Example:

```
{
  "cid": "0x1234...",
  "stream_url": "http://localhost:9000/stream",
  "video_name": "Sample Video",
  "content_creator_wallet": "0xCreator...",
  "content_distributor_wallet": "0xDistributor...",
  "creator_share": 70,
  "provider_share": 30,
  "price": 0.001
}
```

3. Deregister Video Stream
Endpoint: /deregister
Method: POST
Description: Removes a video stream from Redis.

# Payload Example:

```
{
  "cid": "0x1234...",
  "content_distributor_wallet": "0xDistributor..."
}
```

4. Record View History
Endpoint: /api/record-view
Method: POST
Description: Records a view log in SQLite.

Payload Example:
```
{
  "cid": "0x1234...",
  "blockchain_address": "0xViewer...",
  "provider_wallet": "0xProvider...",
  "creator_wallet": "0xCreator...",
  "price": "0.001",
  "timestamp": "2023-07-31T12:00:00Z"
}
```

5. Get View History by CID
Endpoint: /api/get-records/cid/{cid}
Method: GET
Description: Retrieves view history for a specific CID.

💸 Earnings Distribution
Script: distribute_earnings.py
Description: Fetches view logs and distributes earnings between creator and provider based on the share ratio.

# Run the script:

```
python distribute_earnings.py
```

## Development Notes
Ensure MetaMask is connected to the Sepolia test network.
Customize ethers interactions in the frontend for real deployments.


## License
This project is licensed under the MIT License. See the LICENSE file for details.

## Contributing
Fork the repo.
Create your feature branch (git checkout -b feature/AmazingFeature).
Commit your changes (git commit -m 'Add some AmazingFeature').
Push to the branch (git push origin feature/AmazingFeature).
Open a Pull Request.

## Troubleshooting
CORS Error: Ensure FastAPI CORS settings match your frontend URL.
RPC Connection Error: Check .env for correct ETH_RPC_URL and PRIVATEKEY.
Missing Packages: Run pip install -r requirements.txt and npm install in respective directories.
For further assistance, open an issue on GitHub. 👍

## Contact
Email: zephyranthes032@gmail.com
GitHub: github.com/zephyranthes03
