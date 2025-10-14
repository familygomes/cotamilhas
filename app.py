# app.py — CotaMilhas Express • Portão 5 Viagens (v3.6 FINAL)

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

# ==============================
# CONFIGURAÇÕES GERAIS
# ==============================
st.set_page_config(page_title="CotaMilhas Express • Portão 5 Viagens", layout="centered")
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

COLOR_PRIMARY = colors.HexColor("#007C91")
COLOR_BORDER  = colors.HexColor("#E5E7EB")

HIST_CSV  = "cotacoes_historico.csv"
PDF_DIR   = "pdfs"
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
st.caption("Envie o print da passagem, confira os dados detectados, ajuste os valores e gere o PDF profissional.")

# ==============================
# FUNÇÕES AUXILIARES
# ==============================
MESES = {"jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
         "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"}

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def _to_float(s: str) -> float:
    if not s: return 0.0
    s = s.replace("\xa0"," ").replace(".","").replace(",",".")
    try: return float(s)
    except: return 0.0

def _pad_hhmm(t: str) -> str:
    t = t.lower().replace("h",":")
    m = re.match(r"^\s*(\d{1,2})[:](\d{2})\s*$",t)
    if not m: return t.strip()
    return f"{int(m.group(1)):02d}:{m.group(2)}"

# --- OCR ---
def extrair_milhas(texto: str) -> float:
    """Detecta milhas/pontos em Azul, GOL e LATAM."""
    texto_clean = _strip_accents(texto.lower())

    # Azul: "total 02 viajantes 212.800 pontos + r$ 240,16"
    m_azul_total = re.search(r"total[^0-9]*(\d{1,3}(?:\.\d{3})+|\d+)\s*(pontos?)", texto_clean)
    if m_azul_total:
        return float(m_azul_total.group(1).replace(".", ""))

    # Azul/Latam padrão: "212.800 pontos + R$ 240,16"
    pad_combo = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(pontos?|milhas)\s*\+\s*(r\$|brl)\s*[\d\.,]+", texto_clean)
    if pad_combo:
        return float(pad_combo.group(1).replace(".", ""))

    # Padrão geral
    matches = re.findall(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(milhas|pontos?)", texto_clean)
    if matches:
        valores = [int(m[0].replace(".", "")) for m in matches]
        return max(valores)

    return 0.0

def extrair_taxa(texto: str) -> float:
    """Detecta taxa de embarque (R$ ou BRL) incluindo Azul, GOL e LATAM."""
    texto_clean = _strip_accents(texto.lower())

    m_azul = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(pontos?|milhas)\s*\+\s*(?:r\$|brl)\s*([\d\.,]+)", texto_clean)
    if m_azul: return _to_float(m_azul.group(3))

    m_taxa = re.search(r"(taxa|embarque|total).*?(?:r\$|brl)\s*([\d\.,]+)", texto_clean)
    if m_taxa: return _to_float(m_taxa.group(2))

    valores = [_to_float(v) for v in re.findall(r"(?:r\$|brl)\s*([\d\.,]+)", texto_clean)]
    valores = [v for v in valores if 0 < v < 300]
    return round(sum(valores),2) if valores else 0.0

def extrair_rota(texto: str):
    pad = re.search(r"\b([A-Z]{3})\b[^A-Z\n]{0,10}[→\-–> ]{1,3}[^A-Z\n]{0,10}\b([A-Z]{3})\b", texto)
    if pad: return pad.group(1), pad.group(2)
    alt = re.findall(r"\b([A-Z]{3})\b", texto)
    if len(alt) >= 2: return alt[0], alt[1]
    return "-", "-"

def extrair_datas_horas(texto: str):
    texto_s = _strip_accents(texto.lower())
    m1 = re.search(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    m2 = re.findall(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    ano = dt.datetime.now().year
    ida_data = f"{int(m1.group(1)):02d}/{MESES[m1.group(2)]}/{ano}" if m1 else "-"
    volta_data = f"{int(m2[1][0]):02d}/{MESES[m2[1][1]]}/{ano}" if len(m2)>1 else "-"
    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto_s)
    horas = [_pad_hhmm(h) for h in horas]
    return ida_data, horas[0] if len(horas)>0 else "-", horas[1] if len(horas)>1 else "-", volta_data, horas[2] if len(horas)>2 else "-", horas[3] if len(horas)>3 else "-"

def calcular_parcelas(valor_total: float, juros_am: float, max_n: int=10):
    i = juros_am/100.0
    out=[]
    for n in range(1,max_n+1):
        pmt = valor_total/n if i==0 else valor_total*(i*(1+i)**n)/((1+i)**n-1)
        out.append((n,round(pmt,2)))
    return out

def _try_logo(paths):
    for p in paths:
        if os.path.exists(p): return ImageReader(p)
    return None

def load_logo_portao5():
    return _try_logo([os.path.join(LOGOS_DIR,"logo portao5viagens.png"),
                      os.path.join(LOGOS_DIR,"logo_portao5viagens.png")])

def load_logo_cia(cia:str):
    cia=(cia or "").upper().strip()
    if cia=="GOL": return _try_logo([os.path.join(LOGOS_DIR,"logo gol.png")])
    if cia=="LATAM": return _try_logo([os.path.join(LOGOS_DIR,"logo latam.png")])
    if cia=="AZUL": return _try_logo([os.path.join(LOGOS_DIR,"logo azul.png")])
    return None

# ==============================
# GERAR PDF
# ==============================
def gerar_pdf(companhia,origem,destino,ida_data,ida_s,ida_c,vol_data,vol_s,vol_c,passageiros,total_pix,tabela_parc):
    W,H=A4
    buf=BytesIO()
    c=canvas.Canvas(buf,pagesize=A4)

    p5 = load_logo_portao5()
cia_img = load_logo_cia(companhia)

if p5:
    c.drawImage(p5, 2*cm, H - 75, width=110, height=52, mask='auto', preserveAspectRatio=True)
if cia_img:
    c.drawImage(cia_img, W - 2*cm - 95, H - 70, width=95, height=42, mask='auto', preserveAspectRatio=True)

    c.setFont("Helvetica-Bold",18)
    c.drawCentredString(W/2,H-45,"Informações do Voo")
    c.setFont("Helvetica",10)
    c.setFillColor(colors.HexColor("#555"))
    c.drawCentredString(W/2,H-60,f"Cotação gerada em {dt.datetime.now().strftime('%d/%m/%Y')}")

    y=H-120
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm,y,W-4*cm,26,6,fill=True,stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",12)
    c.drawString(2.3*cm,y+7,"✈️  Itinerário de IDA")

    y-=38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold",18)
    c.drawString(2.5*cm,y,f"{origem} → {destino}")
    c.setFont("Helvetica",11)
    c.drawString(2.5*cm,y-18,f"{ida_data}  |  {ida_s} → {ida_c}")

    y-=64
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm,y,W-4*cm,26,6,fill=True,stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold",12)
    c.drawString(2.3*cm,y+7,"🛬  Itinerário de VOLTA")

    y-=38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold",18)
    c.drawString(2.5*cm,y,f"{destino} → {origem}")
    c.setFont("Helvetica",11)
    c.drawString(2.5*cm,y-18,f"{vol_data}  |  {vol_s} → {vol_c}")

    y-=60
    c.setFont("Helvetica-Bold",13)
    c.drawString(2.5*cm,y,f"Passageiros: {passageiros}")
    y-=30
    c.setFont("Helvetica-Bold",15)
    c.drawString(2.5*cm,y,f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    y-=40
    c.setFillColor(COLOR_PRIMARY)
    c.setFont("Helvetica-Bold",14)
    c.drawString(2.5*cm,y,"💳 Opções de Parcelamento")
    y-=15
    c.setStrokeColor(COLOR_BORDER)
    c.rect(2.5*cm,y-180,W-5*cm,180,stroke=True,fill=False)
    y-=25
    c.setFillColor(colors.black)
    c.setFont("Helvetica",12)
    col1_x,col2_x=3*cm,7.5*cm
    for n,pmt in tabela_parc:
        c.drawString(col1_x,y,f"{n}x")
        c.drawString(col2_x,y,f"R$ {pmt:,.2f}")
        y-=16

    y-=25
    c.setFont("Helvetica",9)
    c.setFillColor(colors.grey)
    c.drawString(2*cm,y,"Condições sujeitas à disponibilidade. Remarcações e cancelamentos conforme regras da Cia Aérea,")
    y-=12
    c.drawString(2*cm,y,"podendo haver diferenças tarifárias e multas. Somos consultoria especializada em viagens.")
    y-=12
    c.drawString(2*cm,y,"Comece sua viagem embarcando pelo Portão 5 ✈️")
    y-=12
    c.drawString(2*cm,y,"📞 Contato para confirmação: (51) 99755-6161")

    c.save(); buf.seek(0)
    return buf

# ==============================
# INTERFACE
# ==============================
st.subheader("📸 Envie o print da passagem")
uploaded=st.file_uploader("Arraste e solte o print (PNG/JPG)",type=["png","jpg","jpeg"])

if uploaded:
    image=Image.open(uploaded)
    st.image(image,caption="Print recebido",use_column_width=True)
    texto=pytesseract.image_to_string(image,lang="por+eng")

    milhas=extrair_milhas(texto)
    taxa_ocr=extrair_taxa(texto)
    origem,destino=extrair_rota(texto)
    ida_data,ida_s,ida_c,vol_data,vol_s,vol_c=extrair_datas_horas(texto)

    st.markdown("### 🔎 Dados detectados automaticamente")
    col1,col2,col3 = st.columns(3)
    col1.metric("Origem", origem)
    col2.metric("Destino", destino)
    col3.metric("Taxa de Embarque", f"R$ {taxa_ocr:,.2f}")

    milhas = st.number_input("Total de Pontos/Milhas detectado — editável", value=float(milhas), step=100.0)

    st.markdown("---")
    st.subheader("✈️ Parâmetros da Cotação")

    companhia=st.selectbox("Companhia Aérea",["GOL","LATAM","AZUL"])
    passageiros=st.number_input("Passageiros",min_value=1,value=2)
    milheiro=st.number_input("Milheiro (R$/1000)",value=25.0,step=0.5)
    margem=st.number_input("Margem (%)",value=15.0,step=0.5)
    juros=st.number_input("Juros (% a.m.)",value=2.9,step=0.1)

    taxa=st.number_input("Taxa de Embarque (R$)",value=float(taxa_ocr),step=1.0,format="%.2f")
    valor_milhas=(milhas/1000.0)*milheiro
    subtotal=valor_milhas+taxa
    total_calc=round(subtotal*(1+margem/100.0),2)
    total_pix=st.number_input("Valor Total (Pix) — editável",value=total_calc,step=1.0,format="%.2f")

    tabela=calcular_parcelas(total_pix,juros)
    df=pd.DataFrame({"Parcelas":[f"{n}x" for n,_ in tabela],"Valor da Parcela (R$)":[p for _,p in tabela]})
    st.dataframe(df,use_container_width=True)

    pdf_buf=gerar_pdf(companhia,origem,destino,ida_data,ida_s,ida_c,vol_data,vol_s,vol_c,passageiros,total_pix,tabela)
    filename=f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf"
    st.download_button("📄 Baixar PDF",data=pdf_buf,file_name=filename,mime="application/pdf")

else:
    st.info("Envie o print (PNG ou JPG) da passagem para começar.")

