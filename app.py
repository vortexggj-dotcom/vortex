"""
Vortex - API de análise de vídeos curtos com IA.

Instalação:
    pip install fastapi uvicorn python-multipart opencv-python-headless anthropic

Execução:
    export ANTHROPIC_API_KEY="sua-chave"
    uvicorn vortex_api:app --reload

Teste:
    curl -F "video=@meu_video.mp4" -F "plataformas=tiktok,kwai,shorts,reels" \
         http://localhost:8000/analisar
"""

import base64
import json
import os
import tempfile

import cv2
from anthropic import Anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

MODELO = "claude-sonnet-5-5"
NUM_FRAMES = 6
MAX_LARGURA = 640
MAX_MB = 100

# Regras de cada plataforma, usadas no prompt
PLATAFORMAS = {
    "tiktok": "TikTok: título curto e com gancho (até 90 caracteres), descrição informal, 3 a 5 hashtags misturando populares e de nicho.",
    "kwai": "Kwai: tom popular e direto, emoção e humor, título até 80 caracteres, 3 a 5 hashtags em português.",
    "shorts": "YouTube Shorts: título otimizado para busca (até 100 caracteres), descrição com palavra-chave no início, 3 hashtags incluindo #Shorts.",
    "reels": "Instagram Reels: legenda com gancho na primeira linha, chamada para ação, 5 a 8 hashtags de nicho.",
}

SISTEMA = """Você é um especialista em conteúdo de vídeos curtos verticais.
Você recebe frames de um vídeo, em ordem cronológica, e a duração dele.
Avalie o potencial de desempenho considerando: gancho nos primeiros segundos,
clareza do assunto, qualidade visual, ritmo e potencial de retenção.
Seja honesto e crítico: notas altas (acima de 85) são raras.
Responda SOMENTE com JSON válido, sem markdown, neste formato:
{
  "nota": <inteiro de 0 a 100>,
  "resumo": "<o que acontece no vídeo, em 1 frase>",
  "pontos_fortes": ["..."],
  "melhorias": ["..."],
  "plataformas": {
    "<id da plataforma>": {
      "titulo": "...",
      "descricao": "...",
      "hashtags": ["#..."]
    }
  }
}"""

app = FastAPI(title="Vortex API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrinja ao seu domínio em produção
    allow_methods=["*"],
    allow_headers=["*"],
)
cliente = Anthropic()  # usa ANTHROPIC_API_KEY do ambiente


def extrair_frames(caminho: str, n: int = NUM_FRAMES):
    """Retorna (lista de frames em base64 JPEG, duração em segundos)."""
    cap = cv2.VideoCapture(caminho)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if total <= 0:
        cap.release()
        raise ValueError("Não foi possível ler o vídeo.")

    frames = []
    for i in range(n):
        # distribui os frames ao longo do vídeo (início, meio, fim)
        pos = int(total * (i + 0.5) / n)
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, img = cap.read()
        if not ok:
            continue
        h, w = img.shape[:2]
        if w > MAX_LARGURA:
            img = cv2.resize(img, (MAX_LARGURA, int(h * MAX_LARGURA / w)))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            frames.append(base64.b64encode(buf).decode())
    cap.release()

    if not frames:
        raise ValueError("Nenhum frame extraído do vídeo.")
    return frames, total / fps


def analisar_com_ia(frames, duracao, plataformas):
    conteudo = []
    for i, f in enumerate(frames, 1):
        conteudo.append({"type": "text", "text": f"Frame {i}/{len(frames)}:"})
        conteudo.append(
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": f}}
        )

    regras = "\n".join(f"- {p}: {PLATAFORMAS[p]}" for p in plataformas)
    conteudo.append(
        {
            "type": "text",
            "text": f"Duração do vídeo: {duracao:.1f}s.\n"
            f"Gere os textos em português do Brasil para estas plataformas:\n{regras}",
        }
    )

    resp = cliente.messages.create(
        model=MODELO,
        max_tokens=1500,
        system=SISTEMA,
        messages=[{"role": "user", "content": conteudo}],
    )
    texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    texto = texto.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(texto)


@app.get("/")
def status():
    return {"app": "Vortex", "status": "ok"}


@app.post("/analisar")
def analisar(
    video: UploadFile = File(...),
    plataformas: str = Form("tiktok,kwai,shorts,reels"),
):
    escolhidas = [p.strip().lower() for p in plataformas.split(",") if p.strip() in PLATAFORMAS]
    if not escolhidas:
        raise HTTPException(400, f"Escolha entre: {', '.join(PLATAFORMAS)}")

    sufixo = os.path.splitext(video.filename or "")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tamanho = 0
        while bloco := video.file.read(1024 * 1024):
            tamanho += len(bloco)
            if tamanho > MAX_MB * 1024 * 1024:
                os.unlink(tmp.name)
                raise HTTPException(413, f"Vídeo maior que {MAX_MB} MB.")
            tmp.write(bloco)
        caminho = tmp.name

    try:
        frames, duracao = extrair_frames(caminho)
        resultado = analisar_com_ia(frames, duracao, escolhidas)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except json.JSONDecodeError:
        raise HTTPException(502, "A IA devolveu uma resposta inválida. Tente novamente.")
    finally:
        os.unlink(caminho)

    resultado["duracao_segundos"] = round(duracao, 1)
    return resultado
