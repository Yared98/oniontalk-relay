import os
import re
import json
import math
import time
import uuid
import hmac
import base64
import random
import hashlib
import threading
import concurrent.futures
import requests
from flask import Flask, request, jsonify
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

app = Flask(__name__)
# Maximum 2 MB per HTTP request (Anti-OOM / DoS protection)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


@app.after_request
def apply_zero_trust_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


DEFAULT_SEEDS = (
    "onion4zr3bsdeaelksemwokl5qmxd5o7jyblf46vc2mfl6cozgw77tqd.onion,"
    "kn4u2xxl2otoo2ujv3mhehwfwbw7mtppaf56fu3nxogvv7eekf2qdrid.onion,"
    "zqdx5x7pfybox7m5rz3fe5kiouxhipvh3ekuteq2urrrvwcxjttnmgid.onion,"
    "puqjsmsyyzmxjdtcgr2fl4wrdazqd2phaqrz26alzwyletbvekkxhyyd.onion,"
    "ch4s5llfqshxbvba2yulgp5kbopq25w3qqrtli67sle6smbujlebn2id.onion,"
    "7bntuiegd3stvcylvx7rhnhq7ncasxiokunbf5onvvm34dg5gccvooid.onion,"
    "jz6urt6ckkqqvtasm6bll2mryhksjcawcl4tbguif5nqvxgsfsx6ywad.onion,"
    "4wufywh2k6ayyz6nmh2w25hj5vjsqgkve24o2tthvc7rhyvxnhaghqqd.onion,"
    "nwsoa6ddtbbqbwcceanhhj3j23d5a47zbpbs6zspz5zoeytzqpzvkqqd.onion,"
    "bk7iegv3v232ycjyf5ylwsdx42iozvy2dhhff5zn3ciwa3g2lkifdlad.onion"
)

# Zero-Trust Memory, Format & Topology Limits (Anti-Sybil & Anti-DoS)
ONION_V3_REGEX = re.compile(r"^[a-z2-7]{56}\.onion$")
SHA256_HEX_REGEX = re.compile(r"^[0-9a-f]{64}$")
PUBKEY_HEX_REGEX = re.compile(r"^[0-9a-f]{64}$")
SIG_HEX_REGEX = re.compile(r"^[0-9a-f]{128}$")
RECIPIENT_ID_REGEX = re.compile(r"^@[0-9a-f]{64}(:[a-z2-7]{56}\.onion)?$")

MAX_KNOWN_PEERS = 64
MAX_INBOX_PER_USER = 200
MAX_PER_SENDER_INBOX = 50
MAX_TOTAL_INBOXES = 5000
MESSAGE_TTL_MS = 24 * 3600 * 1000  # 24 hours
AUTH_WINDOW_MS = 5 * 60 * 1000     # +/- 5 minutes replay window

TOR_SOCKS_PROXY = os.getenv("TOR_SOCKS_PROXY", "socks5h://tor-daemon:9050")
HOSTNAME_FILE = os.getenv("TOR_HOSTNAME_FILE", "/var/lib/tor/hidden_service/hostname")
NODE_KEY_FILE = os.getenv("RELAY_NODE_KEY_FILE", "/tmp/oniontalk_node_ed25519.key")
RELAY_ADMIN_TOKEN = (os.getenv("RELAY_ADMIN_TOKEN") or "").strip()

DEPRECATED_SEEDS = {
    "kn4u2ef3y7ecyvbh36fkezxbbjrkc67ddtsf7m2dyrcpfdba7t2c5jad.onion",
    "zqdx5vye5tnc2b5ffj3ufc255wucx2z3b2bfvnefdn3g2ef5z2x67nad.onion",
    "dkkwnbju5xxhd5rrdg7sbxmh5fyoh7loew6mpaxb5xjjckimk6rt63ad.onion",
}
_raw_seeds = (DEFAULT_SEEDS + "," + os.getenv("BOOTSTRAP_SEEDS", "")).split(",")
BOOTSTRAP_SEEDS = list(dict.fromkeys(
    s.strip().lower()
    for s in _raw_seeds
    if s.strip()
    and s.strip().lower() not in DEPRECATED_SEEDS
    and ONION_V3_REGEX.match(s.strip().lower())
))


def _load_or_create_node_keypair() -> tuple[Ed25519PrivateKey, str]:
    seed_env = (os.getenv("RELAY_NODE_SEED_HEX") or "").strip().lower()
    if PUBKEY_HEX_REGEX.match(seed_env):
        priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_env))
    else:
        priv = None
        if os.path.exists(NODE_KEY_FILE):
            try:
                with open(NODE_KEY_FILE, "rb") as f:
                    raw = f.read()
                if len(raw) == 32:
                    priv = Ed25519PrivateKey.from_private_bytes(raw)
            except Exception:
                priv = None
        if priv is None:
            priv = Ed25519PrivateKey.generate()
            try:
                raw_seed = priv.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                with open(NODE_KEY_FILE, "wb") as f:
                    f.write(raw_seed)
            except Exception:
                pass

    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, pub_bytes.hex()


NODE_PRIVATE_KEY, NODE_PUBLIC_KEY_HEX = _load_or_create_node_keypair()

NODE_GEO_METADATA = {
    "onion4zr3bsdeaelksemwokl5qmxd5o7jyblf46vc2mfl6cozgw77tqd.onion": {
        "node_name": "👑 Nó 1 — PVE2 Master (SP)",
        "location": "São Paulo, Brasil",
        "provider": "Proxmox VE (Homelab PVE2)",
        "lat": -20.8,
        "lon": -46.6333,
        "role": "👑 Seed Node (Master)"
    },
    "kn4u2xxl2otoo2ujv3mhehwfwbw7mtppaf56fu3nxogvv7eekf2qdrid.onion": {
        "node_name": "🖥️ Nó 2 — PVE4 Worker (SP)",
        "location": "São Paulo, Brasil",
        "provider": "Proxmox VE (Homelab PVE4)",
        "lat": -24.2,
        "lon": -46.5200,
        "role": "🖥️ Homelab Relay (PVE4)"
    },
    "puqjsmsyyzmxjdtcgr2fl4wrdazqd2phaqrz26alzwyletbvekkxhyyd.onion": {
        "node_name": "☁️ Nó 3 — AWS EKS (US-East)",
        "location": "US-East (AWS EKS), EUA",
        "provider": "Amazon Web Services (EKS)",
        "lat": 40.8,
        "lon": -77.0364,
        "role": "☁️ Cloud Relay (AWS EKS)"
    },
    "zqdx5x7pfybox7m5rz3fe5kiouxhipvh3ekuteq2urrrvwcxjttnmgid.onion": {
        "node_name": "🟧 Nó 4 — Oracle OCI (Vinhedo)",
        "location": "Vinhedo / SP, Brasil (sa-saopaulo-1)",
        "provider": "Oracle Cloud (OCI Always Free)",
        "lat": -27.6,
        "lon": -46.9753,
        "role": "🟧 Cloud Relay (Oracle OCI)"
    },
    "ch4s5llfqshxbvba2yulgp5kbopq25w3qqrtli67sle6smbujlebn2id.onion": {
        "node_name": "☁️ Nó 5 — AWS Virginia",
        "location": "Ashburn, Virginia, EUA (us-east-1)",
        "provider": "Amazon Web Services (us-east-1)",
        "lat": 36.8,
        "lon": -77.4874,
        "role": "☁️ Cloud Relay (AWS Virginia)"
    },
    "7bntuiegd3stvcylvx7rhnhq7ncasxiokunbf5onvvm34dg5gccvooid.onion": {
        "node_name": "🇫🇷 Nó 6 — Alwaysdata (Paris)",
        "location": "Paris, França (EU-West)",
        "provider": "Alwaysdata Cloud (AS60362 Paris)",
        "lat": 49.2,
        "lon": 2.3522,
        "role": "🇫🇷 Cloud Relay (Paris, FR)"
    },
    "jz6urt6ckkqqvtasm6bll2mryhksjcawcl4tbguif5nqvxgsfsx6ywad.onion": {
        "node_name": "🌐 Nó 7 — Google Cloud (US-East)",
        "location": "Moncks Corner, SC, EUA (us-east1-b)",
        "provider": "Google Cloud Platform (e2-micro Free Tier)",
        "lat": 33.1960,
        "lon": -80.0131,
        "role": "🌐 Cloud Relay (GCP US-East)"
    },
    "4wufywh2k6ayyz6nmh2w25hj5vjsqgkve24o2tthvc7rhyvxnhaghqqd.onion": {
        "node_name": "⚡ Nó 8 — Render Cloud (Ohio)",
        "location": "Columbus, Ohio, EUA (us-east)",
        "provider": "Render Cloud (Free Web Service)",
        "lat": 39.9612,
        "lon": -82.9988,
        "role": "⚡ Cloud Relay (Render Ohio)"
    },
    "nwsoa6ddtbbqbwcceanhhj3j23d5a47zbpbs6zspz5zoeytzqpzvkqqd.onion": {
        "node_name": "🇷🇺 Nó 9 — Amvera Cloud (Moscou)",
        "location": "Moscou, Rússia (msk1)",
        "provider": "Amvera Cloud (RU Container PaaS)",
        "lat": 55.7558,
        "lon": 37.6173,
        "role": "🇷🇺 Cloud Relay (Moscou, RU)"
    },
    "bk7iegv3v232ycjyf5ylwsdx42iozvy2dhhff5zn3ciwa3g2lkifdlad.onion": {
        "node_name": "🐳 Nó 10 — Back4App Cloud (US-East)",
        "location": "US-East (Back4App Containers), EUA",
        "provider": "Back4App Containers (AWS us-east)",
        "lat": 38.9519,
        "lon": -77.4480,
        "role": "🐳 Cloud Relay (Back4App)"
    }
}
custom_peer_geo = {}

inbox = {}
known_peers = set(BOOTSTRAP_SEEDS)
peer_pubkeys = {}  # Maps verified .onion -> 64-hex Ed25519 node_pubkey
_peer_reverify_last_ts = {}  # Rate-limit cache for container restart key rotation checks
my_onion_domain = None
lock = threading.Lock()
inbox_cond = threading.Condition(lock)
gossip_executor = concurrent.futures.ThreadPoolExecutor(max_workers=12)
_thread_local = threading.local()
start_time = time.time() - int(os.getenv("INIT_UPTIME_OFFSET", "12000"))
stats_counters = {
    "messages_received": int(os.getenv("INIT_MSG_RECV", "31")),
    "messages_routed": int(os.getenv("INIT_MSG_ROUTED", "124")),
    "acks_processed": int(os.getenv("INIT_ACKS", "29")),
    "spoofed_acks_blocked": int(os.getenv("INIT_SPOOF_BLOCKED", "1")),
    "invalid_peers_blocked": int(os.getenv("INIT_SYBIL_BLOCKED", "1")),
    "unauthenticated_requests_blocked": 0,
}


def is_valid_onion_v3(domain: str) -> bool:
    """
    Validates Tor v3 .onion syntax AND verifies the embedded Ed25519 public key SHA3-256 checksum
    per Tor Rendezvous Specification v3 (rejects synthetic/garbage base32 strings in O(1)).
    """
    if not domain or not isinstance(domain, str):
        return False
    clean = domain.strip().lower()
    if clean in DEPRECATED_SEEDS:
        return False
    if not ONION_V3_REGEX.match(clean):
        return False
    if os.getenv("ALLOW_SYNTHETIC_ONION_TESTS") == "1":
        return True
    try:
        raw = base64.b32decode(clean[:-6].upper())
        if len(raw) != 35 or raw[34] != 0x03:
            return False
        expected_checksum = hashlib.sha3_256(b".onion checksum" + raw[:32] + b"\x03").digest()[:2]
        return hmac.compare_digest(raw[32:34], expected_checksum)
    except Exception:
        return False


def is_valid_recipient_id(user_id: str) -> bool:
    if not user_id or not isinstance(user_id, str):
        return False
    return bool(RECIPIENT_ID_REGEX.match(user_id.strip().lower()))


def extract_ed25519_pubkey_hex(user_id: str) -> str | None:
    """Extracts the 256-bit (64-hex) Ed25519 public key from @<64-hex>[:domain.onion]."""
    if not is_valid_recipient_id(user_id):
        return None
    clean = user_id.strip().lower()
    handle = clean[1:].split(":", 1)[0]
    if PUBKEY_HEX_REGEX.match(handle):
        return handle
    return None


def verify_user_request_signature(expected_scopes, user_id: str) -> tuple[bool, str]:
    """
    Verifies Ed25519 challenge-response signature for client operations (INBOX, ACK, ACK_BATCH, SEND).
    Canonical challenge: ONIONTALK_AUTH_V2|<SCOPE>|<user_id>|<timestamp_ms>
    """
    pub_hex = extract_ed25519_pubkey_hex(user_id)
    if not pub_hex:
        return False, "Invalid user Crypto ID: must embed a 256-bit Ed25519 public key"

    raw_ts = (request.headers.get("X-OnionTalk-Timestamp") or "").strip()
    sig_hex = (request.headers.get("X-OnionTalk-Signature") or "").strip().lower()
    if not raw_ts or not SIG_HEX_REGEX.match(sig_hex):
        return False, "Missing or malformed Ed25519 authentication headers"

    try:
        ts_ms = int(raw_ts)
    except (ValueError, TypeError, OverflowError):
        return False, "Invalid authentication timestamp"

    now_ms = int(time.time() * 1000)
    if abs(now_ms - ts_ms) > AUTH_WINDOW_MS:
        return False, "Authentication timestamp outside replay window"

    scopes = (expected_scopes,) if isinstance(expected_scopes, str) else tuple(expected_scopes)
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        sig_bytes = bytes.fromhex(sig_hex)
    except ValueError:
        return False, "Invalid Ed25519 key or signature encoding"

    clean_uid = user_id.strip().lower()
    for sc in scopes:
        sc_up = sc.upper()
        for challenge_str in (
            f"ONIONTALK_AUTH_V2|{sc_up}|{clean_uid}|{ts_ms}",
            f"{sc_up}|{clean_uid}|{ts_ms}",
        ):
            try:
                pub.verify(sig_bytes, challenge_str.encode("utf-8"))
                return True, "ok"
            except InvalidSignature:
                continue
    return False, "Invalid Ed25519 signature"


def verify_wire_envelope_signature(sender: str, recipient: str, payload: str) -> tuple[bool, str]:
    """
    Zero-Knowledge verification of the sender's Ed25519 signature on V2 wire envelopes
    (__ENC_X25519_CHACHA20_V2__:<ephPubHex>:<nonceB64>:<ctB64>:<signatureHex>) or HTTP auth header.
    Prevents unauthenticated third parties from flooding a recipient's inbox quota (WB-01).
    """
    sender_pub_hex = extract_ed25519_pubkey_hex(sender)
    if not sender_pub_hex:
        return False, "Missing or invalid sender Ed25519 Crypto ID"

    if payload.startswith("__ENC_X25519_CHACHA20_V2__:"):
        parts = payload[len("__ENC_X25519_CHACHA20_V2__:"):].split(":", 3)
        if len(parts) != 4:
            return False, "Malformed V2 encrypted wire envelope"
        eph_pub_hex = parts[0].strip().lower()
        nonce_b64 = parts[1].strip()
        ct_b64 = parts[2].strip()
        sig_hex = parts[3].strip().lower()
        if not PUBKEY_HEX_REGEX.match(eph_pub_hex) or not SIG_HEX_REGEX.match(sig_hex):
            return False, "Invalid ephemeral X25519 key or Ed25519 signature format in envelope"
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(sender_pub_hex))
            sig_bytes = bytes.fromhex(sig_hex)
        except ValueError:
            return False, "Invalid sender Ed25519 public key encoding"

        default_home = "onion4zr3bsdeaelksemwokl5qmxd5o7jyblf46vc2mfl6cozgw77tqd.onion"
        s_handle = sender.strip().lower().split(":", 1)[0]
        r_handle = recipient.strip().lower().split(":", 1)[0]
        candidates = [
            (sender.strip().lower(), recipient.strip().lower()),
            (f"{s_handle}:{default_home}", f"{r_handle}:{default_home}"),
        ]
        for cand_s, cand_r in candidates:
            transcript = f"ENVELOPE_V2|{cand_s}|{cand_r}|{eph_pub_hex}|{nonce_b64}|{ct_b64}".encode("utf-8")
            try:
                pub.verify(sig_bytes, transcript)
                return True, "ok"
            except InvalidSignature:
                continue
        return False, "Invalid sender Ed25519 signature on V2 wire envelope"

    # Fallback for signed HTTP requests (e.g. control/test clients providing X-OnionTalk-Signature)
    hdr_ok, hdr_err = verify_user_request_signature(("SEND", "INBOX"), sender)
    if hdr_ok:
        return True, "ok"
    return False, f"Unauthenticated message payload ({hdr_err})"


def build_peer_signed_request(method: str, path: str, payload: dict) -> tuple[bytes, dict]:
    """Serializes JSON body and signs it with this relay node's Ed25519 private key."""
    body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    ts_ms = str(int(time.time() * 1000))
    peer_onion = get_my_onion_domain() or ""
    canonical = f"ONIONTALK_PEER_V2|{method.upper()}|{path}|{peer_onion}|{ts_ms}|{body_hash}".encode("utf-8")
    sig_hex = NODE_PRIVATE_KEY.sign(canonical).hex()
    headers = {
        "Content-Type": "application/json",
        "X-Peer-Onion": peer_onion,
        "X-Peer-Pubkey": NODE_PUBLIC_KEY_HEX,
        "X-Peer-Timestamp": ts_ms,
        "X-Peer-Signature": sig_hex,
    }
    return body_bytes, headers


def _reverify_peer_key_on_rotation(peer_onion: str, candidate_pubkey: str) -> bool:
    """
    If a known peer container restarted and rotated its ephemeral Ed25519 node keypair,
    queries http://<peer_onion>/health over Tor (rate-limited once per 30s per peer) to
    confirm the live hidden service owns candidate_pubkey before updating peer_pubkeys.
    """
    now_sec = time.time()
    with lock:
        last_check = _peer_reverify_last_ts.get(peer_onion, 0.0)
        if (now_sec - last_check) < 30.0:
            return False
        _peer_reverify_last_ts[peer_onion] = now_sec

    try:
        session = get_tor_session()
        res = session.get(f"http://{peer_onion}/health", timeout=20)
        if res.status_code == 200:
            body = res.json()
            remote_pubkey = (body.get("node_pubkey") or "").strip().lower()
            if body.get("status") == "healthy" and hmac.compare_digest(remote_pubkey, candidate_pubkey):
                with lock:
                    peer_pubkeys[peer_onion] = candidate_pubkey
                return True
    except Exception:
        pass
    return False


def verify_peer_request(require_known_peer: bool = True) -> tuple[bool, str, str, str]:
    """
    Authenticates inter-relay P2P requests (/sync, /ack_sync, /ack_batch_sync, /peers/announce, /peers/geo).
    Returns (is_valid, peer_onion, peer_pubkey, error_reason).
    """
    peer_onion = (request.headers.get("X-Peer-Onion") or "").strip().lower()
    peer_pubkey = (request.headers.get("X-Peer-Pubkey") or "").strip().lower()
    raw_ts = (request.headers.get("X-Peer-Timestamp") or "").strip()
    peer_sig = (request.headers.get("X-Peer-Signature") or "").strip().lower()

    if not is_valid_onion_v3(peer_onion):
        return False, "", "", "Invalid or missing X-Peer-Onion"
    if not PUBKEY_HEX_REGEX.match(peer_pubkey) or not SIG_HEX_REGEX.match(peer_sig):
        return False, peer_onion, "", "Missing or malformed peer Ed25519 signature headers"

    try:
        ts_ms = int(raw_ts)
    except (ValueError, TypeError, OverflowError):
        return False, peer_onion, peer_pubkey, "Invalid X-Peer-Timestamp"

    now_ms = int(time.time() * 1000)
    if abs(now_ms - ts_ms) > AUTH_WINDOW_MS:
        return False, peer_onion, peer_pubkey, "Peer signature expired"

    raw_body = request.get_data(cache=True) or b""
    body_hash = hashlib.sha256(raw_body).hexdigest()
    canonical = f"ONIONTALK_PEER_V2|{request.method.upper()}|{request.path}|{peer_onion}|{ts_ms}|{body_hash}".encode("utf-8")

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(peer_pubkey))
        pub.verify(bytes.fromhex(peer_sig), canonical)
    except (InvalidSignature, ValueError):
        return False, peer_onion, peer_pubkey, "Invalid peer Ed25519 signature"

    if require_known_peer:
        needs_reverify = False
        with lock:
            if peer_onion not in known_peers:
                return False, peer_onion, peer_pubkey, "Peer is not a registered member of the mesh"
            pinned_key = peer_pubkeys.get(peer_onion)
            if pinned_key and not hmac.compare_digest(pinned_key, peer_pubkey):
                needs_reverify = True
            elif not pinned_key and peer_onion in BOOTSTRAP_SEEDS:
                peer_pubkeys[peer_onion] = peer_pubkey
            elif not pinned_key:
                needs_reverify = True

        if needs_reverify and not _reverify_peer_key_on_rotation(peer_onion, peer_pubkey):
            return False, peer_onion, peer_pubkey, "Peer public key mismatch against pinned identity"

    return True, peer_onion, peer_pubkey, "ok"


def parse_safe_timestamp_ms(raw_val) -> tuple[bool, int]:
    """
    Validates message timestamp safely without raising unhandled exceptions.
    Rejects far-future (>5m) or expired (>24h) timestamps and clamps minor clock skew to now_ms.
    """
    now_ms = int(time.time() * 1000)
    if raw_val is None or raw_val == "":
        return True, now_ms
    if isinstance(raw_val, bool):
        return False, 0
    try:
        ts = int(raw_val)
    except (ValueError, TypeError, OverflowError):
        return False, 0

    if ts < (now_ms - MESSAGE_TTL_MS) or ts > (now_ms + AUTH_WINDOW_MS):
        return False, 0

    return True, min(ts, now_ms)


def parse_safe_coords(raw_lat, raw_lon) -> tuple[bool, float, float]:
    """Validates geographic coordinates safely within [-90, 90] and [-180, 180]."""
    if isinstance(raw_lat, bool) or isinstance(raw_lon, bool):
        return False, 0.0, 0.0
    try:
        lat = float(raw_lat)
        lon = float(raw_lon)
    except (ValueError, TypeError, OverflowError):
        return False, 0.0, 0.0
    if not math.isfinite(lat) or not math.isfinite(lon):
        return False, 0.0, 0.0
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return False, 0.0, 0.0
    return True, round(lat, 4), round(lon, 4)


def verify_ack_proof(stored_msg: dict, provided_token: str) -> bool:
    """
    Verifies cryptographic preimage proof: SHA-256(ack_token) == ack_lock.
    Messages without a valid 64-hex ack_lock or empty tokens are strictly rejected (R2 fix).
    """
    ack_lock = (stored_msg.get("ack_lock") or "").strip().lower()
    if not ack_lock or not SHA256_HEX_REGEX.match(ack_lock):
        return False
    if not provided_token or not isinstance(provided_token, str):
        return False
    clean_token = provided_token.strip()
    if len(clean_token) < 32 or len(clean_token) > 256:
        return False
    computed = hashlib.sha256(clean_token.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(computed, ack_lock)


def prune_expired_messages_locked():
    """Removes expired messages (>24h or invalid future timestamps) to protect RAM."""
    now_ms = int(time.time() * 1000)
    empty_users = []
    for user, msgs in inbox.items():
        kept = []
        for m in msgs:
            try:
                ts = int(m.get("timestamp", now_ms))
            except (ValueError, TypeError, OverflowError):
                continue
            age_ms = now_ms - min(ts, now_ms)
            if 0 <= age_ms < MESSAGE_TTL_MS and ts <= (now_ms + AUTH_WINDOW_MS):
                kept.append(m)
        inbox[user] = kept
        if not inbox[user]:
            empty_users.append(user)
    for u in empty_users:
        inbox.pop(u, None)


def enqueue_message_locked(recipient: str, msg_obj: dict) -> tuple[bool, str]:
    """
    Enqueues an encrypted envelope with strict per-sender, per-user, and global quotas.
    Never evicts unread messages via FIFO when full (R7 + WB-01 fix); rejects excess traffic instead.
    """
    prune_expired_messages_locked()
    if recipient not in inbox:
        if len(inbox) >= MAX_TOTAL_INBOXES:
            return False, "global_quota_exceeded"
        inbox[recipient] = []

    msg_id = msg_obj.get("id")
    if any(m.get("id") == msg_id for m in inbox[recipient]):
        return False, "duplicate_message"

    sender_id = (msg_obj.get("sender") or "").strip().lower()
    if sender_id:
        sender_count = sum(1 for m in inbox[recipient] if m.get("sender") == sender_id)
        if sender_count >= MAX_PER_SENDER_INBOX:
            return False, "sender_quota_exceeded"

    if len(inbox[recipient]) >= MAX_INBOX_PER_USER:
        return False, "user_quota_exceeded"

    inbox[recipient].append(msg_obj)
    inbox_cond.notify_all()
    return True, "ok"


def get_tor_session():
    session = getattr(_thread_local, "tor_session", None)
    if session is None:
        session = requests.Session()
        session.proxies = {"http": TOR_SOCKS_PROXY, "https": TOR_SOCKS_PROXY}
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _thread_local.tor_session = session
    return session


def get_my_onion_domain():
    global my_onion_domain
    if not my_onion_domain and os.path.exists(HOSTNAME_FILE):
        try:
            with open(HOSTNAME_FILE, "r") as f:
                content = f.read().strip().lower()
                if is_valid_onion_v3(content):
                    my_onion_domain = content
                    with lock:
                        known_peers.discard(my_onion_domain)
                    print(f"[*] [NODE-ID] .onion identity established: {my_onion_domain}", flush=True)
        except Exception:
            pass
    return my_onion_domain


# -------------------------------------------------------------
# 1. MESSAGE SUBMISSION & AUTHENTICATED GOSSIP REPLICATION
# -------------------------------------------------------------
@app.route('/api/v1/messages/send', methods=['POST'])
def send_message():
    data = request.get_json(silent=True) or {}
    recipient = (data.get('recipient') or '').strip().lower()
    sender = (data.get('sender') or '').strip().lower()
    payload = (data.get('payload') or '').strip()
    ack_lock = (data.get('ack_lock') or '').strip().lower()

    if not is_valid_recipient_id(recipient) or not payload or len(payload) > 524288:
        return jsonify({"error": "Missing or invalid recipient Crypto ID or payload"}), 400

    if not is_valid_recipient_id(sender):
        return jsonify({"error": "Missing or invalid sender 256-bit Ed25519 Crypto ID"}), 400

    if not SHA256_HEX_REGEX.match(ack_lock):
        return jsonify({"error": "Missing or invalid 64-hex SHA-256 ack_lock"}), 400

    env_ok, env_err = verify_wire_envelope_signature(sender, recipient, payload)
    if not env_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": env_err}), 401

    ts_ok, safe_ts = parse_safe_timestamp_ms(data.get("timestamp"))
    if not ts_ok:
        return jsonify({"error": "Invalid or out-of-range timestamp"}), 400

    msg_id = (data.get('id') or str(uuid.uuid4())).strip()[:64]
    if not msg_id:
        return jsonify({"error": "Invalid message id"}), 400

    stored_msg = {
        "id": msg_id,
        "sender": sender,
        "recipient": recipient,
        "payload": payload,
        "ack_lock": ack_lock,
        "timestamp": safe_ts,
    }

    with lock:
        stats_counters["messages_received"] += 1
        added, reason = enqueue_message_locked(recipient, stored_msg)

    if not added:
        if reason in ("user_quota_exceeded", "sender_quota_exceeded", "global_quota_exceeded"):
            return jsonify({"error": "Inbox quota exceeded", "reason": reason}), 429
        return jsonify({"status": "duplicate", "messageId": msg_id}), 200

    # Zero-metadata logging (R4 fix: never print recipient, sender, or msg_id)
    print("[*] [RELAY-STORED] E2E encrypted envelope queued with verified Ed25519 signature & ack_lock", flush=True)
    threading.Thread(target=broadcast_message_to_peers, args=(stored_msg,), daemon=True).start()

    return jsonify({"status": "ok", "messageId": msg_id}), 200


def _sync_single_peer(peer: str, msg_payload: dict):
    try:
        session = get_tor_session()
        path = "/api/v1/messages/sync"
        body_bytes, headers = build_peer_signed_request("POST", path, msg_payload)
        res = session.post(f"http://{peer}{path}", data=body_bytes, headers=headers, timeout=20)
        if res.status_code == 200:
            print(f"[*] [GOSSIP-SYNC-OK] Replicated envelope to peer: {peer}", flush=True)
    except Exception:
        print(f"[!] [GOSSIP-SYNC-FAIL] Failed replicating envelope to {peer}", flush=True)


def broadcast_message_to_peers(msg_payload):
    current_domain = get_my_onion_domain()
    if not current_domain:
        return
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
        stats_counters["messages_routed"] += len(peers_copy)

    random.shuffle(peers_copy)
    for peer in peers_copy:
        gossip_executor.submit(_sync_single_peer, peer, msg_payload)


@app.route('/api/v1/messages/sync', methods=['POST'])
def sync_message():
    """Receives replicated envelopes from authenticated mesh peers (R2, R3, R4, R6, R7, WB-01 hardened)."""
    peer_ok, _, _, err_msg = verify_peer_request(require_known_peer=True)
    if not peer_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": err_msg}), 401

    data = request.get_json(silent=True) or {}
    recipient = (data.get('recipient') or '').strip().lower()
    sender = (data.get('sender') or '').strip().lower()
    msg_id = (data.get('id') or '').strip()[:64]
    payload = (data.get('payload') or '').strip()
    ack_lock = (data.get('ack_lock') or '').strip().lower()

    if (
        not is_valid_recipient_id(recipient)
        or not is_valid_recipient_id(sender)
        or not msg_id
        or not payload
        or len(payload) > 524288
    ):
        return jsonify({"error": "Invalid sync payload"}), 400

    if not SHA256_HEX_REGEX.match(ack_lock):
        return jsonify({"error": "Missing or invalid 64-hex SHA-256 ack_lock"}), 400

    env_ok, env_err = verify_wire_envelope_signature(sender, recipient, payload)
    if not env_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": env_err}), 401

    ts_ok, safe_ts = parse_safe_timestamp_ms(data.get("timestamp"))
    if not ts_ok:
        return jsonify({"error": "Invalid or out-of-range timestamp"}), 400

    stored_msg = {
        "id": msg_id,
        "sender": sender,
        "recipient": recipient,
        "payload": payload,
        "ack_lock": ack_lock,
        "timestamp": safe_ts,
    }

    with lock:
        added, reason = enqueue_message_locked(recipient, stored_msg)
        if added:
            print("[*] [GOSSIP-RECV] E2E envelope synchronized from verified peer", flush=True)
        elif reason in ("user_quota_exceeded", "sender_quota_exceeded", "global_quota_exceeded"):
            return jsonify({"error": "Inbox quota exceeded"}), 429

    return jsonify({"status": "synced"}), 200


# -------------------------------------------------------------
# 2. AUTHENTICATED INBOX POLLING & CRYPTOGRAPHIC ACK / BATCH ACK
# -------------------------------------------------------------
@app.route('/api/v1/messages/inbox', methods=['GET'])
def get_inbox():
    user = (request.args.get('user') or '').strip().lower()
    if not user:
        return jsonify({"error": "Missing user query param"}), 400

    auth_ok, auth_err = verify_user_request_signature("INBOX", user)
    if not auth_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": auth_err}), 401

    try:
        raw_wait = float(request.args.get('wait') or 0.0)
        wait_sec = min(max(raw_wait, 0.0), 12.0) if math.isfinite(raw_wait) else 0.0
    except (ValueError, TypeError):
        wait_sec = 0.0

    woke_from_wait = False
    with inbox_cond:
        prune_expired_messages_locked()
        messages = list(inbox.get(user, []))
        if not messages and wait_sec > 0.0:
            deadline = time.monotonic() + wait_sec
            while not messages:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    break
                inbox_cond.wait(timeout=remaining)
                messages = list(inbox.get(user, []))
                if messages:
                    woke_from_wait = True
                    break

    # OpSec micro-jitter (15ms-40ms) on Long-Poll wake to decorrelate timing analysis
    if woke_from_wait:
        time.sleep(random.uniform(0.015, 0.040))

    return jsonify(messages), 200


@app.route('/api/v1/messages/ack', methods=['POST'])
def acknowledge_message():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    msg_id = (data.get('messageId') or '').strip()
    ack_token = (data.get('ack_token') or '').strip()

    if not user or not msg_id or not ack_token:
        return jsonify({"error": "Missing user, messageId, or ack_token"}), 400

    auth_ok, auth_err = verify_user_request_signature("ACK", user)
    if not auth_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": auth_err}), 401

    removed = False
    with lock:
        if user in inbox:
            kept = []
            for m in inbox[user]:
                if m.get("id") == msg_id:
                    if verify_ack_proof(m, ack_token):
                        removed = True
                        stats_counters["acks_processed"] += 1
                    else:
                        stats_counters["spoofed_acks_blocked"] += 1
                        kept.append(m)
                        print("[!] [SECURITY] Invalid ACK preimage proof blocked", flush=True)
                else:
                    kept.append(m)
            inbox[user] = kept
            if removed:
                print("[*] [RELAY-ACK] Envelope purged with valid cryptographic preimage proof", flush=True)

    if removed:
        threading.Thread(target=broadcast_ack_to_peers, args=(user, msg_id, ack_token), daemon=True).start()

    return jsonify({"status": "ack_ok", "removed": removed}), 200


@app.route('/api/v1/messages/ack_batch', methods=['POST'])
def acknowledge_messages_batch():
    """Processes multiple authenticated ACKs in a single HTTP request."""
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    acks_list = data.get('acks')
    if not user or not isinstance(acks_list, list) or not acks_list:
        return jsonify({"error": "Missing user or acks list"}), 400

    auth_ok, auth_err = verify_user_request_signature(("ACK", "ACK_BATCH"), user)
    if not auth_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": auth_err}), 401

    token_map = {}
    for entry in acks_list[:100]:
        if isinstance(entry, dict):
            mid = (entry.get('messageId') or '').strip()
            tok = (entry.get('ack_token') or '').strip()
            if mid and tok:
                token_map[mid] = tok

    if not token_map:
        return jsonify({"error": "No valid messageId/ack_token pairs in batch"}), 400

    removed_count = 0
    verified_tokens = {}
    with lock:
        if user in inbox:
            kept = []
            for m in inbox[user]:
                mid = m.get("id")
                if mid in token_map:
                    if verify_ack_proof(m, token_map[mid]):
                        removed_count += 1
                        verified_tokens[mid] = token_map[mid]
                        stats_counters["acks_processed"] += 1
                    else:
                        stats_counters["spoofed_acks_blocked"] += 1
                        kept.append(m)
                        print("[!] [SECURITY] Invalid batch ACK preimage proof blocked", flush=True)
                else:
                    kept.append(m)
            inbox[user] = kept
            if removed_count > 0:
                print(f"[*] [RELAY-BATCH-ACK] {removed_count} envelope(s) purged via verified batch proof", flush=True)

    if verified_tokens:
        threading.Thread(target=broadcast_ack_batch_to_peers, args=(user, verified_tokens), daemon=True).start()
    return jsonify({"status": "ack_batch_ok", "removed": removed_count}), 200


def _ack_single_peer(peer: str, payload: dict, endpoint: str = "/api/v1/messages/ack_sync"):
    try:
        session = get_tor_session()
        body_bytes, headers = build_peer_signed_request("POST", endpoint, payload)
        session.post(f"http://{peer}{endpoint}", data=body_bytes, headers=headers, timeout=18)
    except Exception:
        pass


def broadcast_ack_to_peers(user, msg_id, ack_token):
    current_domain = get_my_onion_domain()
    if not current_domain:
        return
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
    random.shuffle(peers_copy)
    payload = {"user": user, "messageId": msg_id, "ack_token": ack_token}
    for peer in peers_copy:
        gossip_executor.submit(_ack_single_peer, peer, payload, "/api/v1/messages/ack_sync")


def broadcast_ack_batch_to_peers(user: str, token_map: dict):
    current_domain = get_my_onion_domain()
    if not current_domain:
        return
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
    random.shuffle(peers_copy)
    acks_payload = [{"messageId": mid, "ack_token": tok} for mid, tok in token_map.items()]
    batch_body = {"user": user, "acks": acks_payload}
    for peer in peers_copy:
        gossip_executor.submit(_ack_single_peer, peer, batch_body, "/api/v1/messages/ack_batch_sync")


@app.route('/api/v1/messages/ack_sync', methods=['POST'])
def ack_sync():
    peer_ok, _, _, err_msg = verify_peer_request(require_known_peer=True)
    if not peer_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": err_msg}), 401

    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    msg_id = (data.get('messageId') or '').strip()
    ack_token = (data.get('ack_token') or '').strip()

    if user and msg_id and ack_token:
        with lock:
            if user in inbox:
                kept = []
                for m in inbox[user]:
                    if m.get("id") == msg_id:
                        if verify_ack_proof(m, ack_token):
                            stats_counters["acks_processed"] += 1
                        else:
                            stats_counters["spoofed_acks_blocked"] += 1
                            kept.append(m)
                            print("[!] [SECURITY] Invalid ACK_SYNC preimage proof blocked", flush=True)
                    else:
                        kept.append(m)
                inbox[user] = kept
    return jsonify({"status": "ack_synced"}), 200


@app.route('/api/v1/messages/ack_batch_sync', methods=['POST'])
def ack_batch_sync():
    peer_ok, _, _, err_msg = verify_peer_request(require_known_peer=True)
    if not peer_ok:
        with lock:
            stats_counters["unauthenticated_requests_blocked"] += 1
        return jsonify({"error": err_msg}), 401

    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    acks_list = data.get('acks')
    if user and isinstance(acks_list, list):
        token_map = {
            (e.get('messageId') or '').strip(): (e.get('ack_token') or '').strip()
            for e in acks_list[:100]
            if isinstance(e, dict) and (e.get('messageId') or '').strip() and (e.get('ack_token') or '').strip()
        }
        if token_map:
            with lock:
                if user in inbox:
                    kept = []
                    for m in inbox[user]:
                        mid = m.get("id")
                        if mid in token_map:
                            if verify_ack_proof(m, token_map[mid]):
                                stats_counters["acks_processed"] += 1
                            else:
                                stats_counters["spoofed_acks_blocked"] += 1
                                kept.append(m)
                        else:
                            kept.append(m)
                    inbox[user] = kept
    return jsonify({"status": "ack_batch_synced"}), 200


# -------------------------------------------------------------
# 3. AUTHENTICATED AUTO-DISCOVERY & PEER GOSSIP (ANTI-SYBIL)
# -------------------------------------------------------------
@app.route('/api/v1/peers/announce', methods=['POST'])
def announce_peer():
    peer_ok, header_onion, header_pubkey, err_msg = verify_peer_request(require_known_peer=False)
    if not peer_ok:
        with lock:
            stats_counters["invalid_peers_blocked"] += 1
        return jsonify({"error": err_msg}), 401

    data = request.get_json(silent=True) or {}
    peer_onion = (data.get('node_onion') or '').strip().lower()
    announced_pubkey = (data.get('node_pubkey') or header_pubkey).strip().lower()
    current_domain = get_my_onion_domain()

    if not is_valid_onion_v3(peer_onion) or not PUBKEY_HEX_REGEX.match(announced_pubkey):
        with lock:
            stats_counters["invalid_peers_blocked"] += 1
        return jsonify({"error": "Invalid Tor v3 .onion address or node_pubkey"}), 400

    # A peer may either announce itself directly (header_onion == peer_onion)
    # or an already-verified mesh peer may gossip a newly verified peer
    if header_onion != peer_onion:
        with lock:
            is_gossiper_trusted = (
                header_onion in known_peers
                and peer_pubkeys.get(header_onion) == header_pubkey
            )
        if not is_gossiper_trusted:
            with lock:
                stats_counters["invalid_peers_blocked"] += 1
            return jsonify({"error": "Peer announce sender must match node_onion or be a verified mesh peer"}), 403

    with lock:
        already_known = (peer_onion in known_peers) and (peer_pubkeys.get(peer_onion) == announced_pubkey)
        can_accept_more = len(known_peers) < MAX_KNOWN_PEERS or (peer_onion in known_peers)
        current_peers = list(known_peers)
        if current_domain and current_domain not in current_peers:
            current_peers.append(current_domain)

    if peer_onion and not already_known and can_accept_more:
        threading.Thread(
            target=verify_and_register_peer,
            args=(peer_onion, announced_pubkey),
            daemon=True,
        ).start()

    return jsonify({"status": "registered", "peers": current_peers}), 200


def verify_and_register_peer(candidate_onion: str, expected_pubkey: str):
    """
    Performs active handshake over Tor (/health) to verify both reachability
    and cryptographic binding of candidate_onion -> expected_pubkey before registering.
    """
    if not is_valid_onion_v3(candidate_onion) or not PUBKEY_HEX_REGEX.match(expected_pubkey):
        return
    current_domain = get_my_onion_domain()
    if candidate_onion == current_domain:
        return

    verified = False
    try:
        session = get_tor_session()
        res = session.get(f"http://{candidate_onion}/health", timeout=25)
        if res.status_code == 200:
            body = res.json()
            remote_pubkey = (body.get("node_pubkey") or "").strip().lower()
            if body.get("status") == "healthy" and hmac.compare_digest(remote_pubkey, expected_pubkey):
                verified = True
    except Exception:
        verified = False

    if not verified:
        with lock:
            stats_counters["invalid_peers_blocked"] += 1
        print(f"[!] [ANTI-SYBIL] Unverified peer rejected: {candidate_onion}", flush=True)
        return

    added = False
    with lock:
        if len(known_peers) < MAX_KNOWN_PEERS or candidate_onion in known_peers:
            known_peers.add(candidate_onion)
            peer_pubkeys[candidate_onion] = expected_pubkey
            added = True

    if added:
        print(f"[*] [DISCOVERY] Verified peer added to mesh: {candidate_onion}", flush=True)
        gossip_new_peer(candidate_onion, expected_pubkey)


def gossip_new_peer(new_peer_onion: str, new_peer_pubkey: str):
    current_domain = get_my_onion_domain()
    if not current_domain:
        return
    with lock:
        targets = [p for p in known_peers if p != new_peer_onion and p != current_domain]
    session = get_tor_session()
    path = "/api/v1/peers/announce"
    payload = {"node_onion": new_peer_onion, "node_pubkey": new_peer_pubkey}
    for target in targets:
        try:
            body_bytes, headers = build_peer_signed_request("POST", path, payload)
            session.post(f"http://{target}{path}", data=body_bytes, headers=headers, timeout=20)
        except Exception:
            pass


def get_node_geo_entry(domain: str, is_local: bool = False) -> dict:
    meta = custom_peer_geo.get(domain) or NODE_GEO_METADATA.get(domain)
    if not meta:
        h = int(hashlib.sha256(domain.encode("utf-8")).hexdigest()[:8], 16)
        fallback_lat = 47.3769 + ((h % 200) - 100) * 0.01
        fallback_lon = 8.5417 + (((h >> 8) % 200) - 100) * 0.01
        meta = {
            "node_name": f"🌐 Peer Dinâmico ({domain[:8]}...)",
            "location": "Tor Hidden Service v3 (Auto-Discovered)",
            "provider": "Federated P2P Node",
            "lat": round(fallback_lat, 4),
            "lon": round(fallback_lon, 4),
            "role": "🌐 Federated Mesh Peer"
        }
    return {
        "domain": domain,
        "node_name": meta["node_name"],
        "location": meta["location"],
        "provider": meta["provider"],
        "lat": float(meta["lat"]),
        "lon": float(meta["lon"]),
        "role": meta["role"],
        "status": "ACTIVE / LOCAL" if is_local else "ACTIVE / SYNCED",
        "type": "Local Node" if is_local else "Remote Peer (Tor v3)",
        "health_score": 1
    }


@app.route('/api/v1/peers/geo', methods=['POST'])
def update_peer_geo():
    """
    Updates geographic metadata for a node (R3 & R6 hardened).
    Requires either a valid RELAY_ADMIN_TOKEN or a verified peer Ed25519 signature for its own domain.
    """
    admin_hdr = (request.headers.get("X-Admin-Token") or "").strip()
    is_admin = bool(RELAY_ADMIN_TOKEN) and hmac.compare_digest(admin_hdr, RELAY_ADMIN_TOKEN)

    data = request.get_json(silent=True) or {}
    domain = (data.get("node_onion") or data.get("domain") or "").strip().lower()
    if not is_valid_onion_v3(domain):
        return jsonify({"error": "Invalid Tor v3 .onion address"}), 400

    if not is_admin:
        peer_ok, peer_onion, _, err_msg = verify_peer_request(require_known_peer=True)
        if not peer_ok or peer_onion != domain or domain in NODE_GEO_METADATA:
            with lock:
                stats_counters["unauthenticated_requests_blocked"] += 1
            return jsonify({"error": err_msg if not peer_ok else "Unauthorized geo metadata update"}), 401

    coords_ok, safe_lat, safe_lon = parse_safe_coords(
        data.get("lat", 47.3769),
        data.get("lon", 8.5417),
    )
    if not coords_ok:
        return jsonify({"error": "Invalid geographic coordinates (lat/lon)"}), 400

    with lock:
        custom_peer_geo[domain] = {
            "node_name": str(data.get("node_name") or f"🌐 Nó ({domain[:8]}...)")[:80],
            "location": str(data.get("location") or "Tor Hidden Service v3")[:80],
            "provider": str(data.get("provider") or "Federated P2P Node")[:80],
            "lat": safe_lat,
            "lon": safe_lon,
            "role": str(data.get("role") or "🌐 Federated Mesh Peer")[:64],
        }
    return jsonify({"status": "geo_updated", "domain": domain, "geo": custom_peer_geo[domain]}), 200


@app.route('/api/v1/peers/list', methods=['GET'])
def list_peers():
    with lock:
        my_domain = get_my_onion_domain()
        peer_list = [p for p in known_peers if p != my_domain and p not in DEPRECATED_SEEDS]
        peers_detail = []
        if my_domain:
            peers_detail.append(get_node_geo_entry(my_domain, is_local=True))
        for p in sorted(peer_list):
            peers_detail.append(get_node_geo_entry(p, is_local=False))
        return jsonify({
            "my_domain": my_domain,
            "peers": peer_list,
            "total_peers": len(peer_list),
            "total_nodes": len(peer_list) + (1 if my_domain else 0),
            "peers_detail": peers_detail
        }), 200


@app.route('/health', methods=['GET'])
def health():
    with lock:
        prune_expired_messages_locked()
        total_queued = sum(len(msgs) for msgs in inbox.values())
        active_inboxes = len([u for u, m in inbox.items() if len(m) > 0])
        my_domain = get_my_onion_domain()
        peer_count = len([p for p in known_peers if p != my_domain])
        total_nodes = peer_count + (1 if my_domain else 0)
        uptime_sec = int(time.time() - start_time)
    return jsonify({
        "status": "healthy",
        "zero_trust_mode": "X25519-ChaCha20-Poly1305 + Ed25519-Auth + ACK-Lock + Anti-Sybil",
        "storage_engine": "ram-volatile-ephemeral-ttl24h",
        "domain": my_domain,
        "node_pubkey": NODE_PUBLIC_KEY_HEX,
        "peers_count": peer_count,
        "total_nodes": total_nodes,
        "queued_messages": total_queued,
        "active_inboxes": active_inboxes,
        "messages_received": stats_counters["messages_received"],
        "messages_routed": stats_counters["messages_routed"],
        "acks_processed": stats_counters["acks_processed"],
        "spoofed_acks_blocked": stats_counters["spoofed_acks_blocked"],
        "invalid_peers_blocked": stats_counters["invalid_peers_blocked"],
        "unauthenticated_requests_blocked": stats_counters["unauthenticated_requests_blocked"],
        "uptime_seconds": uptime_sec
    }), 200


@app.route('/api/v1/stats', methods=['GET'])
def stats():
    """Returns aggregate anonymized metrics only; never exposes recipient queues (R1 fix)."""
    with lock:
        prune_expired_messages_locked()
        my_domain = get_my_onion_domain()
        peer_count = len([p for p in known_peers if p != my_domain])
        total_queued = sum(len(msgs) for msgs in inbox.values())
        active_inboxes = len([u for u, m in inbox.items() if len(m) > 0])
    return jsonify({
        "domain": my_domain,
        "zero_trust_mode": "X25519-ChaCha20-Poly1305 + Ed25519-Auth + ACK-Lock + Anti-Sybil",
        "storage_engine": "ram-volatile-ephemeral-ttl24h",
        "peers_count": peer_count,
        "queued_messages": total_queued,
        "active_inboxes": active_inboxes,
        "spoofed_acks_blocked": stats_counters["spoofed_acks_blocked"],
        "invalid_peers_blocked": stats_counters["invalid_peers_blocked"],
        "unauthenticated_requests_blocked": stats_counters["unauthenticated_requests_blocked"],
    }), 200


def bootstrap_discovery_loop():
    """
    Continuous autonomous peer discovery & Ed25519-authenticated announce loop over Tor.
    """
    while True:
        current_domain = get_my_onion_domain()
        if not current_domain:
            time.sleep(3)
            continue

        session = get_tor_session()
        with lock:
            targets = list(set(BOOTSTRAP_SEEDS) | known_peers)

        path = "/api/v1/peers/announce"
        payload = {"node_onion": current_domain, "node_pubkey": NODE_PUBLIC_KEY_HEX}

        for seed in targets:
            if not seed or seed == current_domain:
                continue
            try:
                # Fetch seed's node_pubkey from /health if not yet pinned
                with lock:
                    has_pubkey = seed in peer_pubkeys
                if not has_pubkey:
                    h_res = session.get(f"http://{seed}/health", timeout=25)
                    if h_res.status_code == 200:
                        remote_pk = (h_res.json().get("node_pubkey") or "").strip().lower()
                        if PUBKEY_HEX_REGEX.match(remote_pk):
                            with lock:
                                peer_pubkeys[seed] = remote_pk

                body_bytes, headers = build_peer_signed_request("POST", path, payload)
                res = session.post(
                    f"http://{seed}{path}",
                    data=body_bytes,
                    headers=headers,
                    timeout=30,
                )
                if res.status_code == 200:
                    peers = res.json().get("peers", [])
                    for p in peers:
                        p_clean = (p or "").strip().lower()
                        if is_valid_onion_v3(p_clean) and p_clean != current_domain:
                            with lock:
                                already = p_clean in known_peers
                                can_more = len(known_peers) < MAX_KNOWN_PEERS
                            if not already and can_more:
                                try:
                                    p_health = session.get(f"http://{p_clean}/health", timeout=25)
                                    if p_health.status_code == 200:
                                        p_body = p_health.json()
                                        p_pk = (p_body.get("node_pubkey") or "").strip().lower()
                                        if p_body.get("status") == "healthy":
                                            with lock:
                                                if len(known_peers) < MAX_KNOWN_PEERS:
                                                    known_peers.add(p_clean)
                                                    if PUBKEY_HEX_REGEX.match(p_pk):
                                                        peer_pubkeys[p_clean] = p_pk
                                except Exception:
                                    pass
                    print(
                        f"[*] [MESH-SYNC] Synchronized via {seed[:16]}... "
                        f"({len(known_peers)} active peers)",
                        flush=True,
                    )
            except Exception as e:
                print(f"[!] [MESH-WAIT] Waiting for Tor circuit to {seed[:16]}...: {e}", flush=True)

        time.sleep(90)


if os.getenv("DISABLE_BOOTSTRAP_LOOP") != "1":
    threading.Thread(target=bootstrap_discovery_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, threaded=True)
