# 🧅 OnionTalk — Servidor Federado (Relay Node)

Este pacote contém tudo o que você precisa para rodar um **Nó Federado do OnionTalk** na sua própria casa (PC, Mini-PC, Raspberry Pi, NAS ou VPS) e fortalecer a malha descentralizada de mensagens criptografadas.

---

## 💡 Por que qualquer pessoa pode rodar em casa?

* **Zero Portas Abertas no Roteador (Funciona em CGNAT)**: Como o nó opera exclusivamente como um **Tor Hidden Service v3 (`.onion`)**, o container abre conexões de saída para a rede Tor. Você **não** precisa configurar redirecionamento de portas (*Port Forwarding*), nem ter IP fixo ou DNS público.
* **Zero-Knowledge & Apenas em Memória RAM**: O servidor atua apenas como correio cego (*store-and-forward*) de envelopes já criptografados e os apaga da memória RAM imediatamente após o recebimento (`ACK`) pelo destinatário. Nenhum histórico de conversa é gravado em disco.
* **Descoberta Automática (Gossip Mesh)**: Ao iniciar, seu servidor gera automaticamente uma identidade `.onion` exclusiva e se anuncia para os **Nós Semente (Seed Nodes)** da rede. Em poucos segundos, todos os outros servidores da malha passam a conhecer e sincronizar com o seu nó.

---

## 📦 Estrutura da Pasta

```text
server/
├── docker-compose.yml   # Orquestração dos containers (Tor Hidden Service + Relay API)
├── Dockerfile           # Imagem leve Python 3.11 + Gunicorn do Relay
├── relay.py             # Motor de roteamento, fila em RAM e Gossip Mesh
├── requirements.txt     # Dependências mínimas (Flask, Requests+SOCKS, Gunicorn)
├── torrc                # Configuração do serviço oculto Tor v3 e proxy SOCKS5
└── README.md            # Este guia de instalação e operação
```

---

## 🛠️ Pré-requisitos

Você só precisa ter instalado na máquina:
* **Docker** e **Docker Compose**
  * **Windows / macOS**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  * **Linux (Ubuntu / Debian / Raspberry Pi OS)**:
    ```bash
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    ```

---

## 🚀 Passo a Passo: Subindo seu Servidor (1 Comando)

Abra o terminal (PowerShell no Windows ou Bash no Linux/macOS) dentro desta pasta `server` e execute:

```bash
docker compose up -d --build
```

### O que acontece automaticamente nos primeiros 30 a 60 segundos:
1. O container **`oniontalk-tor`** inicia o daemon Tor e gera o par de chaves criptográficas Ed25519 do seu novo endereço `.onion` v3 (salvo no volume persistente `tor_keys`).
2. O container **`oniontalk-relay`** sobe a API de mensagens na porta `8080`.
3. O loop de *Auto-Discovery* lê o seu novo endereço `.onion` e faz o *handshake* automático com os nós sementes da malha (`BOOTSTRAP_SEEDS`), integrando seu servidor à federação global do OnionTalk.

---

## 🔍 Como Ver o Endereço `.onion` e o Status do seu Nó

### 1. Consultar a Saúde e o Endereço `.onion` do seu Servidor

No **Linux / macOS**:
```bash
curl http://localhost:8080/health
```

No **Windows (PowerShell)**:
```powershell
Invoke-RestMethod http://localhost:8080/health
```

**Exemplo de resposta quando o nó já está sincronizado na malha:**
```json
{
  "status": "healthy",
  "domain": "seu_endereco_gerado_automaticamente_56_chars.onion",
  "peers_count": 4,
  "total_nodes": 5,
  "queued_messages": 0,
  "active_inboxes": 0,
  "messages_received": 12,
  "messages_routed": 48,
  "acks_processed": 12,
  "uptime_seconds": 340
}
```
> **Nota**: Na primeira inicialização, o Tor pode levar de **30 a 90 segundos** para construir os circuitos iniciais até que `peers_count` suba para `4` (ou mais).

### 2. Listar todos os Servidores (Peers) Conectados na Malha

No **Linux / macOS**:
```bash
curl http://localhost:8080/api/v1/peers/list
```

No **Windows (PowerShell)**:
```powershell
Invoke-RestMethod http://localhost:8080/api/v1/peers/list
```

### 3. Acompanhar os Logs em Tempo Real

```bash
docker compose logs -f
```
Você verá mensagens como:
* `[*] [NODE-ID] Identidade .onion estabelecida: xxxx...onion`
* `[*] [MESH-SYNC] Conectado à malha via onion4zr3bsdeael... (4 peers ativos)`
* `[*] [GOSSIP-SYNC-OK] Replicado para peer: ...`

---

## ⚙️ Configurações Opcionais

Caso a porta `8080` já esteja em uso na sua máquina, você pode escolher outra porta local sem afetar a comunicação Tor (que sempre usa a porta virtual `80` dentro da rede `.onion`):

No **Linux / macOS**:
```bash
RELAY_PORT=8090 docker compose up -d
```

No **Windows (PowerShell)**:
```powershell
$env:RELAY_PORT="8090"; docker compose up -d
```

---

## 💾 Backup da Identidade `.onion` do seu Servidor

A chave privada do endereço `.onion` do seu servidor fica salva automaticamente no volume Docker chamado `tor_keys`.
* Se você reiniciar o computador ou rodar `docker compose restart`, **o seu endereço `.onion` continua o mesmo**.
* **Atenção**: Evite rodar `docker compose down -v` (com a flag `-v`), pois isso apaga o volume `tor_keys` e fará o Tor gerar um novo endereço `.onion` na próxima subida.

---

## 🛑 Comandos Úteis de Manutenção

| Ação | Comando |
| :--- | :--- |
| **Iniciar / Atualizar servidor** | `docker compose up -d --build` |
| **Ver status dos containers** | `docker compose ps` |
| **Ver logs em tempo real** | `docker compose logs -f` |
| **Reiniciar o servidor** | `docker compose restart` |
| **Parar o servidor (mantendo a chave `.onion`)** | `docker compose stop` |
