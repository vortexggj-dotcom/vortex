
import json
import os
import tempfile
import time

import streamlit as st
from google import genai
from google.genai import types

# Se aparecer erro de "modelo nao encontrado", troque este nome
# por um modelo Flash atual em aistudio.google.com
MODELO = "gemini-3.8-flash"
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
        st.markdown(f"**{titulo}**")
        for i in itens:
            st.markdown(f"- {i}")


def mostrar_rede(rede, d):
    st.markdown(f"**Duração ideal:** {d.get('duracao_ideal', '-')}")
    st.markdown(f"**Melhor horário (geral):** {d.get('melhor_horario', '-')}")
    st.markdown("**Títulos**")
    for t in d.get("titulos", []):
        st.code(t, language=None, wrap_lines=True)
    st.markdown("**Descrições**")
    for t in d.get("descricoes", []):
        st.code(t, language=None, wrap_lines=True)
    st.markdown("**Hashtags**")
    st.code(" ".join(d.get("hashtags", [])), language=None, wrap_lines=True)
    st.markdown("**Palavras-chave**")
    st.code(", ".join(d.get("palavras_chave", [])), language=None, wrap_lines=True)
    lista("Chamadas para ação", d.get("chamadas_para_acao"))
    lista("Sugestões de capa", d.get("sugestoes_capa"))
    if rede == "Kwai":
        aviso = "Kwai: sem API pública de publicação que eu conheça. "
        aviso += "Use os textos acima e poste manualmente."
        st.info(aviso)


def mostrar_resultado(r):
    nota = int(r.get("nota", 0))
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("Nota de viralização", f"{nota}/100")
    c2.metric("Classificação", classificar(nota))
    st.progress(min(max(nota, 0), 100) / 100)
    prob = r.get("probabilidade_bom_desempenho", "-")
    st.write(f"**Probabilidade estimada de bom desempenho:** {prob}")
    st.write(r.get("resumo", ""))

    with st.expander("Relatório completo", expanded=True):
        for k, v in r.get("analise", {}).items():
            nome = k.replace("_", " ").capitalize()
            st.markdown(f"**{nome}:** {v}")
        lista("✅ Pontos positivos", r.get("pontos_positivos"))
        lista("⚠️ Pontos negativos", r.get("pontos_negativos"))
        lista("📉 Por que pode flopar", r.get("motivos_flop"))
        lista("🔧 O que corrigir", r.get("correcoes"))
        lista("⏱️ Como melhorar a retenção", r.get("sugestoes_retencao"))
        lista("✂️ Sugestões de edição", r.get("sugestoes_edicao"))
        if r.get("gancho_sugerido"):
            st.markdown("**🎣 Gancho sugerido**")
            st.code(r["gancho_sugerido"], language=None)

    st.subheader("Conteúdo por plataforma")
    abas = st.tabs(REDES)
    for aba, rede in zip(abas, REDES):
        with aba:
            mostrar_rede(rede, r.get("redes", {}).get(rede, {}))


def principal():
    st.set_page_config(page_title="Vortex", page_icon="🌀")
    st.title("🌀 Vortex")
    st.caption(
        "Analise seu vídeo e prepare a publicação. "
        "A nota é uma estimativa, não uma garantia."
    )

    arquivo = st.file_uploader("ENVIAR VÍDEO", type=["mp4", "mov", "webm", "mkv"])
    if arquivo:
        st.video(arquivo)

    clicou = st.button("ANALISAR VÍDEO", type="primary", disabled=arquivo is None)
    if clicou:
        with st.spinner("Analisando... pode levar de 1 a 3 minutos."):
            try:
                st.session_state["r"] = analisar(arquivo)
            except Exception as e:
                st.session_state.pop("r", None)
                st.error(f"Erro: {e}")

    r = st.session_state.get("r")
    if r:
        mostrar_resultado(r)


principal()
