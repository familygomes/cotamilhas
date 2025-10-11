import streamlit as st
from PIL import Image
import pytesseract
import re
import pandas as pd
import io
import datetime as dt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import os

# ✅ Deve ser a primeira configuração Streamlit
st.set_page_config(page_title="CotaMilhas Express", layout="centered")

uploaded_file = st.file_uploader("Envie aqui o print da tela (imagem da passagem)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print enviado", use_column_width=True)

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print enviado", use_column_width=True)
    # Converter imagem para texto usando OCR
    text = pytesseract.image_to_string(image, lang="por")

    # Procurar valor da taxa de embarque (ex: BRL 783,33 ou R$ 204,75)
    import re
    match = re.search(r"(?:BRL|R\$)\s*[\d\.,]+", text)

    if match:
        taxa_embarque = match.group()
        st.success(f"💰 Taxa de embarque detectada: {taxa_embarque}")
    else:
        st.warning("⚠️ Não foi possível identificar a taxa de embarque no print.")
import io
import datetime as dt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import os

# Caminho do histórico
HIST_PATH = "cotacoes_historico.csv"
if not os.path.exists(HIST_PATH):
    pd.DataFrame(columns=["Data/Hora", "Cia", "Origem", "Destino", "Valor PIX", "Parcelado"]).to_csv(HIST_PATH, index=False)

# Função para gerar PDF
def gerar_pdf(companhia, origem, destino, ida_data, ida_saida, ida_chegada,
              volta_data, volta_saida, volta_chegada, passageiros, total_pix, tabela):

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Cabeçalho
    c.setFont("Helvetica-Bold", 20)
    c.drawString(2.5*cm, H-3*cm, "Informações do voo")

    # Logos
    logo_portao = "logos/logo_portao5viagens.png"
    logos = {
        "GOL": "logos/logo_gol.png",
        "LATAM": "logos/logo_latam.png",
        "AZUL": "logos/logoazul.png"
    }
    cia_logo = logos.get(companhia.upper(), None)
    if os.path.exists(logo_portao):
        c.drawImage(logo_portao, 2*cm, H-2.5*cm, width=4*cm, height=1.8*cm, mask='auto')
    if cia_logo and os.path.exists(cia_logo):
        c.drawImage(cia_logo, W-6*cm, H-2.5*cm, width=4*cm, height=1.5*cm, mask='auto')

    # Dados do voo
    y = H - 5*cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2.5*cm, y, f"✈ Itinerário de IDA ({ida_data})")
    y -= 0.8*cm
    c.setFont("Helvetica", 12)
    c.drawString(2.5*cm, y, f"{origem} → {destino} | {ida_saida} → {ida_chegada}")

    y -= 1.2*cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2.5*cm, y, f"✈ Itinerário de VOLTA ({volta_data})")
    y -= 0.8*cm
    c.setFont("Helvetica", 12)
    c.drawString(2.5*cm, y, f"{destino} → {origem} | {volta_saida} → {volta_chegada}")

    y -= 1.2*cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.5*cm, y, f"👥 Passageiros: {passageiros}")

    # Valores
    y -= 1.5*cm
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#0A4D68"))
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    y -= 0.8*cm
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    c.drawString(2.5*cm, y, "💳 Opções de parcelamento:")

    y -= 0.5*cm
    c.setFont("Helvetica", 11)
    for i, (parc, valor) in enumerate(tabela):
        c.drawString(3*cm, y - i*0.5*cm, f"{parc}x de R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    # Rodapé
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawRightString(W-2*cm, 1.5*cm, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    c.save()
    buf.seek(0)
    return buf


# === Interface Streamlit ===

st.title("🛫 CotaMilhas Express - Portão 5 Viagens")
st.markdown("Cole ou envie o print da passagem para gerar a cotação automaticamente.")

# Captura da imagem
uploaded_file = st.file_uploader(
    "Envie aqui o print da tela (imagem da passagem)",
    type=["png", "jpg", "jpeg"]
)

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print enviado", use_column_width=True)
        image = Image.open(uploaded)

if image:
    st.image(image, caption="Print recebido", use_column_width=True)
    texto = pytesseract.image_to_string(image, lang="por")

    # Extrair milhas e taxa (Latam ou Smiles)
    milhas_match = re.search(r"([\d\.]+)\s*milhas", texto)
    taxa_match = re.search(r"\+\s*BRL\s*([\d\.,]+)", texto)

    milhas = float(milhas_match.group(1).replace(".", "")) if milhas_match else 0
    taxa = float(taxa_match.group(1).replace(",", ".").replace(".", "", 1)) if taxa_match else 0

    st.write(f"**Milhas detectadas:** {milhas:,.0f}".replace(",", "."))
    st.write(f"**Taxa de embarque:** R$ {taxa:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    # Entradas manuais
    companhia = st.selectbox("✈️ Companhia aérea", ["GOL", "LATAM", "AZUL"])
    origem = st.text_input("Origem (ex: POA)")
    destino = st.text_input("Destino (ex: GIG)")
    passageiros = st.number_input("Número de passageiros", min_value=1, value=1)
    milheiro = st.number_input("💸 Valor do milheiro (R$ por 1000 milhas):", min_value=10.0, value=16.0, step=0.5)
    margem = st.number_input("📈 Margem (%):", min_value=0.0, value=15.0, step=0.5)

    if milhas > 0 and taxa > 0 and origem and destino:
        total_pix = ((milhas / 1000) * milheiro + taxa) * (1 + margem / 100)

        # Campo editável
        total_editado = st.number_input("💰 Valor final sugerido (editável):", min_value=0.0, value=round(total_pix, 2), step=50.0)

        # Tabela de parcelamento (taxa 2.9% a.m.)
        juros = 0.029
        tabela = []
        for n in range(1, 11):
            parcela = total_editado * (juros * (1 + juros)**n) / ((1 + juros)**n - 1)
            tabela.append((n, parcela))

        st.markdown("### 💳 Tabela de Parcelamento")
        for n, v in tabela:
            st.write(f"**{n}x** de R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        # Botão PDF
        if st.button("📄 Gerar PDF"):
            pdf_buf = gerar_pdf(companhia, origem, destino,
                                "-", "-", "-",
                                "-", "-", "-",
                                passageiros, total_editado, tabela)

            st.download_button("⬇️ Baixar Cotação PDF", pdf_buf, file_name=f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}.pdf")
else:
    st.info("Cole ou envie um print para começar.")
