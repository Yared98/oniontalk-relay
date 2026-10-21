<div align="center">
  <img src="https://raw.githubusercontent.com/onion-talk/.github/main/assets/oniontalk-icon-512.png" alt="OnionTalk Logo" width="110" height="110" />
  <h1>OnionTalk Relay Node</h1>
  <p><strong>Zero-Knowledge Tor v3 Hidden Service Relay with Ed25519-Authenticated Peer Exchange (PEX) & Cryptographic ACK Preimage Lock</strong></p>

  <p>
    <a href="https://play.google.com/store/apps/details?id=org.oniontalk.messenger">
      <img src="https://img.shields.io/badge/Google_Play-OnionTalk_–_Apps_no_Google_Play-3DDC84?style=for-the-badge&logo=google-play&logoColor=black" alt="OnionTalk – Apps no Google Play" />
    </a>
    <a href="https://github.com/sponsors/eriktonon">
      <img src="https://img.shields.io/badge/Sponsor-OnionTalk-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub" />
    </a>
    <a href="#-sponsor--donate">
      <img src="https://img.shields.io/badge/Donate-BTC_%7C_ETH_%7C_SOL-F7931A?style=for-the-badge&logo=bitcoin&logoColor=white" alt="Donate Crypto" />
    </a>
  </p>
</div>

---

## 🚀 What's New in `v1.4.0` (`versionCode = 14`) — 17-Node Global Mesh (8 Countries), Selective `FLAG_SECURE`, Instant Tor Auto-Heal & GZIP File Transfers

- **📦 Direct Signed APK Downloads (`v1.4.0`)**:
  - **Main Messenger APK (`org.oniontalk.messenger`)**: [**Download `OnionTalk-v1.4.0.apk`**](https://github.com/onion-talk/oniontalk-demo/releases/download/v1.4.0-demo/OnionTalk-v1.4.0.apk) (`SHA-256: d11ee5629b6bffa32658d80e2d22cd5582e37c84d3b69bd85dffc424793688c4`)
  - **Standalone Android Relay Node APK (`org.oniontalk.relaynode`)**: [**Download `OnionTalk-RelayNode-v1.4.0.apk`**](https://github.com/onion-talk/oniontalk-demo/releases/download/v1.4.0-demo/OnionTalk-RelayNode-v1.4.0.apk) (`SHA-256: c5d76730a1046bf76e5df518b53be8aecc053690e3ff31e68a14bbc8e282849f`)
- **🌐 17 Active Tor v3 Relays Across 8 Countries (`BR`, `US`, `FR`, `DE`, `RU`, `SG`, `JP`, `CN`)**:
  - Added **Node 16 (DOM Cloud Nuremberg, Germany)**: `o5zqqfl5znzexdojfnxgub5jnjelxdahbyxasjp57sx6fbxtjeqovpad.onion`
  - Added **Node 17 (ModelScope Cloud Hangzhou, China — GFW Bypass)**: `2amizuhb3p5x2lk3sra7f7thm5tgs7qtnysgowqpmexcqi4cuwyv7vad.onion`
  - Added **Zero-Touch Auto-Join & Auto-Geolocation** so any Docker or Android Relay Node joins the mesh in `<15s`.
- **🛡️ Selective `FLAG_SECURE` by Route**:
  - Enforces `WindowManager.LayoutParams.FLAG_SECURE` **100% of the time** on **Conversations (`CHAT_DETAIL`)**, **Active Chats (`CHAT_LIST`)**, and **Contacts Library (`CONTACTS_LIBRARY`)**, while dynamically allowing screenshots on **Settings / QR Code (`SETTINGS`)** for frictionless identity sharing.
- **⚡ 2-Hour Large-Scale Soak & Chaos Engineering Certification (`23:50–01:50`, 60 Waves, 3 Android 15 Emulators)**:
  - **0 crashes, 0 ANRs, 0 frozen process warnings** (`PSS: 62.5 MB – 94.9 MB`).
  - **Online P2P Delivery Latency**: `p50 = 1,147.1 ms` (`1.15s`), `p95 = 5,039.5 ms`.
  - **Encrypted File Transfers (`16 KB`–`256 KB`)**: `15/15` (`100%`) delivered with transparent **GZIP pre-compression (`gz=true`)** and adaptive read timeouts (`25s`).
  - **Bilateral Anti-Forensic Burn (`__CTRL_BURN_V1__`)**: `15/15` (`100%`) confirmed in `p50 = 1,846.5 ms`.
  - **Instant Network Auto-Recovery (`ConnectivityManager.NetworkCallback`)**: Foreground & background `NetworkCallback` + `3.5s` partial wake-lock on incoming batches recovers offline backlogs in `700.8 ms – 849.9 ms`.
- **🎨 Visual Privacy & UI Polish**:
  - Added **Blur / Unblur Contact Photo** (`blurAvatarBitmap`) per contact, removed bubble reply clutter and header shield icon, and placed the `✅ Atualizado` confirmation directly inside the Tor Status card.

| # | Country / Region | Tor v3 Hidden Service Address (`.onion`) | Role |
| :-: | :--- | :--- | :--- |
| 1 | 🇧🇷 Brazil (São Paulo #1) | `onion4zr3bsdeaelksemwokl5qmxd5o7jyblf46vc2mfl6cozgw77tqd.onion` | Master Vanity Seed (PVE2) |
| 2 | 🇧🇷 Brazil (São Paulo #2) | `kn4u2xxl2otoo2ujv3mhehwfwbw7mtppaf56fu3nxogvv7eekf2qdrid.onion` | Homelab Core Seed (PVE4) |
| 3 | 🇺🇸 USA (US-East) | `puqjsmsyyzmxjdtcgr2fl4wrdazqd2phaqrz26alzwyletbvekkxhyyd.onion` | AWS EKS Relay |
| 4 | 🇧🇷 Brazil (Vinhedo) | `zqdx5x7pfybox7m5rz3fe5kiouxhipvh3ekuteq2urrrvwcxjttnmgid.onion` | Oracle Cloud OCI Relay |
| 5 | 🇺🇸 USA (Virginia) | `ch4s5llfqshxbvba2yulgp5kbopq25w3qqrtli67sle6smbujlebn2id.onion` | AWS Virginia Relay |
| 6 | 🇫🇷 France (Paris #1) | `7bntuiegd3stvcylvx7rhnhq7ncasxiokunbf5onvvm34dg5gccvooid.onion` | Alwaysdata EU Relay #1 |
| 7 | 🇺🇸 USA (South Carolina) | `jz6urt6ckkqqvtasm6bll2mryhksjcawcl4tbguif5nqvxgsfsx6ywad.onion` | Google Cloud US-East Relay |
| 8 | 🇺🇸 USA (Ohio) | `4wufywh2k6ayyz6nmh2w25hj5vjsqgkve24o2tthvc7rhyvxnhaghqqd.onion` | Render Cloud Ohio Relay |
| 9 | 🇷🇺 Russia (Moscow) | `nwsoa6ddtbbqbwcceanhhj3j23d5a47zbpbs6zspz5zoeytzqpzvkqqd.onion` | Amvera Cloud Eurasia Relay |
| 10 | 🇺🇸 USA (US-East) | `bk7iegv3v232ycjyf5ylwsdx42iozvy2dhhff5zn3ciwa3g2lkifdlad.onion` | Back4App Container Relay |
| 11 | 🇫🇷 France (Paris #2) | `hdjp7uaj4qemlmwtev7xmj2w3uexnv6ctplfgvbmpqxenbfgwjjwtrid.onion` | Alwaysdata EU Relay #2 |
| 12 | 🇫🇷 France (Paris #3) | `gcvfh67zltoyvithw6luetsrcec6cw42upzrsprxfmx27cvh7vidw4yd.onion` | Alwaysdata EU Relay #3 |
| 13 | 🇺🇸 USA (Iowa, US-Central) | `wfi3nwuzk2tgrsf2scdy4nb6x6rtiocit4n26477zdlvdvshkgip3ayd.onion` | Northflank US-Central Relay |
| 14 | 🇯🇵 Japan (Osaka) | `5s6w6556f2eov2p6wlsuavaxh7si2kaswjwi5reojnovbzemducjzjqd.onion` | DOM Cloud Asia-Pacific East |
| 15 | 🇸🇬 Singapore | `o5yf3eukrwpt2g6jfo4q2y23xtuhoso2qknmnn6ac5eng5t4yt36roqd.onion` | DOM Cloud Southeast Asia Hub |
| 16 | 🇩🇪 Germany (Nuremberg) | `o5zqqfl5znzexdojfnxgub5jnjelxdahbyxasjp57sx6fbxtjeqovpad.onion` | DOM Cloud Central Europe |
| 17 | 🇨🇳 China (Hangzhou) | `2amizuhb3p5x2lk3sra7f7thm5tgs7qtnysgowqpmexcqi4cuwyv7vad.onion` | ModelScope CN / GFW Bypass |

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
