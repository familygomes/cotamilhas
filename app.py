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
# Em Cloud Linux, o tesseract costuma estar em /usr/bin/tesseract
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

COLOR_PRIMARY = colors.HexColor("#007C91")  # Azul Portão 5
COLOR_BORDER  = colors.HexColor("#E5E7EB")  # Cinza suave

HIST_CSV  = "cotacoes_historico.csv"
PDF_DIR   = "pdfs"
LOGOS_DIR = "logos"
os.makedirs(PDF_DIR, exist_ok=True)

# criar CSV se não existir
if not os.path.exists(HIST_CSV):
    pd.DataFrame(columns=[
        "Data/Hora", "Companhia", "Origem", "Destino",
        "Ida Data", "Ida Saída", "Ida Chegada",
        "Volta Data", "Volta Saída", "Volta Chegada",
        "Passageiros", "Milhas", "Taxa", "Milheiro",
        "Margem %", "Juros % a.m.", "Valor Pix"
    ]).to_csv(HIST_CSV, index=False)

st.title("🛫 CotaMilhas Express — Portão 5 Viagens")
st.caption("Envie o print, ajuste valores e gere uma cotação profissional em PDF.")

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

def extrair_milhas(texto: str) -> float:
    pad = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    nums = [int(n.replace(".", "")) for n in pad.findall(texto)]
    return float(max(nums)) if nums else 0.0

def extrair_taxa(texto: str) -> float:
    # LATAM costuma aparecer como "BRL 93,57"; fallback para "R$ 93,57"
    m = re.search(r"BRL\s*([\d\.,]+)", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"R\$\s*([\d\.,]+)", texto, re.IGNORECASE)
    return _to_float(m.group(1)) if m else 0.0

def extrair_rota(texto: str):
    m = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,30}\b([A-Z]{3})\b", texto)
    return (m.group(1), m.group(2)) if m else ("-", "-")

def extrair_datas_horas(texto: str):
    texto_s = _strip_accents(texto.lower())
    m1 = re.search(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
    m2 = re.search(r"(?:volta|retorno|voltar).*?(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s, re.DOTALL)
    ida_data, volta_data = "-", "-"
    ano = dt.datetime.now().year
    if m1:
        ida_data = f"{int(m1.group(1)):02d}/{MESES[m1.group(2)]}/{ano}"
    if m2:
        volta_data = f"{int(m2.group(1)):02d}/{MESES[m2.group(2)]}/{ano}"
    else:
        m2b = re.findall(r"(\d{1,2})\s*de\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", texto_s)
        if len(m2b) >= 2:
            d, mes = m2b[1]
            volta_data = f"{int(d):02d}/{MESES[mes]}/{ano}"

    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto_s)
    horas = [_pad_hhmm(h) for h in horas]
    ida_saida   = horas[0] if len(horas) >= 1 else "-"
    ida_chegada = horas[1] if len(horas) >= 2 else "-"
    volta_saida = horas[2] if len(horas) >= 3 else "-"
    volta_chegada = horas[3] if len(horas) >= 4 else "-"
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
    return _try_logo([os.path.join(LOGOS_DIR, "logo portao5viagens.png")])

def load_logo_cia(cia: str):
    cia = (cia or "").upper().strip()
    logos = {
        "GOL": ["logo gol.png", "logogol.png"],
        "LATAM": ["logo latam.png", "logolatam.png"],
        "AZUL": ["logo azul.png", "logoazul.png"]
    }
    for k, files in logos.items():
        if cia == k:
            return _try_logo([os.path.join(LOGOS_DIR, f) for f in files])
    return None

def gerar_pdf(
    companhia, origem, destino,
    ida_data, ida_saida, ida_chegada,
    volta_data, volta_saida, volta_chegada,
    passageiros,
    total_pix,
    tabela_parc
):
    W, H = A4
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Cabeçalho branco com logos
    p5 = load_logo_portao5()
    cia_img = load_logo_cia(companhia)
    if p5:      c.drawImage(p5, 2*cm, H - 70, width=95, height=42, mask='auto')
    if cia_img: c.drawImage(cia_img, W - 2*cm - 95, H - 70, width=95, height=42, mask='auto')

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W/2, H - 40, "Informações do Voo")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 2*cm, H - 55, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    # Itinerário Ida
    y = H - 120
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "✈️  Itinerário de Ida")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem}  →  {destino}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{ida_data}  |  {ida_saida} → {ida_chegada}")

    # Itinerário Volta
    y -= 64
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "🛬  Itinerário de Volta")

    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{destino}  →  {origem}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{volta_data}  |  {volta_saida} → {volta_chegada}")

    # Passageiros e Valor Pix
    y -= 60
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")

    y -= 30
    c.setFont("Helvetica-Bold", 15)
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    # Parcelamento com borda
    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(2.5*cm, y, "💳 Opções de Parcelamento")
    y -= 12
    c.setStrokeColor(COLOR_BORDER)
    box_height = len(tabela_parc) * 16 + 16
    c.rect(2.4*cm, y - box_height, W - 4.8*cm, box_height, stroke=True, fill=False)

    y -= 20
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    col1_x, col2_x = 2.7*cm, 7.0*cm
    for n, pmt in tabela_parc:
        c.drawString(col1_x, y, f"{n}x")
        c.drawString(col2_x, y, f"R$ {pmt:,.2f}")
        y -= 16
        if y < 2.5*cm:
            c.showPage()
            y = H - 3*cm

    # Condições
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(2.5*cm, y, "Condições da Cotação")
    y -= 15
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica", 10)
    texto = (
        "Esta cotação foi gerada com base na disponibilidade e valores obtidos no momento da simulação.\n\n"
        "Os preços estão sujeitos a variações até a confirmação da emissão.\n\n"
        "Pagamentos via Pix têm desconto para pagamento à vista. Parcelamentos podem ter acréscimos conforme condições informadas.\n\n"
        "Remarcações e Cancelamentos: sujeitos à disponibilidade de assentos, diferenças tarifárias e políticas de multa da companhia aérea.\n\n"
        "A Portão 5 Viagens atua como consultoria especializada em viagens, oferecendo suporte completo na escolha e emissão das passagens, garantindo o melhor custo-benefício e tranquilidade ao viajante.\n\n"
        "✈️ Comece sua viagem embarcando pelo Portão 5."
    )
    for line in texto.split("\n"):
        c.drawString(2.5*cm, y, line)
        y -= 14
        if y < 2.5*cm:
            c.showPage(); y = H - 3*cm

    c.save()
    buf.seek(0)
    return buf

# ------------------------ UI -------------------------
st.subheader("📷 Envie o print da passagem")
uploaded = st.file_uploader("Arraste ou escolha o arquivo", type=["png", "jpg", "jpeg"])

image = None
if uploaded:
    image = Image.open(uploaded)

if image:
    st.image(image, caption="Print recebido", use_column_width=True)

    try:
        # 'por+eng' funciona localmente; no Streamlit Cloud pode faltar 'por'.
        # Se der erro, troque para lang="eng".
        texto = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        texto = pytesseract.image_to_string(image, lang="eng")

    # ---- extrações a partir do OCR
    milhas_ocr = extrair_milhas(texto)
    taxa_ocr   = extrair_taxa(texto)
    origem_ocr, destino_ocr = extrair_rota(texto)
    ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada = extrair_datas_horas(texto)

    st.markdown("---")
    st.subheader("⚙️ Parâmetros da Cotação")

    companhia   = st.selectbox("Companhia aérea", ["GOL","LATAM","AZUL"], index=1 if "latam" in texto.lower() else 0)
    passageiros = st.number_input("Passageiros", min_value=1, value=2, step=1)

    origem  = st.text_input("Origem (IATA)",  value=origem_ocr or "-")
    destino = st.text_input("Destino (IATA)", value=destino_ocr or "-")

    ida_data    = st.text_input("Data da ida",            value=ida_data or "-")
    ida_saida   = st.text_input("Hora saída ida",         value=ida_saida or "-")
    ida_chegada = st.text_input("Hora chegada ida",       value=ida_chegada or "-")

    volta_data    = st.text_input("Data da volta",        value=volta_data or "-")
    volta_saida   = st.text_input("Hora saída volta",     value=volta_saida or "-")
    volta_chegada = st.text_input("Hora chegada volta",   value=volta_chegada or "-")

    milhas   = st.number_input("Milhas totais", value=float(milhas_ocr) if milhas_ocr else 0.0, step=100.0)
    taxa     = st.number_input("Taxa (R$)",     value=float(taxa_ocr) if taxa_ocr else 0.0, step=1.0, format="%.2f")
    milheiro = st.number_input("Milheiro (R$/1000)", value=25.0, step=0.5)
    margem   = st.number_input("Margem (%)", value=15.0, step=0.5)
    juros    = st.number_input("Juros (% a.m.)", value=2.9, step=0.1)

    if milhas > 0:
        valor_milhas = (milhas / 1000.0) * milheiro
        subtotal     = valor_milhas + taxa
        total_pix_sugerido = round(subtotal * (1 + margem/100.0), 2)

        st.markdown("---")
        st.subheader("💰 Cotação")

        # Campo editável para arredondar; recalcula tabela em cima dele
        total_pix = st.number_input("Valor total (Pix) — editável", value=total_pix_sugerido, step=1.0, format="%.2f")

        tabela = calcular_parcelas(total_pix, juros, max_n=10)
        df = pd.DataFrame({
            "Parcelas": [f"{n}x" for n,_ in tabela],
            "Valor da parcela (R$)": [p for _,p in tabela]
        })
        st.dataframe(df, use_container_width=True)

        # salva no histórico
        novo = pd.DataFrame([{
            "Data/Hora": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Companhia": companhia,
            "Origem": origem, "Destino": destino,
            "Ida Data": ida_data, "Ida Saída": ida_saida, "Ida Chegada": ida_chegada,
            "Volta Data": volta_data, "Volta Saída": volta_saida, "Volta Chegada": volta_chegada,
            "Passageiros": passageiros, "Milhas": milhas, "Taxa": taxa, "Milheiro": milheiro,
            "Margem %": margem, "Juros % a.m.": juros, "Valor Pix": total_pix
        }])
        if os.path.exists(HIST_CSV):
            hist = pd.read_csv(HIST_CSV)
            hist = pd.concat([novo, hist], ignore_index=True)
        else:
            hist = novo
        hist.to_csv(HIST_CSV, index=False)

        # gera PDF
        pdf_buf = gerar_pdf(companhia, origem, destino, ida_data, ida_saida, ida_chegada,
                            volta_data, volta_saida, volta_chegada, passageiros,
                            total_pix, tabela)

        filename = f"Portao5Viagens_Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf".replace(" ","_")
        filepath = os.path.join(PDF_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(pdf_buf.getvalue())

        st.download_button(
            label="📄 Baixar PDF",
            data=pdf_buf,
            file_name=filename,
            mime="application/pdf"
        )

        with st.expander("📊 Histórico de cotações"):
            st.dataframe(hist, use_container_width=True)

else:
    st.info("Envie um print (upload/drag) para começar.")

