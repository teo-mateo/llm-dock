# LLM-Dock

A dashboard for managing local LLM inference services with Docker Compose. Supports llama.cpp (GGUF models) and vLLM (HuggingFace models) with automatic GPU detection, model discovery, and Open WebUI integration.

## Features

- **Model Discovery** - Automatically scans HuggingFace cache and local directories for models
- **Multi-Engine Support** - llama.cpp for GGUF models, vLLM for safetensors/HuggingFace models
- **GPU Monitoring** - Real-time nvidia-smi stats in the dashboard
- **Service Management** - Create, start, stop, restart services via web UI or API
- **Open WebUI Integration** - Auto-registers services as OpenAI-compatible endpoints
- **Port Management** - Automatic port assignment in the 3300-3400 range

## Prerequisites

- Linux (tested on Ubuntu 22.04)
- Docker with Compose v2 (`docker compose`, not `docker-compose`)
- Python 3.10+
- NVIDIA GPU with CUDA drivers
- nvidia-container-toolkit

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/llm-dock.git
cd llm-dock

# Run setup (creates venv, installs deps, generates token, starts Open WebUI)
./setup.sh

# Build llama.cpp Docker image (if using GGUF models)
./build-llamacpp.sh

# Start the dashboard
cd dashboard
source venv/bin/activate
python app.py
```

**Access points:**
- Dashboard: http://localhost:3399
- Open WebUI: http://localhost:3300

## Project Structure

```
llm-dock/
├── setup.sh                    # Initial setup script
├── build-llamacpp.sh           # Build llama.cpp Docker image
├── docker-compose.yml          # Docker Compose configuration
│
├── dashboard/
│   ├── app.py                  # Flask API server
│   ├── compose_manager.py      # Docker Compose management
│   ├── flag_metadata.py        # Engine flag definitions
│   ├── model_discovery.py      # Model scanning
│   ├── service_templates.py    # Service generators
│   ├── openwebui_integration.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── templates/              # Jinja2 service templates
│   │   ├── llamacpp.j2
│   │   └── vllm.j2
│   └── static/                 # Pre-built frontend
│
└── llama.cpp/
    └── Dockerfile              # Custom llama.cpp build
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` in the dashboard directory:

```bash
cd dashboard
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `DASHBOARD_TOKEN` | API authentication token | (required) |
| `DASHBOARD_PORT` | Dashboard port | 3399 |
| `DASHBOARD_HOST` | Dashboard bind address | 127.0.0.1 |
| `COMPOSE_PROJECT_NAME` | Docker project name | llm-dock |
| `COMPOSE_FILE` | Path to docker-compose.yml | ../docker-compose.yml |
| `LOG_LEVEL` | Logging level | INFO |

### Model Paths

The dashboard automatically scans:
- `~/.cache/huggingface/hub/` - HuggingFace cache
- `~/.cache/models/` - Generic GGUF directory

To add custom paths, modify `model_discovery.py`.

## API Reference

All endpoints (except `/api/health`) require Bearer token authentication:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:3399/api/services
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check (no auth) |
| `/api/gpu` | GET | GPU statistics |
| `/api/system/info` | GET | System info + discovered models |
| `/api/services` | GET | List all services |
| `/api/services/<name>/start` | POST | Start a service |
| `/api/services/<name>/stop` | POST | Stop a service |
| `/api/services/<name>/restart` | POST | Restart a service |
| `/api/services/<name>/logs` | GET | Get service logs |
| `/api/services/create` | POST | Create a new service |
| `/api/v2/services/<name>` | GET | Get service config |
| `/api/v2/services/<name>` | PUT | Update service |
| `/api/v2/services/<name>` | DELETE | Delete service |
| `/api/v2/flag-metadata/<type>` | GET | Get engine flags |

### Creating a Service

```bash
curl -X POST http://localhost:3399/api/services/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "engine": "llamacpp",
    "model_data": {
      "name": "unsloth/Qwen2.5-7B-Instruct-GGUF",
      "files": [{"name": "model-Q4_K_M.gguf", "path": "/path/to/model.gguf"}]
    },
    "options": {
      "model_path": "/hf-cache/hub/.../model.gguf",
      "context_length": "32000",
      "gpu_layers": "999"
    }
  }'
```

## Supported Engines

### llama.cpp
- Format: GGUF files
- Multimodal: Supported (mmproj files)
- Image: Custom build (`my-llamacpp`)

Available flags:
- `-c` / `context_length` - Context length
- `-ngl` / `gpu_layers` - GPU layers (999 = all)
- `-b` / `batch_size` - Batch size
- `--flash-attn` - Flash attention
- `--jinja` - Jinja template support
- `--reasoning-format` - Reasoning mode

### vLLM
- Format: safetensors (HuggingFace models)
- Image: `vllm/vllm-openai:v0.11.0`

Available flags:
- `--max-model-len` - Context length
- `--gpu-memory-utilization` - GPU memory fraction
- `--max-num-batched-tokens` - Batch size
- `--max-num-seqs` - Max concurrent sequences
- `--enable-prefix-caching` - Prefix caching
- `--tensor-parallel-size` - Multi-GPU support

## Building llama.cpp

The `build-llamacpp.sh` script builds a custom llama.cpp Docker image optimized for your GPU:

```bash
./build-llamacpp.sh
```

The script will:
1. Detect your GPU and suggest the optimal CUDA architecture
2. Prompt for confirmation or manual override
3. Build the Docker image (~10-15 minutes)

### CUDA Architectures

| Architecture | GPUs |
|--------------|------|
| 120 | RTX 50 series (Blackwell) |
| 90 | H100, H200 (Hopper) |
| 89 | RTX 40 series (Ada Lovelace) |
| 86 | RTX 30 series, A100, A10 (Ampere) |
| 75 | RTX 20 series, T4 (Turing) |
| 70 | V100 (Volta) |
| 61 | GTX 10 series (Pascal) |

Find your GPU's compute capability: https://developer.nvidia.com/cuda-gpus

## Running as a System Service

Create `/etc/systemd/system/llm-dock.service`:

```ini
[Unit]
Description=LLM-Dock Dashboard
After=network.target docker.service

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/llm-dock/dashboard
Environment=PATH=/path/to/llm-dock/dashboard/venv/bin:/usr/bin
ExecStart=/path/to/llm-dock/dashboard/venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable llm-dock
sudo systemctl start llm-dock
```

## Troubleshooting

### "nvidia-container-toolkit not detected"
Install the NVIDIA Container Toolkit:
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Services not starting
Check Docker logs:
```bash
docker compose logs <service-name>
```

### GPU not detected in container
Verify nvidia-smi works in Docker:
```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## License

MIT License - see [LICENSE](LICENSE) file.
