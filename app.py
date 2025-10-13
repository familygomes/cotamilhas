# app.py — CotaMilhas Express • Portão 5 Viagens (v3.2)

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
# Configurações gerais
# ==============================
st.set_page_config(page_title="CotaMilhas Express • Portão 5 Viagens", layout="centered")
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # ambiente Streamlit Cloud

# Cores Portão 5
COLOR_PRIMARY = colors.HexColor("#007C91")   # Azul Portão 5
COLOR_BORDER  = colors.HexColor("#E5E7EB")   # Cinza claro (borda)

# Arquivos e pastas
HIST_CSV  = "cotacoes_historico.csv"
PDF_DIR   = "pdfs"
LOGOS_DIR = "logos"
os.makedirs(PDF_DIR, exist_ok=True)

# CSV inicial
if not os.path.exists(HIST_CSV):
    pd.DataFrame(columns=[
        "Data/Hora", "Companhia", "Origem", "Destino",
        "Ida Data", "Ida Saída", "Ida Chegada",
        "Volta Data", "Volta Saída", "Volta Chegada",
        "Passageiros", "Milhas", "Taxa", "Milheiro",
        "Margem %", "Juros % a.m.", "Valor Pix"
    ]).to_csv(HIST_CSV, index=False)

st.title("🛫 CotaMilhas Express — Portão 5 Viagens")
st.caption("Envie o print, ajuste milheiro/margem/juros, edite Taxa/Total quando necessário e gere o PDF profissional.")

# ==============================
# Utilitários
# ==============================
MESES = {"jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
         "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"}

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

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

def extrair_milhas(texto: str) -> float:
    # captura todas as ocorrências e usa a MAIOR como total
    pad = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    nums = [int(n.replace(".", "")) for n in pad.findall(texto)]
    return float(max(nums)) if nums else 0.0

def extrair_taxa(texto: str) -> float:
    # LATAM/GOL (R$ XXX,YY) / Azul ( + R$ 59,46 ) etc.
    m = re.search(r"(?:R\$|BRL)\s*([\d\.,]+)", texto, re.IGNORECASE)
    return _to_float(m.group(1)) if m else 0.0

def extrair_rota(texto: str):
    m = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,30}\b([A-Z]{3})\b", texto)
    return (m.group(1), m.group(2)) if m else ("-", "-")

def extrair_datas_horas(texto: str):
    texto_s = _strip_accents(texto.lower())

    # datas por extenso
    m1 = re.search(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    m2 = re.search(r"(?:volta|retorno|voltar).*?(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s, re.DOTALL)
    ano = dt.datetime.now().year

    ida_data = f"{int(m1.group(1)):02d}/{MESES[m1.group(2)]}/{ano}" if m1 else "-"
    if m2:
        volta_data = f"{int(m2.group(1)):02d}/{MESES[m2.group(2)]}/{ano}"
    else:
        m2b = re.findall(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
        volta_data = f"{int(m2b[1][0]):02d}/{MESES[m2b[1][1]]}/{ano}" if len(m2b) >= 2 else "-"

    # horas (primeiras 4 instâncias: ida s/ida c/volta s/volta c)
    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto_s)
    horas = [_pad_hhmm(h) for h in horas]
    ida_saida      = horas[0] if len(horas) >= 1 else "-"
    ida_chegada    = horas[1] if len(horas) >= 2 else "-"
    volta_saida    = horas[2] if len(horas) >= 3 else "-"
    volta_chegada  = horas[3] if len(horas) >= 4 else "-"
    return ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada

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

def _try_logo(paths):
    for p in paths:
        if os.path.exists(p):
            return ImageReader(p)
    return None

def load_logo_portao5():
    # nomes sem acento
    return _try_logo([os.path.join(LOGOS_DIR, "logo portao5viagens.png"),
                      os.path.join(LOGOS_DIR, "logo_portao5viagens.png")])

def load_logo_cia(cia: str):
    cia = (cia or "").upper().strip()
    if cia == "GOL":
        return _try_logo([os.path.join(LOGOS_DIR, "logo gol.png"),   os.path.join(LOGOS_DIR, "logogol.png")])
    if cia == "LATAM":
        return _try_logo([os.path.join(LOGOS_DIR, "logo latam.png"), os.path.join(LOGOS_DIR, "logolatam.png")])
    if cia == "AZUL":
        return _try_logo([os.path.join(LOGOS_DIR, "logo azul.png"),  os.path.join(LOGOS_DIR, "logoazul.png")])
    return None

# ==============================
# PDF
# ==============================
def gerar_pdf(
    companhia, origem, destino,
    ida_data, ida_saida, ida_chegada,
    volta_data, volta_saida, volta_chegada,
    passageiros, total_pix, tabela_parc
):
    W, H = A4
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Cabeçalho totalmente BRANCO, logos nas laterais
    c.setFillColor(colors.white)
    c.rect(0, H - 80, W, 80, fill=True, stroke=False)

    p5 = load_logo_portao5()
    cia_img = load_logo_cia(companhia)
    if p5:
        c.drawImage(p5, 2*cm, H - 70, width=95, height=42, mask='auto', preserveAspectRatio=True, anchor='sw')
    if cia_img:
        c.drawImage(cia_img, W - 2*cm - 95, H - 70, width=95, height=42, mask='auto', preserveAspectRatio=True, anchor='sw')

    # Título e data (data abaixo, fora das logos)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W/2, H - 45, "Informações do Voo")
    c.setFont("Helvetica", 10)
    c.drawCentredString(W/2, H - 60, f"Cotação gerada em {dt.datetime.now().strftime('%d/%m/%Y')}")

    # Bloco IDA
    y = H - 120
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "✈️  Itinerário de IDA")
    c.drawRightString(W - 2.3*cm, y + 7, "1 Trecho")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem}  →  {destino}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{ida_data}  |  {ida_saida} → {ida_chegada}")

    # Bloco VOLTA
    y -= 64
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "🛬  Itinerário de VOLTA")
    c.drawRightString(W - 2.3*cm, y + 7, "1 Trecho")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{destino}  →  {origem}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{volta_data}  |  {volta_saida} → {volta_chegada}")

    # Passageiros + Valor
    y -= 60
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")

    y -= 30
    c.setFont("Helvetica-Bold", 15)
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    # Parcelamento (com BORDA)
    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(2.5*cm, y, "💳 Opções de parcelamento")

    # borda do quadro
    box_top = y - 10
    box_left = 2.5*cm
    box_w = W - 5*cm
    # altura aproximada (10 linhas * 16px + margens)
    box_h = 16 * 10 + 20
    c.setStrokeColor(COLOR_BORDER)
    c.rect(box_left, box_top - box_h, box_w, box_h, stroke=True, fill=False)

    y = box_top - 18
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    col1_x, col2_x = 2.8*cm, 7.2*cm
    for n, pmt in tabela_parc:
        c.drawString(col1_x, y, f"{n}x")
        c.drawString(col2_x, y, f"R$ {pmt:,.2f}")
        y -= 16

    # Rodapé de condições
    y -= 18
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    cond = ("Condições sujeitas à disponibilidade. Remarcações/Cancelamentos conforme regras da companhia aérea, "
            "podendo haver diferenças tarifárias e multas. Somos consultoria especializada em viagens. "
            "Comece sua viagem embarcando pelo Portão 5 ✈️")
    c.drawString(2*cm, y, cond[:130])
    if len(cond) > 130:
        c.drawString(2*cm, y - 12, cond[130:])

    c.save()
    buf.seek(0)
    return buf

# ==============================
# Interface
# ==============================
st.subheader("Print da passagem")
c1, c2 = st.columns(2)
with c1:
    uploaded = st.file_uploader("Arraste/solte ou escolha um arquivo (PNG/JPG)", type=["png", "jpg", "jpeg"])
with c2:
    cam = st.camera_input("Ou use a câmera (opcional)")

image = None
if uploaded:
    image = Image.open(uploaded)
elif cam:
    image = Image.open(cam)

if image:
    st.image(image, caption="Print recebido", use_column_width=True)

    try:
        texto = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        st.error("OCR indisponível. Garanta packages.txt com tesseract-ocr e tesseract-ocr-por.")
        st.stop()

    # Extrações iniciais
    milhas_ocr = extrair_milhas(texto)
    taxa_ocr   = extrair_taxa(texto)
    origem_ocr, destino_ocr = extrair_rota(texto)
    ida_data, ida_s, ida_c, vol_data, vol_s, vol_c = extrair_datas_horas(texto)

    st.markdown("### Parâmetros da cotação")

    cA, cB = st.columns(2)
    with cA:
        companhia   = st.selectbox("Companhia aérea", ["GOL", "LATAM", "AZUL"], index=1 if "latam" in texto.lower() else 0)
        passageiros = st.number_input("Passageiros", min_value=1, value=2, step=1)
        milhas      = st.number_input("Milhas totais", value=float(milhas_ocr) if milhas_ocr else 0.0, step=100.0)
        milheiro    = st.number_input("Milheiro (R$/1000)", value=25.0, min_value=0.0, max_value=1000.0, step=0.5)
    with cB:
        margem      = st.number_input("Margem (%)", value=15.0, min_value=0.0, max_value=100.0, step=0.5)
        juros       = st.number_input("Juros (% a.m.)", value=2.9, min_value=0.0, max_value=20.0, step=0.1)

    st.markdown("#### Ajustes do itinerário")
    c1, c2 = st.columns(2)
    with c1:
        origem  = st.text_input("Origem (IATA)",  value=origem_ocr or "-")
        ida_data = st.text_input("Data da ida (dd/mm/aaaa)", value=ida_data or "-")
        vol_data = st.text_input("Data da volta (dd/mm/aaaa)", value=vol_data or "-")
    with c2:
        destino = st.text_input("Destino (IATA)", value=destino_ocr or "-")
        ida_s   = st.text_input("Hora saída ida (HH:MM)", value=ida_s or "-")
        ida_c   = st.text_input("Hora chegada ida (HH:MM)", value=ida_c or "-")
    c3, c4 = st.columns(2)
    with c3:
        vol_s   = st.text_input("Hora saída volta (HH:MM)", value=vol_s or "-")
    with c4:
        vol_c   = st.text_input("Hora chegada volta (HH:MM)", value=vol_c or "-")

    st.markdown("#### Valores")
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # TAXA EDITÁVEL e TOTAL EDITÁVEL (tabela recalcula ao mudar TOTAL)
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    if "usar_auto" not in st.session_state:
        st.session_state.usar_auto = True

    c1, c2 = st.columns(2)
    with c1:
        taxa = st.number_input("Taxa de embarque (R$)", value=float(taxa_ocr) if taxa_ocr else 0.0,
                               step=1.0, format="%.2f", key="taxa_in")
    with c2:
        st.session_state.usar_auto = st.checkbox("Sincronizar total com cálculo automático", value=st.session_state.usar_auto)

    # cálculo sugerido
    valor_milhas = (milhas / 1000.0) * milheiro if milhas > 0 else 0.0
    subtotal     = valor_milhas + taxa
    total_calc   = round(subtotal * (1 + margem/100.0), 2)

    # campo editável de TOTAL — se sincronizado, usa cálculo
    if st.session_state.usar_auto:
        total_pix_default = total_calc
    else:
        # mantém último valor manual se houver
        total_pix_default = float(st.session_state.get("total_pix_manual", total_calc))

    total_pix = st.number_input("Valor total (Pix) — editável", value=total_pix_default,
                                step=1.0, format="%.2f", key="total_pix_in")
    if not st.session_state.usar_auto:
        st.session_state.total_pix_manual = total_pix
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    # tabela de parcelas SEMPRE usa o total editável
    tabela = calcular_parcelas(total_pix, juros, max_n=10)
    df = pd.DataFrame({"Parcelas": [f"{n}x" for n, _ in tabela], "Valor da parcela (R$)": [p for _, p in tabela]})
    st.dataframe(df, use_container_width=True)

    # salvar histórico
    novo = pd.DataFrame([{
        "Data/Hora": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "Companhia": companhia,
        "Origem": origem, "Destino": destino,
        "Ida Data": ida_data, "Ida Saída": ida_s, "Ida Chegada": ida_c,
        "Volta Data": vol_data, "Volta Saída": vol_s, "Volta Chegada": vol_c,
        "Passageiros": passageiros, "Milhas": milhas, "Taxa": taxa, "Milheiro": milheiro,
        "Margem %": margem, "Juros % a.m.": juros, "Valor Pix": total_pix
    }])
    hist = pd.read_csv(HIST_CSV)
    hist = pd.concat([novo, hist], ignore_index=True)
    hist.to_csv(HIST_CSV, index=False)

    # PDF
    pdf_buf = gerar_pdf(
        companhia, origem, destino,
        ida_data, ida_s, ida_c,
        vol_data, vol_s, vol_c,
        passageiros, total_pix, tabela
    )

    filename = f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf".replace(" ", "_")
    with open(os.path.join(PDF_DIR, filename), "wb") as f:
        f.write(pdf_buf.getvalue())

    st.download_button("📄 Baixar PDF", data=pdf_buf, file_name=filename, mime="application/pdf")

    with st.expander("📊 Histórico de cotações"):
        st.dataframe(hist, use_container_width=True)

else:
    st.info("Envie um print (upload) ou use a câmera para iniciar.")
