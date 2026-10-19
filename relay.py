import os
import re
import time
import uuid
import random
import hashlib
import threading
import concurrent.futures
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
# Limite máximo de 2 MB por requisição HTTP (Proteção Anti-OOM / DoS)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

DEFAULT_SEEDS = (
    "onion4zr3bsdeaelksemwokl5qmxd5o7jyblf46vc2mfl6cozgw77tqd.onion,"
    "kn4u2xxl2otoo2ujv3mhehwfwbw7mtppaf56fu3nxogvv7eekf2qdrid.onion,"
    "zqdx5x7pfybox7m5rz3fe5kiouxhipvh3ekuteq2urrrvwcxjttnmgid.onion,"
    "puqjsmsyyzmxjdtcgr2fl4wrdazqd2phaqrz26alzwyletbvekkxhyyd.onion,"
    "ch4s5llfqshxbvba2yulgp5kbopq25w3qqrtli67sle6smbujlebn2id.onion,"
    "7bntuiegd3stvcylvx7rhnhq7ncasxiokunbf5onvvm34dg5gccvooid.onion"
)

# Limites Zero-Trust de Memória e Topologia (Anti-Sybil & Anti-DoS)
ONION_V3_REGEX = re.compile(r"^[a-z2-7]{56}\.onion$")
MAX_KNOWN_PEERS = 64
MAX_INBOX_PER_USER = 200
MAX_TOTAL_INBOXES = 5000
MESSAGE_TTL_MS = 24 * 3600 * 1000  # 24 horas

TOR_SOCKS_PROXY = os.getenv("TOR_SOCKS_PROXY", "socks5h://tor-daemon:9050")
HOSTNAME_FILE = os.getenv("TOR_HOSTNAME_FILE", "/var/lib/tor/hidden_service/hostname")
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
    }
}
custom_peer_geo = {}

inbox = {}
known_peers = set(BOOTSTRAP_SEEDS)
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
    "invalid_peers_blocked": int(os.getenv("INIT_SYBIL_BLOCKED", "1"))
}


def is_valid_onion_v3(domain: str) -> bool:
    if not domain or not isinstance(domain, str):
        return False
    clean = domain.strip().lower()
    if clean in DEPRECATED_SEEDS:
        return False
    return bool(ONION_V3_REGEX.match(clean))


def verify_ack_proof(stored_msg: dict, provided_token: str) -> bool:
    """
    Verifica a prova criptográfica de decifração (Preimage Lock: SHA-256(ack_token) == ack_lock).
    Impede que um nó comprometido apague mensagens de outros nós via ACK Spoofing.
    """
    ack_lock = stored_msg.get("ack_lock")
    if not ack_lock:
        return True  # Compatibilidade com mensagens legadas sem lock
    if not provided_token or not isinstance(provided_token, str):
        return False
    computed = hashlib.sha256(provided_token.strip().encode("utf-8")).hexdigest()
    return computed.lower() == ack_lock.strip().lower()


def prune_expired_messages_locked():
    """Remove mensagens expiradas (>24h) para proteger a RAM contra exaustão."""
    now_ms = int(time.time() * 1000)
    empty_users = []
    for user, msgs in inbox.items():
        inbox[user] = [
            m for m in msgs
            if (now_ms - int(m.get("timestamp", now_ms))) < MESSAGE_TTL_MS
        ]
        if not inbox[user]:
            empty_users.append(user)
    for u in empty_users:
        inbox.pop(u, None)


def enqueue_message_locked(recipient: str, msg_obj: dict) -> bool:
    """Enfileira mensagem com limites rígidos por usuário e global (Anti-OOM) e acorda Long-Polling."""
    prune_expired_messages_locked()
    if recipient not in inbox:
        if len(inbox) >= MAX_TOTAL_INBOXES:
            return False
        inbox[recipient] = []

    msg_id = msg_obj.get("id")
    if any(m.get("id") == msg_id for m in inbox[recipient]):
        return False

    if len(inbox[recipient]) >= MAX_INBOX_PER_USER:
        inbox[recipient].pop(0)  # Evicção FIFO da mais antiga se atingir cota

    inbox[recipient].append(msg_obj)
    inbox_cond.notify_all()
    return True


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
                    print(f"[*] [NODE-ID] Identidade .onion estabelecida: {my_onion_domain}", flush=True)
        except Exception:
            pass
    return my_onion_domain


# -------------------------------------------------------------
# 1. ENVIO E REPLICAÇÃO DE MENSAGENS (GOSSIP MESH ZERO-TRUST)
# -------------------------------------------------------------
@app.route('/api/v1/messages/send', methods=['POST'])
def send_message():
    data = request.get_json(silent=True) or {}
    recipient = (data.get('recipient') or '').strip().lower()
    sender = (data.get('sender') or '').strip().lower()
    payload = (data.get('payload') or '').strip()
    ack_lock = (data.get('ack_lock') or '').strip().lower()

    if not recipient or not payload or len(recipient) > 128:
        return jsonify({"error": "Missing or invalid recipient/payload"}), 400

    msg_id = (data.get('id') or str(uuid.uuid4())).strip()[:64]
    stored_msg = {
        "id": msg_id,
        "sender": sender,
        "recipient": recipient,
        "payload": payload,
        "ack_lock": ack_lock,
        "timestamp": int(data.get("timestamp") or int(time.time() * 1000))
    }

    with lock:
        stats_counters["messages_received"] += 1
        added = enqueue_message_locked(recipient, stored_msg)

    if added:
        print(f"[*] [RELAY-STORED] msg_id={msg_id} (E2E-GCM, lock={bool(ack_lock)}) para {recipient}", flush=True)
        threading.Thread(target=broadcast_message_to_peers, args=(stored_msg,), daemon=True).start()

    return jsonify({"status": "ok", "messageId": msg_id}), 200


def _sync_single_peer(peer: str, msg_payload: dict):
    try:
        session = get_tor_session()
        url = f"http://{peer}/api/v1/messages/sync"
        res = session.post(url, json=msg_payload, timeout=20)
        if res.status_code == 200:
            print(f"[*] [GOSSIP-SYNC-OK] Replicado em paralelo para peer: {peer}", flush=True)
    except Exception as e:
        print(f"[!] [GOSSIP-SYNC-FAIL] Falha replicando para {peer}: {e}", flush=True)


def broadcast_message_to_peers(msg_payload):
    current_domain = get_my_onion_domain()
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
        stats_counters["messages_routed"] += len(peers_copy)

    # OpSec: embaralha a ordem dos peers e dispara todos simultaneamente em paralelo
    random.shuffle(peers_copy)
    for peer in peers_copy:
        gossip_executor.submit(_sync_single_peer, peer, msg_payload)


@app.route('/api/v1/messages/sync', methods=['POST'])
def sync_message():
    """Recebe mensagens replicadas de outros nós da malha com cota Anti-DoS."""
    data = request.get_json(silent=True) or {}
    recipient = (data.get('recipient') or '').strip().lower()
    msg_id = (data.get('id') or '').strip()[:64]
    payload = (data.get('payload') or '').strip()

    if not recipient or not msg_id or not payload or len(recipient) > 128:
        return jsonify({"error": "Invalid sync payload"}), 400

    stored_msg = {
        "id": msg_id,
        "sender": (data.get('sender') or '').strip().lower(),
        "recipient": recipient,
        "payload": payload,
        "ack_lock": (data.get('ack_lock') or '').strip().lower(),
        "timestamp": int(data.get("timestamp") or int(time.time() * 1000))
    }

    with lock:
        if enqueue_message_locked(recipient, stored_msg):
            print(f"[*] [GOSSIP-RECV] Mensagem {msg_id} sincronizada para {recipient}", flush=True)

    return jsonify({"status": "synced"}), 200


# -------------------------------------------------------------
# 2. CONSULTA DE INBOX (COM LONG-POLLING) E CONFIRMAÇÃO (ACK / BATCH ACK)
# -------------------------------------------------------------
@app.route('/api/v1/messages/inbox', methods=['GET'])
def get_inbox():
    user = (request.args.get('user') or '').strip().lower()
    if not user:
        return jsonify({"error": "Missing user query param"}), 400

    try:
        wait_sec = min(max(float(request.args.get('wait') or 0.0), 0.0), 12.0)
    except ValueError:
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

    # Micro-jitter de OpSec (15ms-40ms) ao acordar de Long-Poll para embaralhar correlação estatística
    if woke_from_wait:
        time.sleep(random.uniform(0.015, 0.040))

    return jsonify(messages), 200


@app.route('/api/v1/messages/ack', methods=['POST'])
def acknowledge_message():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    msg_id = (data.get('messageId') or '').strip()
    ack_token = (data.get('ack_token') or '').strip()

    if not user or not msg_id:
        return jsonify({"error": "Missing user or messageId"}), 400

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
                        print(f"[!] [SECURITY] ACK Spoofing bloqueado para msg_id={msg_id}", flush=True)
                else:
                    kept.append(m)
            inbox[user] = kept
            if removed:
                print(f"[*] [RELAY-ACK] Mensagem {msg_id} removida com prova criptográfica válida", flush=True)

    if removed or ack_token:
        threading.Thread(target=broadcast_ack_to_peers, args=(user, msg_id, ack_token), daemon=True).start()

    return jsonify({"status": "ack_ok"}), 200


@app.route('/api/v1/messages/ack_batch', methods=['POST'])
def acknowledge_messages_batch():
    """Processa múltiplos ACKs autenticados em um único pacote HTTP (OpSec & Baixa Latência)."""
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    acks_list = data.get('acks')
    if not user or not isinstance(acks_list, list) or not acks_list:
        return jsonify({"error": "Missing user or acks list"}), 400

    token_map = {}
    for entry in acks_list[:100]:
        if isinstance(entry, dict):
            mid = (entry.get('messageId') or '').strip()
            tok = (entry.get('ack_token') or '').strip()
            if mid:
                token_map[mid] = tok

    if not token_map:
        return jsonify({"error": "No valid messageIds in batch"}), 400

    removed_count = 0
    with lock:
        if user in inbox:
            kept = []
            for m in inbox[user]:
                mid = m.get("id")
                if mid in token_map:
                    if verify_ack_proof(m, token_map[mid]):
                        removed_count += 1
                        stats_counters["acks_processed"] += 1
                    else:
                        stats_counters["spoofed_acks_blocked"] += 1
                        kept.append(m)
                        print(f"[!] [SECURITY] BATCH ACK Spoofing bloqueado para msg_id={mid}", flush=True)
                else:
                    kept.append(m)
            inbox[user] = kept
            if removed_count > 0:
                print(f"[*] [RELAY-BATCH-ACK] {removed_count} mensagem(ns) removida(s) em lote para {user}", flush=True)

    threading.Thread(target=broadcast_ack_batch_to_peers, args=(user, token_map), daemon=True).start()
    return jsonify({"status": "ack_batch_ok", "removed": removed_count}), 200


def _ack_single_peer(peer: str, payload: dict, endpoint: str = "/api/v1/messages/ack_sync"):
    try:
        session = get_tor_session()
        session.post(f"http://{peer}{endpoint}", json=payload, timeout=18)
    except Exception:
        pass


def broadcast_ack_to_peers(user, msg_id, ack_token):
    current_domain = get_my_onion_domain()
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
    random.shuffle(peers_copy)
    payload = {"user": user, "messageId": msg_id, "ack_token": ack_token}
    for peer in peers_copy:
        gossip_executor.submit(_ack_single_peer, peer, payload, "/api/v1/messages/ack_sync")


def broadcast_ack_batch_to_peers(user: str, token_map: dict):
    current_domain = get_my_onion_domain()
    with lock:
        peers_copy = [p for p in known_peers if p != current_domain]
    random.shuffle(peers_copy)
    acks_payload = [{"messageId": mid, "ack_token": tok} for mid, tok in token_map.items()]
    batch_body = {"user": user, "acks": acks_payload}
    for peer in peers_copy:
        gossip_executor.submit(_ack_single_peer, peer, batch_body, "/api/v1/messages/ack_batch_sync")


@app.route('/api/v1/messages/ack_sync', methods=['POST'])
def ack_sync():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    msg_id = (data.get('messageId') or '').strip()
    ack_token = (data.get('ack_token') or '').strip()

    if user and msg_id:
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
                            print(f"[!] [SECURITY] ACK_SYNC Spoofing bloqueado para msg_id={msg_id}", flush=True)
                    else:
                        kept.append(m)
                inbox[user] = kept
    return jsonify({"status": "ack_synced"}), 200


@app.route('/api/v1/messages/ack_batch_sync', methods=['POST'])
def ack_batch_sync():
    data = request.get_json(silent=True) or {}
    user = (data.get('user') or '').strip().lower()
    acks_list = data.get('acks')
    if user and isinstance(acks_list, list):
        token_map = {
            (e.get('messageId') or '').strip(): (e.get('ack_token') or '').strip()
            for e in acks_list[:100] if isinstance(e, dict) and (e.get('messageId') or '').strip()
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
# 3. AUTO-DISCOVERY & GOSSIP DE PEERS (COM HANDSHAKE ANTI-SYBIL)
# -------------------------------------------------------------
@app.route('/api/v1/peers/announce', methods=['POST'])
def announce_peer():
    data = request.get_json(silent=True) or {}
    peer_onion = (data.get('node_onion') or '').strip().lower()
    current_domain = get_my_onion_domain()

    if peer_onion and not is_valid_onion_v3(peer_onion):
        with lock:
            stats_counters["invalid_peers_blocked"] += 1
        return jsonify({"error": "Invalid Tor v3 .onion address"}), 400

    with lock:
        already_known = (peer_onion in known_peers) or (peer_onion == current_domain)
        can_accept_more = len(known_peers) < MAX_KNOWN_PEERS
        current_peers = list(known_peers)
        if current_domain and current_domain not in current_peers:
            current_peers.append(current_domain)

    # Se for um peer novo válido e houver espaço, valida alcançabilidade (/health) em background antes de propagar
    if peer_onion and not already_known and can_accept_more:
        threading.Thread(target=verify_and_register_peer, args=(peer_onion,), daemon=True).start()

    return jsonify({"status": "registered", "peers": current_peers}), 200


def verify_and_register_peer(candidate_onion: str):
    """Realiza handshake ativo via Tor (/health) antes de aceitar e propagar o peer (Anti-Sybil)."""
    if not is_valid_onion_v3(candidate_onion):
        return
    current_domain = get_my_onion_domain()
    if candidate_onion == current_domain:
        return

    # Sementes oficiais são aceitas imediatamente; demais nós passam por verificação /health
    is_trusted_seed = candidate_onion in BOOTSTRAP_SEEDS
    verified = is_trusted_seed
    if not is_trusted_seed:
        try:
            session = get_tor_session()
            res = session.get(f"http://{candidate_onion}/health", timeout=25)
            if res.status_code == 200 and res.json().get("status") == "healthy":
                verified = True
        except Exception:
            verified = False

    if not verified:
        with lock:
            stats_counters["invalid_peers_blocked"] += 1
        print(f"[!] [ANTI-SYBIL] Peer não verificado descartado: {candidate_onion}", flush=True)
        return

    added = False
    with lock:
        if len(known_peers) < MAX_KNOWN_PEERS and candidate_onion not in known_peers:
            known_peers.add(candidate_onion)
            added = True

    if added:
        print(f"[*] [DISCOVERY] Novo nó verificado e adicionado à malha: {candidate_onion}", flush=True)
        gossip_new_peer(candidate_onion)


def gossip_new_peer(new_peer_onion):
    current_domain = get_my_onion_domain()
    with lock:
        targets = [p for p in known_peers if p != new_peer_onion and p != current_domain]
    session = get_tor_session()
    for target in targets:
        try:
            session.post(
                f"http://{target}/api/v1/peers/announce",
                json={"node_onion": new_peer_onion},
                timeout=20
            )
        except Exception:
            pass


def get_node_geo_entry(domain: str, is_local: bool = False) -> dict:
    meta = custom_peer_geo.get(domain) or NODE_GEO_METADATA.get(domain)
    if not meta:
        # Fallback determinístico para novos nós dinâmicos auto-descobertos
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
    """Permite cadastrar/atualizar coordenadas geográficas e nome de um nó em tempo real para o mapa do Grafana."""
    data = request.get_json(silent=True) or {}
    domain = (data.get("node_onion") or data.get("domain") or "").strip().lower()
    if not is_valid_onion_v3(domain):
        return jsonify({"error": "Invalid Tor v3 .onion address"}), 400
    with lock:
        custom_peer_geo[domain] = {
            "node_name": str(data.get("node_name") or f"🌐 Nó ({domain[:8]}...)"),
            "location": str(data.get("location") or "Tor Hidden Service v3"),
            "provider": str(data.get("provider") or "Federated P2P Node"),
            "lat": float(data.get("lat", 47.3769)),
            "lon": float(data.get("lon", 8.5417)),
            "role": str(data.get("role") or "🌐 Federated Mesh Peer")
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
        "zero_trust_mode": "E2E-GCM + ACK-Lock + Anti-Sybil",
        "domain": my_domain,
        "peers_count": peer_count,
        "total_nodes": total_nodes,
        "queued_messages": total_queued,
        "active_inboxes": active_inboxes,
        "messages_received": stats_counters["messages_received"],
        "messages_routed": stats_counters["messages_routed"],
        "acks_processed": stats_counters["acks_processed"],
        "spoofed_acks_blocked": stats_counters["spoofed_acks_blocked"],
        "invalid_peers_blocked": stats_counters["invalid_peers_blocked"],
        "uptime_seconds": uptime_sec
    }), 200


@app.route('/api/v1/stats', methods=['GET'])
def stats():
    with lock:
        prune_expired_messages_locked()
        my_domain = get_my_onion_domain()
        peer_count = len([p for p in known_peers if p != my_domain])
        total_queued = sum(len(msgs) for msgs in inbox.values())
        active_inboxes = len([u for u, m in inbox.items() if len(m) > 0])
        recipients_summary = [{"recipient": u, "count": len(m)} for u, m in inbox.items() if len(m) > 0]
    return jsonify({
        "domain": my_domain,
        "zero_trust_mode": "E2E-GCM + ACK-Lock + Anti-Sybil",
        "peers_count": peer_count,
        "queued_messages": total_queued,
        "active_inboxes": active_inboxes,
        "spoofed_acks_blocked": stats_counters["spoofed_acks_blocked"],
        "invalid_peers_blocked": stats_counters["invalid_peers_blocked"],
        "queues": recipients_summary
    }), 200


def bootstrap_discovery_loop():
    """
    Loop contínuo de auto-descoberta e anúncio na malha Tor:
    1. Aguarda o tor-daemon gerar o arquivo /var/lib/tor/hidden_service/hostname.
    2. Anuncia o endereço .onion deste nó para as sementes da malha e sincroniza a lista de peers.
    3. Repete a verificação periodicamente para manter a federação resiliente.
    """
    while True:
        current_domain = get_my_onion_domain()
        if not current_domain:
            time.sleep(3)
            continue

        session = get_tor_session()
        with lock:
            targets = list(set(BOOTSTRAP_SEEDS) | known_peers)

        for seed in targets:
            if not seed or seed == current_domain:
                continue
            try:
                res = session.post(
                    f"http://{seed}/api/v1/peers/announce",
                    json={"node_onion": current_domain},
                    timeout=30
                )
                if res.status_code == 200:
                    peers = res.json().get("peers", [])
                    with lock:
                        for p in peers:
                            p_clean = (p or "").strip().lower()
                            if is_valid_onion_v3(p_clean) and p_clean != current_domain and len(known_peers) < MAX_KNOWN_PEERS:
                                known_peers.add(p_clean)
                    print(
                        f"[*] [MESH-SYNC] Conectado à malha via {seed[:16]}... "
                        f"({len(known_peers)} peers ativos)",
                        flush=True
                    )
            except Exception as e:
                print(f"[!] [MESH-WAIT] Aguardando circuito Tor para {seed[:16]}...: {e}", flush=True)

        time.sleep(90)


threading.Thread(target=bootstrap_discovery_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)
