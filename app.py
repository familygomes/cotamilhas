import streamlit as st
import pytesseract
from PIL import Image
import re
import datetime
import pandas as pd
import os

# Inicializar o banco de dados local
HISTORICO_ARQ = "cotacoes_historico.csv"
if not os.path.exists(HISTORICO_ARQ):
    pd.DataFrame(columns=["Data/Hora", "Origem", "Destino", "Milhas", "Taxa", "Milheiro", "Valor Final"]).to_csv(HISTORICO_ARQ, index=False)

st.set_page_config(page_title="CotaMilhas Express", layout="centered")
st.title("🛫 CotaMilhas Express")
st.markdown("Envie o print da sua tela Smiles, insira o valor do milheiro e receba a cotação da viagem com margem.")

# Upload da imagem
uploaded_file = st.file_uploader("📷 Envie o print da passagem:", type=["png", "jpg", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print recebido", use_column_width=True)

    # OCR para extrair texto
    texto_extraido = pytesseract.image_to_string(image, lang="por")

    # Expressões regulares para encontrar dados
    milhas_match = re.search(r"Total.*?(\d{2,3}[\.\d]*) milhas", texto_extraido.replace(".", "").replace(",", "."))
    taxa_match = re.search(r"Taxa.*?R\$\s*(\d+[\.,]\d{2})", texto_extraido)
    origem = re.search(r"Passagem de ida.*?([A-Z]{3})", texto_extraido)
    destino = re.search(r"Passagem de volta.*?([A-Z]{3})", texto_extraido)

    milhas = float(milhas_match.group(1)) if milhas_match else None
    taxa = float(taxa_match.group(1).replace(",", ".")) if taxa_match else None
    origem_val = origem.group(1) if origem else "-"
    destino_val = destino.group(1) if destino else "-"

    st.markdown("---")
    st.subheader("🔢 Dados extraídos:")
    st.write(f"- Origem: {origem_val}")
    st.write(f"- Destino: {destino_val}")
    st.write(f"- Milhas detectadas: {milhas if milhas else 'Não encontrado'}")
    st.write(f"- Taxa de embarque: R$ {taxa if taxa else 'Não encontrada'}")

    if milhas and taxa:
        milheiro = st.number_input("💸 Informe o valor do milheiro (R$ por 1000 milhas):", min_value=10.0, max_value=100.0, step=0.5)

        if milheiro:
            valor_milhas = (milhas / 1000) * milheiro
            subtotal = valor_milhas + taxa
            valor_final = round(subtotal * 1.15, 2)

            st.markdown("---")
            st.subheader("💰 Cotação Final")
            st.markdown(f"**Valor total do bilhete (com 15% de margem): R$ {valor_final:.2f}**")

            # Salvar histórico
            novo_registro = pd.DataFrame([{
                "Data/Hora": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "Origem": origem_val,
                "Destino": destino_val,
                "Milhas": milhas,
                "Taxa": taxa,
                "Milheiro": milheiro,
                "Valor Final": valor_final
            }])

            historico = pd.read_csv(HISTORICO_ARQ)
            historico = pd.concat([novo_registro, historico], ignore_index=True)
            historico.to_csv(HISTORICO_ARQ, index=False)

            with st.expander("📊 Ver histórico de cotações"):
                st.dataframe(historico)

else:
    st.info("Envie um print para iniciar a cotação.")
