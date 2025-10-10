import streamlit as st
import pytesseract
from PIL import Image
import re
import datetime as dt
import pandas as pd
import os

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from io import BytesIO

# ============ CONFIGURAÇÕES GERAIS ============
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # Streamlit Cloud

COLOR_PRIMARY = colors.HexColor("#007C91")  # Azul Portão 5 Viagens
COLOR_ACCENT  = colors.HexColor("#F58220")  # Laranja Portão 5 Viagens

HISTORICO_ARQ = "cotacoes_historico.csv"
if not os.path.exists(HISTORICO_ARQ):
    pd.DataFrame(columns=[
        "Data/Hora", "Companhia", "Origem", "Destino",
        "Ida Data", "Ida Saída", "Ida Chegada",
        "Volta Data", "Volta Saída", "Volta Chegada",
        "Passageiros", "Milhas", "Taxa", "Milheiro",
        "Margem %", "Juros % a.m.", "Valor Pix"
    ]).to_csv(HISTORICO_ARQ, index=False)

st.set_page_config(page_title="CotaMilhas Express • Portão 5 Viagens", layout="centered")
st.title("🛫 CotaMilhas Express — Portão 5 Viagens")
st.caption("Cole o print (Ctrl+V) ou envie o arquivo. Informe milheiro, margem e juros. Gere PDF profissional.")

# ============ FUNÇÕES AUXILIARES (OCR & PARSE) ============

def _to_float(num_str: str) -> float:
    if not num_str:
        return 0.0
    s = str(num_str).strip().replace("\xa0", " ")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def _norm_time(t: str) -> str:
    t = t.lower().replace("h", ":")
    m = re.match(r"^(\d{1,2})[:](\d{2})$", t)
    if not m:
        return t
    hh = int(m.group(1)); mm = m.group(2)
    return f"{hh:02d}:{mm}"

def extrair_milhas(texto: str) -> float:
    # pega TODAS as ocorrências "... milhas" e escolhe a MAIOR
    padrao = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    nums = [int(n.replace(".", "")) for n in padrao.findall(texto)]
    return float(max(nums)) if nums else 0.0

def extrair_taxa(texto: str) -> float:
    m = re.search(r"Taxa\s*de\s*embarque.*?R\$\s*([\d\.,]+)", texto, re.IGNORECASE | re.DOTALL)
    if m:
        return _to_float(m.group(1))
    m = re.search(r"milhas\s*\+\s*R\$\s*([\d\.,]+)", texto, re.IGNORECASE)
    if m:
        return _to_float(m.group(1))
    valores = [_to_float(x) for x in re.findall(r"R\$\s*([\d\.,]+)", texto, re.IGNORECASE)]
    cand = [v for v in valores if v >= 100]
    return min(cand) if cand else 0.0

def extrair_rota(texto: str):
    m = re.search(r"\b([A-Z]{3})\s*\d{1,2}[:h]\d{2}\s*([A-Z]{3})\s*\d{1,2}[:h]\d{2}", texto)
    if m:
        return m.group(1), m.group(2)
    m2 = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,20}\b([A-Z]{3})\b", texto)
    if m2 and m2.group(1) != "GOL":
        return m2.group(1), m2.group(2)
    return "-", "-"

def extrair_datas_horas(texto: str):
    datas = re.findall(r"\b(\d{2}/\d{2}(?:/\d{4})?)\b", texto)
    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto)
    ida_data  = datas[0] if len(datas) >= 1 else "-"
    volta_data = datas[1] if len(datas) >= 2 else "-"
    h = [_norm_time(x) for x in horas]
    ida_saida   = h[0] if len(h) >= 1 else "-"
    ida_chegada = h[1] if len(h) >= 2 else "-"
    volta_saida = h[2] if len(h) >= 3 else "-"
    volta_chegada = h[3] if len(h) >= 4 else "-"
    return ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada

def extrair_passageiros(texto: str) -> int:
    m = re.findall(r"(\d+)\s*(?:pessoas?|viajantes|adultos?)", texto, re.IGNORECASE)
    if m:
        return int(sorted([int(x) for x in m])[-1])
    return 1

# ============ PARCELAMENTO ============

def calcular_parcelas(pv: float, juros_am: float, max_n: int = 10):
    # juros_am em %, ex: 2.9
    i = juros_am / 100.0
    rows = []
    for n in range(1, max_n + 1):
        if i == 0:
            pmt = pv / n
        else:
            pmt = pv * (i * (1 + i) ** n) / ((1 + i) ** n - 1)
        rows.append((n, round(pmt, 2)))
    return rows

# ============ LOGOS ============

def carregar_logo_cia(nome_cia: str):
    base = "logos"
    mapa = {
        "GOL": os.path.join(base, "logo gol.png"),
        "LATAM": os.path.join(base, "logo latam.png"),
        "AZUL": os.path.join(base, "logo azul.png"),
    }
    path = mapa.get(nome_cia.upper())
    if path and os.path.exists(path):
        return ImageReader(path)
    return None

def carregar_logo_portao5():
    path = os.path.join("logos", "logo portao5viagens.png")
    if os.path.exists(path):
        return ImageReader(path)
    return None

# ============ PDF ============

def gerar_pdf(
    companhia, origem, destino,
    ida_data, ida_saida, ida_chegada,
    volta_data, volta_saida, volta_chegada,
    passageiros,
    total_pix,
    tabela_parcelas
):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Cabeçalho colorido
    c.setFillColor(COLOR_ACCENT)
    c.rect(0, H - 80, W, 80, fill=True, stroke=False)

    # Logos
    p5 = carregar_logo_portao5()
    cia_img = carregar_logo_cia(companhia)
    if p5:
        c.drawImage(p5, 2*cm, H - 70, width=90, height=40, mask='auto', preserveAspectRatio=True, anchor='sw')
    if cia_img:
        c.drawImage(cia_img, W - 2*cm - 90, H - 70, width=90, height=40, mask='auto', preserveAspectRatio=True, anchor='sw')

    # Título e data
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W/2, H - 45, "Informacoes do voo")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 2*cm, H - 60, f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y')}")

    # Bloco IDA
    y = H - 130
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "✈️  Itinerario de IDA")
    c.drawRightString(W - 2.3*cm, y + 7, "1 Trecho")

    # Detalhes Ida
    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem}  →  {destino}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{ida_data}  |  {ida_saida} → {ida_chegada}")

    # Bloco Volta
    y -= 64
    c.setFillColor(COLOR_PRIMARY)
    c.roundRect(2*cm, y, W - 4*cm, 26, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 7, "🛬  Itinerario de VOLTA")
    c.drawRightString(W - 2.3*cm, y + 7, "1 Trecho")

    # Detalhes Volta
    y -= 38
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{destino}  →  {origem}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 18, f"{volta_data}  |  {volta_saida} → {volta_chegada}")

    # Passageiros e Valores
    y -= 60
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")

    y -= 30
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.black)
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")

    # Tabela de Parcelamento (somente qtd x valor parc.)
    y -= 40
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_PRIMARY)
    c.drawString(2.5*cm, y, "💳 Opcoes de parcelamento")
    y -= 10
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.line(2.5*cm, y, W - 2.5*cm, y)

    y -= 18
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    col1_x = 2.6*cm
    col2_x = 7.0*cm

    for n, parcela in tabela_parcelas:
        c.drawString(col1_x, y, f"{n}x")
        c.drawString(col2_x, y, f"R$ {parcela:,.2f}")
        y -= 16
        if y < 2.5*cm:
            c.showPage()
            y = H - 3*cm

    # Rodapé
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawString(2*cm, 1.5*cm, "Gerado automaticamente via CotaMilhas Express")

    c.save()
    buf.seek(0)
    return buf

# ============ UI ============
st.subheader("Entrada do print")
st.write("Cole sua imagem aqui (Ctrl+V) ou clique para enviar.")
uploaded_file = st.file_uploader("PNG/JPG", type=["png", "jpg", "jpeg"], accept_multiple_files=False)

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Print recebido", use_column_width=True)

    try:
        texto = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        st.error("OCR indisponível. Garanta 'packages.txt' com tesseract-ocr e tesseract-ocr-por.")
        st.stop()

    # Extrações automáticas
    milhas_ocr = extrair_milhas(texto)
    taxa_ocr = extrair_taxa(texto)
    origem_ocr, destino_ocr = extrair_rota(texto)
    ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada = extrair_datas_horas(texto)
    pax_ocr = extrair_passageiros(texto)

    st.markdown("---")
    st.subheader("Parâmetros da cotação")
    companhia = st.selectbox("Companhia aérea", ["GOL", "LATAM", "AZUL"], index=0)
    passageiros = st.number_input("Passageiros", value=int(pax_ocr) if pax_ocr else 1, min_value=1, step=1)
    margem = st.number_input("Margem (%)", value=15.0, min_value=0.0, max_value=100.0, step=0.5)
    juros = st.number_input("Juros (% a.m.)", value=2.9, min_value=0.0, max_value=20.0, step=0.1)

    # Ajustes manuais (se OCR falhar em algo)
    st.markdown("### Ajustes (se necessário)")
    origem = st.text_input("Origem (IATA)", value=origem_ocr or "-")
    destino = st.text_input("Destino (IATA)", value=destino_ocr or "-")
    ida_data = st.text_input("Data da ida (dd/mm[/aaaa])", value=ida_data or "-")
    ida_saida = st.text_input("Hora saída ida (HH:MM)", value=ida_saida or "-")
    ida_chegada = st.text_input("Hora chegada ida (HH:MM)", value=ida_chegada or "-")
    volta_data = st.text_input("Data da volta (dd/mm[/aaaa])", value=volta_data or "-")
    volta_saida = st.text_input("Hora saída volta (HH:MM)", value=volta_saida or "-")
    volta_chegada = st.text_input("Hora chegada volta (HH:MM)", value=volta_chegada or "-")

    milhas = st.number_input("Milhas totais", value=float(milhas_ocr) if milhas_ocr else 0.0, step=100.0)
    taxa = st.number_input("Taxa de embarque (R$)", value=float(taxa_ocr) if taxa_ocr else 0.0, step=1.0, format="%.2f")
    milheiro = st.number_input("Valor do milheiro (R$/1000)", value=25.0, min_value=0.0, max_value=1000.0, step=0.5)

    if milhas > 0 and (taxa >= 0):
        valor_milhas = (milhas / 1000.0) * milheiro
        subtotal = valor_milhas + taxa
        total_pix = round(subtotal * (1 + margem/100.0), 2)

        # tabela de parcelas (1..10) — somente qtd x valor
        tabela = calcular_parcelas(total_pix, juros, max_n=10)

        st.markdown("---")
        st.subheader("💰 Cotação Final")
        st.write(f"**Valor total (Pix): R$ {total_pix:,.2f}**")

        # Mostrar tabela no app
        df_parc = pd.DataFrame({"Parcelas": [f"{n}x" for n,_ in tabela], "Valor da parcela (R$)": [v for _,v in tabela]})
        st.dataframe(df_parc, use_container_width=True)

        # Salvar histórico
        novo = pd.DataFrame([{
            "Data/Hora": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Companhia": companhia,
            "Origem": origem, "Destino": destino,
            "Ida Data": ida_data, "Ida Saída": ida_saida, "Ida Chegada": ida_chegada,
            "Volta Data": volta_data, "Volta Saída": volta_saida, "Volta Chegada": volta_chegada,
            "Passageiros": passageiros, "Milhas": milhas, "Taxa": taxa, "Milheiro": milheiro,
            "Margem %": margem, "Juros % a.m.": juros, "Valor Pix": total_pix
        }])
        hist = pd.read_csv(HISTORICO_ARQ)
        hist = pd.concat([novo, hist], ignore_index=True)
        hist.to_csv(HISTORICO_ARQ, index=False)

        # PDF
        pdf_buffer = gerar_pdf(
            companhia, origem, destino,
            ida_data, ida_saida, ida_chegada,
            volta_data, volta_saida, volta_chegada,
            passageiros,
            total_pix,
            tabela
        )
        filename = f"Cotacao_{companhia}_{origem}_{destino}_{dt.datetime.now().date()}.pdf".replace(" ", "_")
        st.download_button(
            label="📄 Baixar cotacao em PDF",
            data=pdf_buffer,
            file_name=filename,
            mime="application/pdf"
        )

        with st.expander("📊 Ver histórico de cotações"):
            st.dataframe(hist, use_container_width=True)
else:
    st.info("Cole o print (Ctrl+V) ou clique na área acima para enviar a imagem.")
