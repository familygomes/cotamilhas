import os
import re
import unicodedata
import datetime as dt
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image
import pytesseract

# PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ------------------------ CONFIG ------------------------
st.set_page_config(page_title="CotaMilhas Express • Portão 5 Viagens", layout="centered")
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"   # para Streamlit Cloud

COLOR_PRIMARY = colors.HexColor("#007C91")  # Azul Portão 5
HIST_CSV = "cotacoes_historico.csv"
PDF_DIR  = "pdfs"
LOGOS_DIR = "logos"

os.makedirs(PDF_DIR, exist_ok=True)

if not os.path.exists(HIST_CSV):
    pd.DataFrame(columns=[
        "Data/Hora", "Companhia", "Origem", "Destino",
        "Ida Data", "Ida Saída", "Ida Chegada",
        "Volta Data", "Volta Saída", "Volta Chegada",
        "Passageiros", "Milhas", "Taxa", "Milheiro",
        "Margem %", "Juros % a.m.", "Valor Pix"
    ]).to_csv(HIST_CSV, index=False)

st.title("🛫 CotaMilhas Express — Portão 5 Viagens")
st.caption("Envie o print da passagem e gere a cotação automática com PDF profissional.")

# ------------------------ UTILS -------------------------
def _to_float(s: str) -> float:
    if not s:
        return 0.0
    s = s.replace("\xa0", " ").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def _pad_hhmm(t: str) -> str:
    t = t.lower().replace("h", ":")
    m = re.match(r"^\s*(\d{1,2})[:](\d{2})\s*$", t)
    if not m:
        return t.strip()
    hh = int(m.group(1)); mm = m.group(2)
    return f"{hh:02d}:{mm}"

MESES = {
    "jan": "01","fev": "02","mar": "03","abr": "04","mai": "05","jun": "06",
    "jul": "07","ago": "08","set": "09","out": "10","nov": "11","dez": "12"
}

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

# ------------------------ OCR EXTRACTORS ------------------------
def extrair_milhas(texto: str) -> float:
    """
    Extrai total de milhas/pontos (LATAM, Azul, GOL).
    """
    texto_clean = _strip_accents(texto.lower())

    # Prioriza blocos com TOTAL
    pad_total = re.search(r"total.*?(\d{1,3}(?:\.\d{3})+|\d+)\s*(milhas|pontos?)", texto_clean)
    if pad_total:
        return float(pad_total.group(1).replace(".", ""))

    # Busca padrão Azul (ex: '212.800 pontos + R$ 240,16')
    pad_azul = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(pontos?|milhas).*?\+\s*(?:r\$|brl)\s*([\d\.,]+)", texto_clean)
    if pad_azul:
        return float(pad_azul.group(1).replace(".", ""))

    # Busca geral
    matches = re.findall(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(milhas|pontos?)", texto_clean)
    if matches:
        valores = [int(m[0].replace(".", "")) for m in matches]
        return max(valores)
    return 0.0


def extrair_taxa(texto: str) -> float:
    """
    Extrai a taxa total (LATAM, Azul e GOL).
    """
    texto_clean = _strip_accents(texto.lower())

    # Azul: bloco total (ex: "212.800 pontos + R$ 240,16")
    m_azul = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(pontos?|milhas).*?\+\s*(?:r\$|brl)\s*([\d\.,]+)", texto_clean)
    if m_azul:
        return _to_float(m_azul.group(3))

    # Busca taxa de embarque ou total
    m_total = re.search(r"(taxa|embarque|total).*?(?:r\$|brl)\s*([\d\.,]+)", texto_clean)
    if m_total:
        return _to_float(m_total.group(2))

    # Último recurso: soma de taxas pequenas
    valores = [_to_float(v) for v in re.findall(r"(?:r\$|brl)\s*([\d\.,]+)", texto_clean)]
    valores = [v for v in valores if 0 < v < 300]
    return round(sum(valores), 2) if valores else 0.0


def extrair_rota(texto: str):
    m = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,30}\b([A-Z]{3})\b", texto)
    if m:
        return m.group(1), m.group(2)
    return "-", "-"


def extrair_datas_horas(texto: str):
    texto_s = _strip_accents(texto.lower())
    m1 = re.search(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    m2 = re.findall(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    ano = dt.datetime.now().year
    ida_data = f"{int(m1.group(1)):02d}/{MESES[m1.group(2)]}/{ano}" if m1 else "-"
    volta_data = f"{int(m2[1][0]):02d}/{MESES[m2[1][1]]}/{ano}" if len(m2) > 1 else "-"
    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto_s)
    horas = [_pad_hhmm(h) for h in horas]
    return ida_data, horas[0] if len(horas) > 0 else "-", horas[1] if len(horas) > 1 else "-", volta_data, horas[2] if len(horas) > 2 else "-", horas[3] if len(horas) > 3 else "-"

# ------------------------ FINANCE ------------------------
def calcular_parcelas(valor_total: float, juros_am: float, max_n: int = 10):
    i = juros_am / 100.0
    out = []
    for n in range(1, max_n + 1):
        if i == 0:
            pmt = valor_total / n
        else:
            pmt = valor_total * (i * (1 + i) ** n) / ((1 + i) ** n - 1)
        out.append((n, round(pmt, 2)))
    return out

# ------------------------ LOGOS ------------------------
def _try_logo(paths):
    for p in paths:
        if os.path.exists(p):
            return ImageReader(p)
    return None

def load_logo_portao5():
    return _try_logo([os.path.join(LOGOS_DIR, "logo portao5viagens.png")])

def load_logo_cia(cia: str):
    cia = (cia or "").upper().strip()
    if "GOL" in cia:
        return _try_logo([os.path.join(LOGOS_DIR, "logo gol.png")])
    if "LATAM" in cia:
        return _try_logo([os.path.join(LOGOS_DIR, "logo latam.png")])
    if "AZUL" in cia:
        return _try_logo([os.path.join(LOGOS_DIR, "logo azul.png")])
    return None

# ------------------------ PDF ------------------------
def gerar_pdf(companhia, origem, destino,
              ida_data, ida_saida, ida_chegada,
              volta_data, volta_saida, volta_chegada,
              passageiros, total_pix, tabela_parc):
    W, H = A4
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Cabeçalho branco
    p5 = load_logo_portao5()
    cia_img = load_logo_cia(companhia)
    if p5: c.drawImage(p5, 2*cm, H - 70, width=95, height=42, mask='auto')
    if cia_img: c.drawImage(cia_img, W - 2*cm - 95, H - 70, width=95, height=42, mask='auto')

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W/2, H - 45, "Informações do Voo")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawCentredString(W/2, H - 60, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    # Itinerário
    y = H - 130
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "✈️  Itinerário de IDA")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem} → {destino}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{ida_data}  |  {ida_saida} → {ida_chegada}")

    # Volta
    y -= 64
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "🛬  Itinerário de VOLTA")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{destino} → {origem}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{volta_data}  |  {volta_saida} → {volta_chegada}")

    # Passageiros e total
    y -= 60
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")
    y -= 30
    c.setFont("Helvetica-Bold", 15)
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    # Parcelamento com borda
    y -= 40
    c.setFillColor(COLOR_PRIMARY)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2.5*cm, y, "💳 Opções de Parcelamento")
    y -= 15
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.rect(2.5*cm, y - 180, W - 5*cm, 180, stroke=True, fill=False)
    y -= 25
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    col1_x, col2_x = 3*cm, 7.5*cm
    for n, pmt in tabela_parc:
        c.drawString(col1_x, y, f"{n}x")
        c.drawString(col2_x, y, f"R$ {pmt:,.2f}")
        y -= 16

    # Observações finais
    y -= 25
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawString(2*cm, y, "Condições sujeitas à disponibilidade.")
    y -= 12
    c.drawString(2*cm, y, "Remarcações e cancelamentos conforme regras da companhia aérea.")
    y -= 12
    c.drawString(2*cm, y, "Comece sua viagem embarcando pelo Portão 5 ✈️")

    c.save(); buf.seek(0)
    return buf

# ------------------------ INTERFACE ------------------------
st.subheader("📸 Envie o print da tela da passagem")
uploaded = st.file_uploader("Selecione a imagem", type=["png", "jpg", "jpeg"])

if uploaded:
    image = Image.open(uploaded)
    st.image(image, caption="Print recebido", use_column_width=True)

    try:
        texto = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        st.error("OCR indisponível. Garanta que o ambiente tem tesseract-ocr e tesseract-ocr-por instalados.")
        st.stop()

    milhas = extrair_milhas(texto)
    taxa = extrair_taxa(texto)
    origem, destino = extrair_rota(texto)
    ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada = extrair_datas_horas(texto)

    # Detectar companhia
    cia_auto = "GOL" if "smiles" in texto.lower() or "gol" in texto.lower() else \
               "LATAM" if "latam" in texto.lower() else \
               "AZUL" if "azul" in texto.lower() else "LATAM"

    st.markdown("---")
    st.subheader("✈️ Parâmetros da Cotação")

    companhia = st.selectbox("Companhia aérea", ["GOL", "LATAM", "AZUL"], index=["GOL","LATAM","AZUL"].index(cia_auto))
    passageiros = st.number_input("Passageiros", min_value=1, value=2, step=1)
    origem = st.text_input("Origem (IATA)", value=origem)
    destino = st.text_input("Destino (IATA)", value=destino)

    ida_data = st.text_input("Data da ida", value=ida_data)
    volta_data = st.text_input("Data da volta", value=volta_data)

    milheiro = st.number_input("Milheiro (R$/1000)", value=25.0, step=0.5)
    margem = st.number_input("Margem (%)", value=15.0, step=0.5)
    juros = st.number_input("Juros (% a.m.)", value=2.9, step=0.1)

    if milhas > 0:
        valor_milhas = (milhas / 1000.0) * milheiro
        subtotal = valor_milhas + taxa
        total_pix = round(subtotal * (1 + margem / 100.0), 2)
        tabela = calcular_parcelas(total_pix, juros)

        st.markdown("### 💰 Cotação")
        st.write(f"**Milhas:** {milhas:,.0f}")
        st.write(f"**Taxa:** R$ {taxa:,.2f}")
        st.write(f"**Valor total sugerido:** R$ {total_pix:,.2f}")

        df = pd.DataFrame({
            "Parcelas": [f"{n}x" for n, _ in tabela],
            "Valor (R$)": [p for _, p in tabela]
        })
        st.dataframe(df, use_container_width=True)

        pdf_buf = gerar_pdf(companhia, origem, destino,
                            ida_data, ida_saida, ida_chegada,
                            volta_data, volta_saida, volta_chegada,
                            passageiros, total_pix, tabela)

        filename = f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf"
        st.download_button("📄 Baixar PDF", pdf_buf, file_name=filename, mime="application/pdf")

else:
    st.info("Envie o print (PNG/JPG) da passagem para começar.")
