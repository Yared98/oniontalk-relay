<div align="center">
  <img src="https://raw.githubusercontent.com/onion-talk/.github/main/assets/oniontalk-icon-512.png" alt="OnionTalk Logo" width="110" height="110" />
  <h1>OnionTalk Relay Node</h1>
  <p><strong>Zero-Knowledge Tor v3 Hidden Service Relay with Ed25519-Authenticated Peer Exchange (PEX) & Cryptographic ACK Preimage Lock</strong></p>

  <p>
    <a href="https://github.com/sponsors/eriktonon">
      <img src="https://img.shields.io/badge/Sponsor-OnionTalk-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub" />
    </a>
    <a href="#-sponsor--donate">
      <img src="https://img.shields.io/badge/Donate-BTC_%7C_ETH_%7C_SOL-F7931A?style=for-the-badge&logo=bitcoin&logoColor=white" alt="Donate Crypto" />
    </a>
  </p>
</div>

---

## 🎯 Overview

`oniontalk-relay` is the federated RAM-only store-and-forward node that powers the **OnionTalk** decentralized messaging mesh.

- **Works Behind CGNAT & Home Routers (Zero Open Clearnet Ports)**: Because the relay operates strictly as a **Tor v3 Hidden Service (`.onion`)** and binds its local inspection port solely to `127.0.0.1`, the container establishes outbound circuits into the Tor network. No port forwarding, static IP, or public DNS is required.
- **Zero-Knowledge RAM-Only Store-and-Forward**: The relay stores encrypted envelopes (`__ENC_X25519_CHACHA20_V2__`: `X25519 ECDH` + `HKDF-SHA256` + `ChaCha20-Poly1305 AEAD` + `Ed25519 Signature`) exclusively in volatile RAM (`ram-volatile-ephemeral-ttl24h`), requires `Ed25519` challenge signatures (`X-OnionTalk-Signature`) on `/inbox` and `/ack`, and purges envelopes upon verifying a 256-bit cryptographic preimage proof (`SHA-256(ack_token) == ack_lock`).
- **Authenticated Peer Discovery (Ed25519 Gossip PEX)**: On startup, the relay generates its `.onion` v3 hidden service and `Ed25519` node signing key (`node_pubkey`), announcing itself to the mesh bootstrap seeds and verifying peer keys over Tor (`/health`) before accepting gossip replication.

---

## 🚀 Quick Start (1 Command)

```bash
git clone https://github.com/onion-talk/oniontalk-relay.git
cd oniontalk-relay
docker compose up -d --build
```

### Check Your Relay `.onion` Identity & Mesh Health

```bash
curl http://127.0.0.1:8080/health
```

Example output once Tor circuits are established (30–90 seconds after first boot):

```json
{
  "status": "healthy",
  "zero_trust_mode": "X25519-ChaCha20-Poly1305 + Ed25519-Auth + ACK-Lock + Anti-Sybil",
  "storage_engine": "ram-volatile-ephemeral-ttl24h",
  "domain": "your_generated_56_character_ed25519_address.onion",
  "node_pubkey": "64_character_hex_ed25519_public_key",
  "peers_count": 5,
  "total_nodes": 6,
  "queued_messages": 0,
  "active_inboxes": 0,
  "messages_received": 42,
  "messages_routed": 168,
  "acks_processed": 42
}
```

### Inspect Connected Mesh Peers & Geo-Distribution

```bash
curl http://127.0.0.1:8080/api/v1/peers/list
```

---

## 📂 Repository Structure

```text
oniontalk-relay/
├── docker-compose.yml   # Orchestrates Tor v3 Hidden Service + Gunicorn Relay API (127.0.0.1 bind)
├── Dockerfile           # Pinned Python 3.12-slim-bookworm + Gunicorn container image
├── relay.py             # Zero-knowledge RAM routing engine, Ed25519 auth, PEX gossip & ACK lock
├── requirements.txt     # Pinned dependencies (Flask, Gunicorn, Requests[socks], Cryptography)
├── torrc                # Tor v3 HiddenServiceVersion 3 + SOCKS5h configuration
└── README.md            # Deployment and operations guide
```

---

## ⚙️ Optional Configuration

To change the localhost HTTP inspection port (default `127.0.0.1:8080`) without affecting Tor hidden service routing (which always uses virtual port `80` inside the `.onion` circuit):

```bash
RELAY_PORT=8090 docker compose up -d
```

> **Important**: Your node's Ed25519 `.onion` private key is persisted in the `tor_keys` Docker volume. Avoid running `docker compose down -v` unless you intentionally want to rotate your `.onion` address.

---

## 💖 Sponsor & Donate

Help us keep independent Tor v3 bootstrap relays running across multiple global jurisdictions:

- **GitHub Sponsors**: [github.com/sponsors/eriktonon](https://github.com/sponsors/eriktonon)
- **Bitcoin (BTC)**: `bc1q0hr95ay33rtazfepg64yddf52q3yqh7ud83cza`
- **Ethereum (ETH / ERC-20)**: `0xE69FCE4Fa35CF3bd98F496337b1eA223270b2c92`
- **Solana (SOL)**: `3E8L1Hdqe7Xk6GCrzHbtY5sReAfLFc9CdwgZxP7qaoHq`
