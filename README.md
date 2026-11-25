# DePIN Video Streaming Gateway

The gateway for a 2025 hackathon prototype that streams video from independently operated nodes. This FastAPI service receives uploads, stores content metadata and view records in SQLite, and registers available streams in Redis.

## Project components

| Repository | Role |
| --- | --- |
| Gateway | Accepts video uploads and provides the stream registry, catalog, and view-log API. |
| [depin_client](https://github.com/zephyranthes03/depin_client) | Fetches source video, transcodes it to HLS, and registers the stream with the gateway. |
| [front_depin_host](https://github.com/zephyranthes03/front_depin_host) | Provides creator, provider, and viewer workflows in the browser. |

## Local setup

The gateway expects Python 3.10 or later and Redis at `localhost:6379`. The upload paths use the IPFS or EthStorage CLI. Configure the variables in [env.sample](env.sample) in your local shell for the storage path you use.

~~~sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn gateway:app --host 127.0.0.1 --port 8000
~~~

Use the [generated API docs](http://127.0.0.1:8000/docs) for request and response schemas. The prototype includes service URLs from the original demo. Configure each component for your own local stack before testing the full flow.

## Gateway API

| Endpoint | Purpose |
| --- | --- |
| `POST /upload-content` | Upload video through IPFS and record its metadata. |
| `POST /upload-content-web3` | Upload through the EthStorage path. |
| `POST /register`, `POST /deregister` | Add or remove streaming nodes in the Redis registry. |
| `GET /meta/get_all_metadata` | List video metadata for the browser app. |
| `POST /api/record-view` | Store a view record in SQLite. |
| `GET /api/get-records/cid/{cid}` | Retrieve view records for one video. |

The separate [distribution script](distribute_script.py) reads view records and contains the prototype transaction-signing path. The local gateway setup above starts only the API.

## License

[MIT](LICENSE)
