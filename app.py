import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import os

# ---------------------------------------------------------
# CONFIGURAÇÕES INICIAIS
# ---------------------------------------------------------
st.set_page_config(
    page_title="CotaMilhas Express - Portão 5 Viagens",
    layout="centered"
)

st.title("🛫 CotaMilhas Express - Portão 5 Viagens")
st.markdown("Envie ou cole o print da tela da passagem para gerar a cotação automaticamente.")

# ---------------------------------------------------------
# UPLOAD DA IMAGEM
# ---------------------------------------------------------
uploaded_file = st.file_uploader(
    "📸 Envie aqui o print da tela da passagem (PNG, JPG, JPEG)",
    type=["png", "jpg", "jpeg"]
)

if uploaded_file is not None:
    # Exibe a imagem enviada
    image = Image.open(uploaded_file)
    st.image(image, caption="🖼️ Print enviado com sucesso!", use_column_width=True)

    # -----------------------------------------------------
    # PROCESSA OCR COM TESSERACT
    # -----------------------------------------------------
    st.info("🔍 Lendo as informações da imagem...")
    try:
        text = pytesseract.image_to_string(image, lang='eng')
        st.text_area("🧾 Texto identificado na imagem:", text, height=200)

        # -------------------------------------------------
        # GERA ARQUIVO PDF COM AS INFORMAÇÕES
        # -------------------------------------------------
        pdf_filename = f"cotacao_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join("/tmp", pdf_filename)

        c = canvas.Canvas(pdf_path, pagesize=A4)
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.black)
        c.drawString(50, 800, "CotaMilhas Express - Portão 5 Viagens")
        c.line(50, 795, 550, 795)
        c.setFont("Helvetica", 10)
        text_y = 770

        for line in text.splitlines():
            if text_y < 50:
                c.showPage()
                text_y = 800
            c.drawString(50, text_y, line)
            text_y -= 15

        c.save()

        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        st.success("✅ PDF gerado com sucesso!")
        st.download_button(
            label="📥 Baixar cotação em PDF",
            data=pdf_data,
            file_name=pdf_filename,
            mime="application/pdf"
        )

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar a imagem: {e}")

else:
    st.warning("👆 Envie ou cole o print da tela acima para começar.")
