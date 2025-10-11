import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
import io
import datetime as dt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import os

# ==========================
# ⚙️ CONFIGURAÇÃO INICIAL
# ==========================
st.set_page_config(page_title="CotaMilhas Express", layout="centered")

st.title("✈️ CotaMilhas Express - Portão 5 Viagens")
st.markdown("Envie ou cole o print da passagem para gerar a cotação automaticamente.")

# ==========================
# 🧩 TENTA ATIVAR MODO PASTE
# ==========================
try:
    from streamlit_image_paste import image_paste
    modo_paste = True
except ImportError:
    modo_paste = False

# ==========================
# 📸 UPLOAD OU COLAGEM
# ==========================
st.markdown("### 🖼️ Envie ou cole o print da tela da passagem")

image = None
uploaded_file = st.file_uploader(
    "Envie aqui o print (PNG, JPG, JPEG)",
    type=["png", "jpg", "jpeg"]
)

if modo_paste:
    image = image_paste(label="📋 Cole o print aqui (Ctrl + V)")

if not image and uploaded_file:
    image = Image.open(uploaded_file)

# ==========================
# 🔍 FUNÇÃO OCR
# ==========================
def extrair_texto(img):
    texto = pytesseract.image_to_string(img, lang="por")
    return texto

# ==========================
# 💰 FUNÇÃO PARA ENCONTRAR DADOS
# ==========================
def extrair_dados(texto):
    import re
    milhas = re.findall(r"([\d\.]+)\s*milha", texto)
    valores = re.findall(r"R\$[\s]*([\d\.,]+)", texto)
    return milhas, valores

# ==========================
# 🧾 GERAÇÃO DE PDF
# ==========================
def gerar_pdf(df, companhia, origem, destino, total_pix):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    W, H = A4
    y = H - 80

    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(W / 2, y, "COTAÇÃO DE PASSAGEM")
    y -= 30

    c.setFont("Helvetica", 12)
    c.drawCentredString(W / 2, y, f"Companhia: {companhia}  |  Rota: {origem} → {destino}")
    y -= 40

    # Cabeçalho da tabela
    c.setFont("Helvetica-Bold", 11)
    c.drawString(3 * cm, y, "Milhas")
    c.drawString(7 * cm, y, "Valor (R$)")
    y -= 10
    c.line(2.5 * cm, y, 17.5 * cm, y)
    y -= 10

    # Linhas da tabela
    c.setFont("Helvetica", 10)
    for _, row in df.iterrows():
        c.drawString(3 * cm, y, str(row["Milhas"]))
        c.drawString(7 * cm, y, str(row["Valor (R$)"]))
        y -= 15

    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawString(3 * cm, y, f"💳 Valor total (Pix): R$ {total_pix:.2f}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# ==========================
# ⚙️ PROCESSAMENTO PRINCIPAL
# ==========================
if image:
    st.image(image, caption="Print recebido", use_column_width=True)

    with st.spinner("🕵️ Extraindo informações do print..."):
        texto_extraido = extrair_texto(image)
        milhas, valores = extrair_dados(texto_extraido)

    if milhas and valores:
        st.success("✅ Dados detectados com sucesso!")

        dados = pd.DataFrame({
            "Milhas": milhas[:len(valores)],
            "Valor (R$)": valores[:len(milhas)]
        })

        st.markdown("### ✏️ Revise os valores antes de gerar o PDF")
        dados_edit = st.data_editor(dados, num_rows="dynamic", use_container_width=True)

        total_pix = st.number_input("💰 Valor final sugerido (R$)", value=0.0, step=10.0)

        companhia = st.text_input("✈️ Companhia aérea", value="LATAM")
        origem = st.text_input("🌍 Origem", value="POA")
        destino = st.text_input("🎯 Destino", value="GIG")

        if st.button("📄 Gerar PDF"):
            pdf_file = gerar_pdf(dados_edit, companhia, origem, destino, total_pix)
            st.download_button(
                label="⬇️ Baixar cotação em PDF",
                data=pdf_file,
                file_name=f"Cotacao_{companhia}_{origem}_{destino}.pdf",
                mime="application/pdf"
            )
    else:
        st.warning("⚠️ Não consegui identificar milhas ou valores no print. Verifique se a imagem está legível.")
else:
    st.info("👆 Envie ou cole o print da tela acima para começar.")
