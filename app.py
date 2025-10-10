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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Fonte com acentuação
pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))

# ---------------- CONFIG ----------------
st.set_page_config(page_title="CotaMilhas Express • Portão 5 Viagens", layout="centered")

COLOR_PRIMARY = colors.HexColor("#007C91")
COLOR_ACCENT = colors.HexColor("#F58220")

HIST_CSV = "cotacoes_historico.csv"
PDF_DIR = "pdfs"
LOGOS_DIR = "logos"
os.makedirs(PDF_DIR, exist_ok=True)

if not os.path.exists(HIST_CSV):
    pd.DataFrame(columns=[
        "Data/Hora","Companhia","Origem","Destino","Ida Data","Ida Saída",
        "Ida Chegada","Volta Data","Volta Saída","Volta Chegada",
        "Passageiros","Milhas","Taxa","Milheiro","Margem %","Juros % a.m.","Valor Pix"
    ]).to_csv(HIST_CSV, index=False)

st.title("🛫 CotaMilhas Express — Portão 5 Viagens")

# --------------- Funções ----------------
def _to_float(s):
    s = s.replace(".", "").replace(",", ".") if s else "0"
    try:
        return float(s)
    except:
        return 0.0

def _pad_hhmm(t):
    t = t.lower().replace("h", ":")
    m = re.match(r"(\d{1,2})[:](\d{2})", t)
    if not m:
        return t.strip()
    hh = int(m.group(1)); mm = m.group(2)
    return f"{hh:02d}:{mm}"

MESES = {
    "jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
    "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"
}

def _strip_accents(s): 
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def extrair_milhas(texto):
    pad = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    nums = [int(n.replace(".", "")) for n in pad.findall(texto)]
    return float(max(nums)) if nums else 0.0

def extrair_taxa(texto):
    m = re.search(r"(?:R\$|BRL)\s*([\d\.,]+)", texto)
    return _to_float(m.group(1)) if m else 0.0

def extrair_rota(texto):
    m = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,30}\b([A-Z]{3})\b", texto)
    return (m.group(1), m.group(2)) if m else ("-", "-")

def extrair_datas_horas(texto):
    texto_s = _strip_accents(texto.lower())
    ano = dt.datetime.now().year
    m1 = re.search(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    m2b = re.findall(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    ida = volta = "-"
    if m1:
        ida = f"{int(m1.group(1)):02d}/{MESES[m1.group(2)]}/{ano}"
    if len(m2b) >= 2:
        d, mes = m2b[1]
        volta = f"{int(d):02d}/{MESES[mes]}/{ano}"

    horas = re.findall(r"(\d{1,2}[:h]\d{2})", texto_s)
    horas = [_pad_hhmm(h) for h in horas]
    ida_s, ida_c, vol_s, vol_c = horas + ["-"]*4
    return ida, ida_s, ida_c, volta, vol_s, vol_c

def calcular_parcelas(valor_total, juros_am, max_n=10):
    i = juros_am / 100.0
    out = []
    for n in range(1, max_n + 1):
        if i == 0:
            pmt = valor_total / n
        else:
            pmt = valor_total * (i * (1 + i) ** n) / ((1 + i) ** n - 1)
        out.append((n, round(pmt, 2)))
    return out

def _try_logo(paths):
    for p in paths:
        if os.path.exists(p):
            return ImageReader(p)
    return None

def logo_portao():
    return _try_logo([os.path.join(LOGOS_DIR, "logo portao5viagens.png")])

def logo_cia(cia):
    cia = (cia or "").upper().strip()
    nomes = {
        "GOL":["logo gol.png","logogol.png"],
        "LATAM":["logo latam.png","logolatam.png"],
        "AZUL":["logo azul.png","logoazul.png"]
    }
    for n in nomes.get(cia, []):
        p = os.path.join(LOGOS_DIR, n)
        if os.path.exists(p):
            return ImageReader(p)
    return None

def gerar_pdf(companhia, origem, destino,
              ida_data, ida_saida, ida_chegada,
              volta_data, volta_saida, volta_chegada,
              passageiros, total_pix, tabela_parc):
    W, H = A4
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("DejaVuSans", 12)

    # Header
    p5 = logo_portao()
    cia_img = logo_cia(companhia)
    if p5: c.drawImage(p5, 2*cm, H-70, width=95, height=42, mask='auto')
    if cia_img: c.drawImage(cia_img, W-2*cm-85, H-68, width=85, height=38, mask='auto')
    c.setStrokeColor(COLOR_PRIMARY)
    c.setLineWidth(2)
    c.line(2*cm, H-75, W-2*cm, H-75)
    c.setFillColor(COLOR_PRIMARY)
    c.setFont("DejaVuSans-Bold", 20)
    c.drawCentredString(W/2, H-95, "Informações do voo")
    c.setFont("DejaVuSans", 10)
    c.drawRightString(W-2.3*cm, H-110, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    y = H-150
    c.setFont("DejaVuSans-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem} → {destino}")
    c.setFont("DejaVuSans", 12)
    c.drawString(2.5*cm, y-18, f"Ida: {ida_data}  |  {ida_saida} → {ida_chegada}")
    c.drawString(2.5*cm, y-36, f"Volta: {volta_data}  |  {volta_saida} → {volta_chegada}")

    y -= 70
    c.setFont("DejaVuSans-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")
    y -= 25
    c.setFont("DejaVuSans-Bold", 15)
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    y -= 40
    c.setFont("DejaVuSans-Bold", 14)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(2.5*cm, y, "💳 Opções de parcelamento")
    y -= 15
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.line(2.5*cm, y, W-2.5*cm, y)
    y -= 20
    c.setFont("DejaVuSans", 12)
    c.setFillColor(colors.black)
    for n,pmt in tabela_parc:
        c.drawString(2.6*cm, y, f"{n}x")
        c.drawString(7*cm, y, f"R$ {pmt:,.2f}")
        y -= 18
        if y < 2.5*cm:
            c.showPage(); y = H-3*cm

    c.setFont("DejaVuSans", 9)
    c.setFillColor(colors.grey)
    c.drawString(2*cm, 1.5*cm, "Gerado automaticamente via CotaMilhas Express — Portão 5 Viagens")
    c.save(); buf.seek(0)
    return buf

# ---------------- Interface ----------------
st.subheader("📸 Inserir print da passagem")
uploaded = st.file_uploader("Arraste ou selecione a imagem (PNG ou JPG)", type=["png","jpg","jpeg"])

if uploaded:
    image = Image.open(uploaded)
    st.image(image, caption="Print recebido", use_column_width=True)
    texto = pytesseract.image_to_string(image, lang="por+eng")

    milhas_ocr = extrair_milhas(texto)
    taxa_ocr = extrair_taxa(texto)
    origem_ocr, destino_ocr = extrair_rota(texto)
    ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada = extrair_datas_horas(texto)

    companhia = st.selectbox("Companhia aérea", ["GOL","LATAM","AZUL"], index=1 if "latam" in texto.lower() else 0)
    passageiros = st.number_input("Passageiros", min_value=1, value=2, step=1)

    st.markdown("#### Ajustes")
    origem = st.text_input("Origem", origem_ocr)
    destino = st.text_input("Destino", destino_ocr)
    ida_data = st.text_input("Data da ida", ida_data)
    volta_data = st.text_input("Data da volta", volta_data)

    milhas = st.number_input("Milhas totais", value=float(milhas_ocr), step=100.0)
    taxa = st.number_input("Taxa (R$)", value=float(taxa_ocr), step=1.0)
    milheiro = st.number_input("Milheiro (R$/1000)", value=25.0, step=0.5)
    margem = st.number_input("Margem (%)", value=15.0, step=0.5)
    juros = st.number_input("Juros (% a.m.)", value=2.9, step=0.1)

    if milhas > 0:
        total_pix_sugerido = round(((milhas/1000)*milheiro + taxa) * (1+margem/100), 2)
        total_pix = st.number_input("Valor total (Pix) — editável", value=total_pix_sugerido, step=1.0)
        tabela = calcular_parcelas(total_pix, juros, 10)
        df = pd.DataFrame({"Parcelas":[f"{n}x" for n,_ in tabela],
                           "Valor da parcela (R$)":[p for _,p in tabela]})
        st.dataframe(df, use_container_width=True)

        # Histórico
        novo = pd.DataFrame([{
            "Data/Hora":dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Companhia":companhia,"Origem":origem,"Destino":destino,
            "Ida Data":ida_data,"Ida Saída":ida_saida,"Ida Chegada":ida_chegada,
            "Volta Data":volta_data,"Volta Saída":volta_saida,"Volta Chegada":volta_chegada,
            "Passageiros":passageiros,"Milhas":milhas,"Taxa":taxa,"Milheiro":milheiro,
            "Margem %":margem,"Juros % a.m.":juros,"Valor Pix":total_pix
        }])
        hist = pd.read_csv(HIST_CSV)
        hist = pd.concat([novo, hist], ignore_index=True)
        hist.to_csv(HIST_CSV, index=False)

        pdf_buf = gerar_pdf(companhia, origem, destino,
                            ida_data, ida_saida, ida_chegada,
                            volta_data, volta_saida, volta_chegada,
                            passageiros, total_pix, tabela)
        filename = f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf"
        with open(os.path.join(PDF_DIR, filename), "wb") as f:
            f.write(pdf_buf.getvalue())

        st.download_button("📄 Baixar PDF", data=pdf_buf, file_name=filename, mime="application/pdf")
        with st.expander("📊 Histórico"):
            st.dataframe(hist, use_container_width=True)
else:
    st.info("Envie o print da passagem para gerar a cotação.")
