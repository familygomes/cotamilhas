import streamlit as st
from PIL import Image
import pytesseract
import re
import datetime as dt
import pandas as pd
import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# ========== CONFIGURAÇÕES INICIAIS ==========
st.set_page_config(page_title="CotaMilhas Express", layout="centered")

st.title("🛫 CotaMilhas Express")
st.markdown("""
Envie o print da tela (LATAM, GOL ou AZUL) para extrair automaticamente as informações da passagem.  
Depois, edite os campos, adicione a margem e gere o PDF da cotação.
""")

# ========== REGISTRO DAS FONTES ==========
base_dir = os.path.dirname(__file__)
font_regular = os.path.join(base_dir, "DejaVuSans.ttf")
font_bold = os.path.join(base_dir, "DejaVuSans-Bold.ttf")

pdfmetrics.registerFont(TTFont("DejaVuSans", font_regular))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", font_bold))

# ========== UPLOAD DO PRINT ==========
uploaded_file = st.file_uploader("📸 Arraste ou selecione o print da tela", type=["png", "jpg", "jpeg"])

# ========== FUNÇÃO OCR ==========
def extrair_info(image):
    texto = pytesseract.image_to_string(image, lang="por")
    milhas = None
    taxa = None
    origem = "-"
    destino = "-"
    data_ida = "-"
    data_volta = "-"

    # Buscar milhas e taxa
    milhas_match = re.search(r"(\d{1,3}(?:[.\d]{3})*)\s*milhas", texto)
    taxa_match = re.search(r"R\$\s*(\d+[\.,]\d{2})", texto)

    # Buscar cidades
    orig_dest = re.findall(r"\b([A-Z]{3})\b", texto)
    if len(orig_dest) >= 2:
        origem, destino = orig_dest[0], orig_dest[1]

    # Buscar datas
    data_match = re.findall(r"(\d{1,2}\s*de\s*\w+)", texto)
    if len(data_match) >= 1:
        data_ida = data_match[0]
    if len(data_match) >= 2:
        data_volta = data_match[1]

    milhas = float(milhas_match.group(1).replace(".", "")) if milhas_match else 0
    taxa = float(taxa_match.group(1).replace(",", ".")) if taxa_match else 0

    return origem, destino, milhas, taxa, data_ida, data_volta


# ========== INTERFACE ==========
if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print recebido", use_column_width=True)

    origem, destino, milhas, taxa, data_ida, data_volta = extrair_info(image)

    st.markdown("### ✈️ Dados extraídos automaticamente")
    col1, col2 = st.columns(2)
    with col1:
        origem = st.text_input("Origem", origem)
        data_ida = st.text_input("Data de ida", data_ida)
    with col2:
        destino = st.text_input("Destino", destino)
        data_volta = st.text_input("Data de volta", data_volta)

    milhas = st.number_input("Total de milhas", value=milhas, step=100.0)
    taxa = st.number_input("Taxa de embarque (R$)", value=taxa, step=10.0)
    passageiros = st.number_input("Passageiros", min_value=1, max_value=10, value=1)

    milheiro = st.number_input("💸 Valor do milheiro (R$ por 1.000 milhas):", min_value=10.0, max_value=100.0, value=16.0, step=0.5)
    margem = st.number_input("📈 Margem (%)", min_value=0, max_value=100, value=15)

    if st.button("🧮 Calcular Cotação"):
        valor_milhas = (milhas / 1000) * milheiro
        subtotal = (valor_milhas + taxa) * passageiros
        valor_final = round(subtotal * (1 + margem / 100), 2)

        st.success(f"💰 Valor total sugerido: **R$ {valor_final:,.2f}**")

        # Calcular tabela de parcelamento (até 10x, juros fixos 2.9% a.m)
        juros = 2.9 / 100
        tabela = []
        for n in range(1, 11):
            parcela = (valor_final * juros * (1 + juros) ** n) / ((1 + juros) ** n - 1)
            tabela.append((f"{n}x", f"R$ {parcela:,.2f}"))

        df = pd.DataFrame(tabela, columns=["Parcelas", "Valor"])
        st.dataframe(df)

        # Botão gerar PDF
        if st.button("📄 Gerar PDF da Cotação"):
            buffer = io.BytesIO()
            gerar_pdf(
                companhia="LATAM",
                origem=origem,
                destino=destino,
                data_ida=data_ida,
                data_volta=data_volta,
                passageiros=passageiros,
                total_pix=valor_final,
                tabela=df,
                buffer=buffer,
            )
            st.download_button(
                label="⬇️ Baixar PDF da Cotação",
                data=buffer.getvalue(),
                file_name=f"Portao5Viagens_Cotacao_{origem}_{destino}_{dt.date.today()}.pdf",
                mime="application/pdf",
            )
else:
    st.info("Envie o print da tela para iniciar a cotação.")


# ========== FUNÇÃO GERAR PDF ==========
def gerar_pdf(companhia, origem, destino, data_ida, data_volta, passageiros, total_pix, tabela, buffer):
    c = canvas.Canvas(buffer, pagesize=A4)
    W, H = A4

    # Cabeçalho (sem fundo)
    c.setFont("DejaVuSans-Bold", 20)
    c.drawCentredString(W / 2, H - 80, "Informações do voo")

    c.setFont("DejaVuSans", 12)
    c.drawString(2.5 * cm, H - 120, f"Origem: {origem}   ➜   Destino: {destino}")
    c.drawString(2.5 * cm, H - 140, f"Ida: {data_ida}   |   Volta: {data_volta}")
    c.drawString(2.5 * cm, H - 160, f"Passageiros: {passageiros}")
    c.drawString(2.5 * cm, H - 190, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    # Tabela de parcelamento
    c.setFont("DejaVuSans-Bold", 14)
    c.drawString(2.5 * cm, H - 230, "Opções de parcelamento:")

    y = H - 250
    c.setFont("DejaVuSans", 12)
    for index, row in tabela.iterrows():
        c.drawString(3 * cm, y, f"{row['Parcelas']}: {row['Valor']}")
        y -= 18

    # Rodapé
    c.setFont("DejaVuSans", 10)
    c.drawRightString(W - 2.5 * cm, 2 * cm, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    c.save()
