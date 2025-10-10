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
    m = re.search(r"\b([A-Z]{3})\s*\d{1,2}[:h]\d{2}\s*([A-Z]{3})\s*\d{1,2}[:]()*

