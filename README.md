# PeerStor

Single-file Python file server with a browser UI. Phase 1 (MVP) ships as a single script using Python stdlib only — no pip installs.

- **Zero setup**: `python peerStor/peerstor.py`
- **Web UI**: Directory listing + upload form
- **Resumable downloads**: HTTP Range support
- **Resumable uploads**: Built-in chunked API + JS button
- **Auto port fallback**: Finds a free port if 8080 is busy
- **Local IP hint**: Prints `Access at: http://<ip>:<port>`

> Safety note: MVP has no auth. Use only on trusted networks or behind a reverse proxy with auth.

## Requirements
- Python 3.8+
- Works on Windows, macOS, Linux

## Run
```bash
python peerStor/peerstor.py              # bind 0.0.0.0:8080 (auto-increment if busy)
python peerStor/peerstor.py --port 9000  # custom port
python peerStor/peerstor.py --host 127.0.0.1  # local only
python peerStor/peerstor.py --storage ./mydata  # custom storage directory
python peerStor/peerstor.py --no-gzip    # disable gzip compression for downloads
python peerStor/peerstor.py --gzip-threshold 2097152  # compress files <= 2 MiB
```

On start, you'll see something like:
```
Access at: http://192.168.1.42:8080
```
Open the URL in your browser to upload/download files.

## Features (MVP)
- Directory listing with breadcrumbs
- Upload via browser (multipart/form-data)
- Upload via browser (resumable, chunked)
- Download with HTTP Range (resume/seek)
- Optional gzip compression for text/JSON (client Accept-Encoding dependent)
- Strict path sandboxing to the storage directory
- Light CORS headers for GET/HEAD/OPTIONS

## Resumable uploads (API)
- GET `/api/upload/offset?dir=/path&name=<filename>` → `{ "offset": <int> }`
- POST `/api/upload/chunk?dir=/path&name=<filename>&offset=<int>` with raw body bytes → `{ "nextOffset": <int> }`
- POST `/api/upload/complete?dir=/path&name=<filename>&size=<int>` → `{ "status": "ok" }`

UI: Select a file and click "Upload (resumable)". The client retries/resumes automatically using the API.

## Project Structure
```
peerStor/
  peerstor.py   # the entire app (MVP)
  data/         # created automatically on first run (default storage)
```

## Roadmap (Phases)
- Phase 1: MVP (this) — listing, upload, range downloads
- Phase 2: Resumable uploads; compression on-the-fly; simple token auth; basic UI polish
- Phase 3: Chunking + replication across peers; discovery (mDNS/zeroconf)
- Phase 4: Dashboard, quotas, search/indexing
- Phase 5: Performance & robustness (delta sync, caching)

## Notes
- Windows may prompt for firewall permission on first run.
- Avoid exposing directly to the internet without authentication.

## License
MIT — see LICENSE.
