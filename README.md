# PeerStor

Single-file Python file server with a browser UI. Phase 1 (MVP) ships as a single script using Python stdlib only — no pip installs.

- **Zero setup**: `python peerStor/peerstor.py`
- **Web UI**: Directory listing + upload form
- **Resumable downloads**: HTTP Range support
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
```

On start, you'll see something like:
```
Access at: http://192.168.1.42:8080
```
Open the URL in your browser to upload/download files.

## Features (MVP)
- Directory listing with breadcrumbs
- Upload via browser (multipart/form-data)
- Download with HTTP Range (resume/seek)
- Strict path sandboxing to the storage directory
- Light CORS headers for GET/HEAD/OPTIONS

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
