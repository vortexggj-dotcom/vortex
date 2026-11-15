import json
import os
import tempfile
import time

import streamlit as st
from google import genai
from google.genai import types

# Se aparecer erro de "modelo não encontrado", troque este nome
# por um modelo Flash atual em aistudio.google.com
MODELO = "gemini-2.5-flash"
REDES = ["TikTok", "Kwai", "YouTube Shorts", "Instagram Reels"]

PROMPT = """Você é um especialista em vídeos curtos (TikTok, Kwai, YouTube Shorts, Instagram Reels).
Analise o vídeo anexado com honestidade e rigor. Não elogie sem motivo e NUNCA afirme que o vídeo
vai viralizar ou flopar com certeza: trabalhe com estimativas.
Avalie: qualidade/resolução, força dos 3 primeiros segundos, retenção, ritmo de edição,
legendas e textos na tela, áudio e música, potencial de engajamento e compartilhamento,
clareza e duração ideal. Escreva tudo em português do Brasil.
Não há dados da conta do usuário: os horários sugeridos são gerais e devem ser tratados assim.

Responda SOMENTE com um JSON neste formato:
{
 "nota": inteiro de 0 a 100,
 "probabilidade_bom_desempenho": "faixa estimada, ex.: 'Moderada (30% a 45%)'",
 "resumo": "2 frases",
 "analise": {
  "qualidade_resolucao": "", "gancho_3s": "", "retencao": "", "ritmo_edicao": "",
  "legendas_textos": "", "audio_musica": "", "engajamento_compartilhamento": "",
  "clareza": "", "duracao_ideal": ""
 },
 "pontos_positivos": [],
 "pontos_negativos": [],
 "motivos_flop": [],
 "correcoes": [],
 "sugestoes_retencao": [],
 "gancho_sugerido": "",
 "sugestoes_edicao": [],
 "redes": {
  "TikTok": {"duracao_ideal": "", "titulos": [3 itens], "descricoes": [3 itens],
             "hashtags": [], "palavras_chave": [], "chamadas_para_acao": [],
             "sugestoes_capa": [], "melhor_horario": ""},
  "Kwai": { mesmos campos },
  "YouTube Shorts": { mesmos campos },
  "Instagram Reels": { mesmos campos }
 }
}
Adapte tom, tamanho e hashtags a cada rede."""


def classificar(nota):
    if nota < 40:
        return "Alto risco de baixo desempenho"
    if nota < 60:
        return "Precisa melhorar"
    if nota < 80:
        return "Bom potencial"
    return "Alto potencial de desempenho"


def analisar(arquivo):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    sufixo = os.path.splitext(arquivo.name)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tmp.write(arquivo.getbuffer())
        caminho = tmp.name
    enviado = None
    try:
        enviado = client.files.upload(file=caminho)
        while enviado.state.name == "PROCESSING":
            time.sleep(3)
            enviado = client.files.get(name=enviado.name)
        if enviado.state.name == "FAILED":
            raise RuntimeError("O Gemini não conseguiu processar esse vídeo.")
        resp = client.models.generate_content(
            model=MODELO,
            contents=[enviado, PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.4
            ),
        )
        return json.loads(resp.text)
    finally:
        os.remove(caminho)
        if enviado is not None:
            try:
                client.files.delete(name=enviado.name)
            except Exception:
                pass


def lista(titulo, itens):
    if itens:
        st.markdown(f"*{titulo}*")
        for i in itens:
            st.markdown(f"- {i}")


st.set_page_config(page_title="Vortex", page_icon="🌀")
st.title("🌀 Vortex")
st.caption("Analise seu vídeo e prepare a publicação. A nota é uma estimativa, não uma garantia.")

arquivo = st.file_uploader("ENVIAR VÍDEO", type=["mp4", "mov", "webm", "mkv"])
if arquivo:
    st.video(arquivo)

if st.button("ANALISAR VÍDEO", type="primary", disabled=arquivo is None):
    with st.spinner("Analisando... pode levar de 1 a 3 minutos."):
        try:
            st.session_state["r…
