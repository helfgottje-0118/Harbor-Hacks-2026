# Harbor LoRa Simulator (no radios needed)

This CLI models incoming LoRa messages. It **does not** transmit LoRa or test Meshtastic, antenna range, delivery, or wireless connectivity.

Run commands from the root of this repository. The simulator uses the Python standard library; no new dependencies are needed.

## AI assistance

Start Ollama on your AI server and install a model, for example `ollama pull llama3.2:3b`.

```bash
python scripts/harbor_lora_simulator.py --mode ai
```

Enter text at `LoRa message >`; type `exit` to quit. To test one message:

```bash
python scripts/harbor_lora_simulator.py --mode ai --once "What should I do if floodwater rises?"
```

If Ollama is on another **private, trusted** machine:

```bash
export OLLAMA_URL=http://YOUR_PRIVATE_OLLAMA_IP:11434
export OLLAMA_MODEL=llama3.2:3b
python scripts/harbor_lora_simulator.py --mode ai
```

Use a VPN such as Tailscale between the competition Raspberry Pi and the home server. Do not expose Ollama's unauthenticated API to the public internet.

## Simulate an incident on the map

Start Harbor's FastAPI backend, then run:

```bash
python scripts/harbor_lora_simulator.py --mode incident --once "Tree blocking road with an injured person"
```

This calls the existing `POST /api/mesh/message` endpoint and **creates a real incident record marked `LORA_SIM`** in Harbor's database. Only test against a local/demo instance or database, not a live emergency-operations deployment.

To target a different Harbor instance, set `HARBOR_URL` to its private base URL or pass `--harbor-url`. Use `--node TEST-PI` to change the simulated sender ID.

## Real radios later

For your Heltec ESP32 LoRa V4 devices, use Meshtastic firmware and a Raspberry Pi USB gateway. Replace the terminal-input adapter with Meshtastic message receiving and return the replies using its serial interface. This CLI is not a hardware driver, and the AI mode is separate from the Harbor website chat API.

## Run tests

```bash
pytest -q tests/test_lora_simulator.py
```
