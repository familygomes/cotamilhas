import streamlit as st
import pytesseract
from PIL import Image
import re
import datetime
import pandas as pd
import os

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from io import BytesIO

# --- Config OCR (Streamlit Cloud) ---
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"  # binário via packages.txt

# --- Persistência simples ---
HISTORICO_ARQ = "cotacoes_historico.csv"
if not os.path.exists(HISTORICO_ARQ):
    pd.DataFrame(columns=[
        "Data/Hora", "Origem", "Destino",
        "Ida Data", "Ida Saída", "Ida Chegada",
        "Volta Data", "Volta Saída", "Volta Chegada",
        "Passageiros", "Milhas", "Taxa", "Milheiro",
        "Total Pix", "Total Parcelado"
    ]).to_csv(HISTORICO_ARQ, index=False)

st.set_page_config(page_title="CotaMilhas Express", layout="centered")
st.title("🛫 CotaMilhas Express")
st.markdown("Envie o print da sua tela (Smiles/GOL/Latam/Azul), informe o milheiro e gere a cotação com PDF.")

# ---------- Utils ----------
def _to_float(num_str: str) -> float:
    if not num_str:
        return 0.0
    s = str(num_str).strip().replace("\xa0", " ")
    s = s.replace(".", "").replace(",", ".")
    try: return float(s)
    except: return 0.0

def _norm_time(t: str) -> str:
    # Normaliza "10h35" ou "10:35" -> "10:35"
    t = t.lower().replace("h", ":")
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if not m: return t
    hh = int(m.group(1)); mm = m.group(2)
    return f"{hh:02d}:{mm}"

def extrair_milhas(texto: str) -> float:
    padrao = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*milhas", re.IGNORECASE)
    nums = [int(n.replace(".", "")) for n in padrao.findall(texto)]
    return float(max(nums)) if nums else 0.0

def extrair_taxa(texto: str) -> float:
    m = re.search(r"Taxa\s*de\s*embarque.*?R\$\s*([\d\.,]+)", texto, re.IGNORECASE | re.DOTALL)
    if m: return _to_float(m.group(1))
    m = re.search(r"milhas\s*\+\s*R\$\s*([\d\.,]+)", texto, re.IGNORECASE)
    if m: return _to_float(m.group(1))
    valores = [_to_float(x) for x in re.findall(r"R\$\s*([\d\.,]+)", texto, re.IGNORECASE)]
    cand = [v for v in valores if v >= 100]
    return min(cand) if cand else 0.0

def extrair_rota(texto: str):
    # Procura pares IATA com horários
    m = re.search(r"\b([A-Z]{3})\s*\d{1,2}[:h]\d{2}\s*([A-Z]{3})\s*\d{1,2}[:h]\d{2}", texto)
    if m: return m.group(1), m.group(2)
    # Fallback: dois IATAs próximos
    m2 = re.search(r"\b([A-Z]{3})\b[^A-Z]{0,20}\b([A-Z]{3})\b", texto)
    if m2 and m2.group(1) != "GOL": return m2.group(1), m2.group(2)
    return "-", "-"

def extrair_passageiros(texto: str) -> int:
    m = re.findall(r"(\d+)\s*(?:pessoas?|viajantes|adultos?)", texto, re.IGNORECASE)
    if m: return int(sorted([int(x) for x in m])[-1])
    return 2  # default amigável

def extrair_datas_horas(texto: str):
    # Datas tipo 26/02/2026 ou 26/02
    datas = re.findall(r"\b(\d{2}/\d{2}(?:/\d{4})?)\b", texto)
    # Horas tipo 10h35 ou 10:35
    horas = re.findall(r"\b(\d{1,2}[:h]\d{2})\b", texto)

    ida_data  = datas[0] if len(datas) >= 1 else "-"
    volta_data = datas[1] if len(datas) >= 2 else "-"

    # Pega as quatro primeiras horas encontradas (ida: 2, volta: 2)
    h = [_norm_time(x) for x in horas]
    ida_saida   = h[0] if len(h) >= 1 else "-"
    ida_chegada = h[1] if len(h) >= 2 else "-"
    volta_saida = h[2] if len(h) >= 3 else "-"
    volta_chegada = h[3] if len(h) >= 4 else "-"

    return ida_data, ida_saida, ida_chegada, volta_data, volta_saida, volta_chegada

# ---------- PDF ----------
def gerar_pdf_universal(
    origem, destino,
    ida_data, ida_saida, ida_chegada,
    volta_data, volta_saida, volta_chegada,
    passageiros, milhas, taxa, milheiro,
    total_pix, total_parc
):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Cabeçalho
    c.setFillColor(colors.HexColor("#1F1F3D"))
    c.rect(0, H - 80, W, 80, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(2*cm, H - 50, "Informações do voo")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 2*cm, H - 50, f"Gerado em {datetime.datetime.now().strftime('%d/%m/%Y')}")

    # ---- Bloco IDA
    y = H - 130
    c.setFillColor(colors.HexColor("#1F1F3D"))
    c.roundRect(2*cm, y, W - 4*cm, 28, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 9, "✈️  Itinerário de IDA")
    c.drawRightString(W - 2.3*cm, y + 9, "1 Trecho")

    y -= 40
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{origem}  →  {destino}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 20, f"{ida_data}  |  {ida_saida} → {ida_chegada}")

    # ---- Bloco VOLTA
    y -= 70
    c.setFillColor(colors.HexColor("#1F1F3D"))
    c.roundRect(2*cm, y, W - 4*cm, 28, 6, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.3*cm, y + 9, "🛬  Itinerário de VOLTA")
    c.drawRightString(W - 2.3*cm, y + 9, "1 Trecho")

    y -= 40
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2.5*cm, y, f"{destino}  →  {origem}")
    c.setFont("Helvetica", 11)
    c.drawString(2.5*cm, y - 20, f"{volta_data}  |  {volta_saida} → {volta_chegada}")

    # ---- Passageiros e parâmetros
    y -= 70
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2.5*cm, y, f"Passageiros: {passageiros}")

    y -= 22
    c.setFont("Helvetica", 12)
    if milhas:
        c.drawString(2.5*cm, y, f"Total em milhas: {int(milhas):,}".replace(",", "."))
        y -= 18
    c.drawString(2.5*cm, y, f"Taxa de embarque: R$ {taxa:,.2f}")
    y -= 18
    c.drawString(2.5*cm, y, f"Valor do milheiro: R$ {milheiro:,.2f}")
    y -= 10
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.line(2.5*cm, y, W - 2.5*cm, y)

    # ---- Totais
    y -= 38
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawString(2.5*cm, y, f"💰 Valor total (Pix): R$ {total_pix:,.2f}")
    y -= 26
    c.setFillColor(colors.HexColor("#1F1F3D"))
    c.drawString(2.5*cm, y, f"💳 Parcelado em até 10x sem juros (+20%): R$ {total_parc:,.2f}")

    # Rodapé
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawString(2*cm, 1.5*cm, "Gerado automaticamente via CotaMilhas Express")

    c.save()
    buf.seek(0)
    return buf

# ---------- UI ----------
uploaded_file = st.file_uploader("📷 Envie o print da passagem:", type=["png", "jpg", "jpeg"])

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
    st.subheader("🔢 Dados extraídos:")
    st.write(f"- Origem: {origem_ocr}")
    st.write(f"- Destino: {destino_ocr}")
    st.write(f"- Ida: {ida_data}  |  {ida_saida} → {ida_chegada}")
    st.write(f"- Volta: {volta_data}  |  {volta_saida} → {volta_chegada}")
    st.write(f"- Milhas detectadas: {milhas_ocr if milhas_ocr else '—'}")
    st.write(f"- Taxa de embarque: R$ {taxa_ocr if taxa_ocr else '—'}")
    st.write(f"- Passageiros: {pax_ocr}")

    # Correções rápidas (se necessário)
    st.markdown("### ✍️ Ajustes manuais (se necessário)")
    origem = st.text_input("Origem (IATA)", value=origem_ocr or "-")
    destino = st.text_input("Destino (IATA)", value=destino_ocr or "-")
    ida_data = st.text_input("Data da ida (dd/mm[/aaaa])", value=ida_data or "-")
    ida_saida = st.text_input("Hora saída ida (HH:MM)", value=ida_saida or "-")
    ida_chegada = st.text_input("Hora chegada ida (HH:MM)", value=ida_chegada or "-")
    volta_data = st.text_input("Data da volta (dd/mm[/aaaa])", value=volta_data or "-")
    volta_saida = st.text_input("Hora saída volta (HH:MM)", value=volta_saida or "-")
    volta_chegada = st.text_input("Hora chegada volta (HH:MM)", value=volta_chegada or "-")
    passageiros = st.number_input("Passageiros", value=int(pax_ocr) if pax_ocr else 2, min_value=1, step=1)
    milhas = st.number_input("Milhas totais", value=float(milhas_ocr) if milhas_ocr else 0.0, step=100.0)
    taxa = st.number_input("Taxa de embarque (R$)", value=float(taxa_ocr) if taxa_ocr else 0.0, step=1.0, format="%.2f")

    if milhas > 0 and taxa >= 0:
        milheiro = st.number_input("💸 Valor do milheiro (R$ por 1.000 milhas):", min_value=10.0, max_value=300.0, step=0.5, value=25.0)

        if milheiro:
            # Base + margem 15%
            valor_milhas = (milhas / 1000.0) * milheiro
            subtotal = valor_milhas + taxa
            total_pix = round(subtotal * 1.15, 2)               # à vista (com margem 15%)
            total_parc = round(total_pix * 1.20, 2)             # +20% parcelado

            st.markdown("---")
            st.subheader("💰 Cotação Final")
            st.write(f"**Valor total (Pix): R$ {total_pix:,.2f}**")
            st.write(f"**Parcelado em até 10x sem juros (+20%): R$ {total_parc:,.2f}**")

            # Salvar histórico
            novo = pd.DataFrame([{
                "Data/Hora": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "Origem": origem, "Destino": destino,
                "Ida Data": ida_data, "Ida Saída": ida_saida, "Ida Chegada": ida_chegada,
                "Volta Data": volta_data, "Volta Saída": volta_saida, "Volta Chegada": volta_chegada,
                "Passageiros": passageiros, "Milhas": milhas, "Taxa": taxa, "Milheiro": milheiro,
                "Total Pix": total_pix, "Total Parcelado": total_parc
            }])
            hist = pd.read_csv(HISTORICO_ARQ)
            hist = pd.concat([novo, hist], ignore_index=True)
            hist.to_csv(HISTORICO_ARQ, index=False)

            # PDF
            pdf_buffer = gerar_pdf_universal(
                origem, destino,
                ida_data, ida_saida, ida_chegada,
                volta_data, volta_saida, volta_chegada,
                passageiros, milhas, taxa, milheiro,
                total_pix, total_parc
            )
            st.download_button(
                label="📄 Baixar cotação em PDF",
                data=pdf_buffer,
                file_name=f"Cotacao_{origem}_{destino}.pdf",
                mime="application/pdf"
            )

            with st.expander("📊 Ver histórico de cotações"):
                st.dataframe(hist)
else:
    st.info("Envie um print para iniciar a cotação.")
