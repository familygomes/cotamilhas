import streamlit as st
import pytesseract
from PIL import Image
import re
import datetime
import pandas as pd
import os

# --- Config OCR (Streamlit Cloud) ---
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # binário via packages.txt

# --- Persistência ---
HISTORICO_ARQ = "cotacoes_historico.csv"
if not os.path.exists(HISTORICO_ARQ):
    pd.DataFrame(columns=["Data/Hora", "Origem", "Destino", "Milhas", "Taxa", "Milheiro", "Valor Final"]).to_csv(HISTORICO_ARQ, index=False)

st.set_page_config(page_title="CotaMilhas Express", layout="centered")
st.title("🛫 CotaMilhas Express")
st.markdown("Envie o print da sua tela Smiles, insira o valor do milheiro e receba a cotação da viagem com margem.")

# ---------- Utils ----------
def _to_float(num_str: str) -> float:
    if not num_str:
        return 0.0
    s = str(num_str).strip().replace("\xa0", " ")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def extrair_milhas(texto: str) -> float:
    # pega TODAS as ocorrências "... milhas" e escolhe a MAIOR (ex.: 58.400 do resumo)
    padrao = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    numeros = [int(n.replace(".", "")) for n in padrao.findall(texto)]
    return float(max(numeros)) if numeros else 0.0

def extrair_taxa(texto: str) -> float:
    m = re.search(r"Taxa\s*de\s*embarque.*?R\$\s*([\d\.,]+)", texto, re.IGNORECASE | re.DOTALL)
    if m:
        return _to_float(m.group(1))
    m = re.search(r"milhas\s*\+\s*R\$\s*([\d\.,]+)", texto, re.IGNORECASE)
    if m:
        return _to_float(m.group(1))
    valores = [_to_float(x) for x in re.findall(r"R\$\s*([\d\.,]+)", texto, re.IGNORECASE)]
    candidatos = [v for v in valores if v >= 150]  # tipicamente 150–300
    return min(candidatos) if candidatos else 0.0

def extrair_rota(texto: str):
    m = re.search(r"\b([A-Z]{3})\s*\d{1,2}h\d{2}\s*([A-Z]{3})\s*\d{1,2}h\d{2}", texto)
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,20}\b([A-Z]{3})\b", texto)
    if m2 and m2.group(1) != "GOL":  # evita capturar 'GOL'
        return m2.group(1), m2.group(2)
    return "-", "-"

# ---------- UI ----------
uploaded_file = st.file_uploader("📷 Envie o print da passagem:", type=["png", "jpg", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print recebido", use_column_width=True)

    try:
        texto = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        st.error("OCR indisponível. Garanta o 'packages.txt' com tesseract-ocr e tesseract-ocr-por.")
        st.stop()

    milhas_ocr = extrair_milhas(texto)
    taxa_ocr = extrair_taxa(texto)
    origem_ocr, destino_ocr = extrair_rota(texto)

    st.markdown("---")
    st.subheader("🔢 Dados extraídos:")
    st.write(f"- Origem: {origem_ocr}")
    st.write(f"- Destino: {destino_ocr}")
    st.write(f"- Milhas detectadas: {milhas_ocr if milhas_ocr else 'Não encontrado'}")
    st.write(f"- Taxa de embarque: R$ {taxa_ocr if taxa_ocr else 'Não encontrada'}")

    # Correções rápidas (se necessário)
    st.markdown("### ✍️ Ajustes manuais (se necessário)")
    origem = st.text_input("Origem (IATA)", value=origem_ocr or "-")
    destino = st.text_input("Destino (IATA)", value=destino_ocr or "-")
    milhas = st.number_input("Milhas totais", value=float(milhas_ocr) if milhas_ocr else 0.0, step=100.0)
    taxa = st.number_input("Taxa de embarque (R$)", value=float(taxa_ocr) if taxa_ocr else 0.0, step=1.0, format="%.2f")

    if milhas > 0 and taxa >= 0:
        milheiro = st.number_input("💸 Informe o valor do milheiro (R$ por 1000 milhas):", min_value=10.0, max_value=200.0, step=0.5)
        if milheiro:
            valor_milhas = (milhas / 1000.0) * milheiro
            subtotal = valor_milhas + taxa
            valor_final = round(subtotal * 1.15, 2)

            st.markdown("---")
            st.subheader("💰 Cotação Final")
            st.markdown(f"**Valor total do bilhete (com 15% de margem): R$ {valor_final:.2f}**")

            novo_registro = pd.DataFrame([{
                "Data/Hora": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "Origem": origem, "Destino": destino,
                "Milhas": milhas, "Taxa": taxa, "Milheiro": milheiro,
                "Valor Final": valor_final
            }])

            historico = pd.read_csv(HISTORICO_ARQ)
            historico = pd.concat([novo_registro, historico], ignore_index=True)
            historico.to_csv(HISTORICO_ARQ, index=False)

            with st.expander("📊 Ver histórico de cotações"):
                st.dataframe(historico)
else:
    st.info("Envie um print para iniciar a cotação.")
