import streamlit as st
import pandas as pd
import sqlite3
import pdfplumber
import re
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------
st.set_page_config(page_title="DomusSplit Pro", page_icon="🏠", layout="wide")
DB_NAME = "domus.db"

# ---------------------------------------------------------
# DATABASE & ARCHIVIO
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Reset sicuro delle tabelle per evitare incompatibilità di schema
    cursor.execute('DROP TABLE IF EXISTS bollette')
    cursor.execute('DROP TABLE IF EXISTS incassi')
    
    # Tabella Bollette ed Estrazioni OCR/PDF
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bollette (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            servizio TEXT NOT NULL,
            data_emissione DATE,
            data_scadenza DATE,
            importo_totale REAL NOT NULL,
            kwh_totali REAL DEFAULT 0,
            kwh_claudio REAL DEFAULT 0,
            mc_gpl REAL DEFAULT 0,
            prezzo_litro_gpl REAL DEFAULT 0,
            quota_claudio REAL NOT NULL,
            quota_sergio REAL NOT NULL,
            note TEXT
        )
    ''')
    
    # Tabella Registro Incassi (Cash / Bonifici)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incassi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_incasso DATE NOT NULL,
            importo REAL NOT NULL,
            modalita TEXT NOT NULL,
            iban_destinazione TEXT,
            note TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_NAME)

# ---------------------------------------------------------
# MOTORE DI PARSING PDF (ESTRAZIONE AUTOMATICA)
# ---------------------------------------------------------
def estrai_dati_pdf(uploaded_file, servizio):
    importo = 0.0
    kwh_tot = 0.0
    
    with pdfplumber.open(uploaded_file) as pdf:
        testo = ""
        for page in pdf.pages:
            testo += page.extract_text() or ""
            
    match_importo = re.search(r'TOTAL[EO]\I?\s*DATI?\s*SPESA.*?([\d\.,]+)\s*€', testo, re.IGNORECASE) or \
                    re.search(r'Importo\s*totale.*?([\d\.,]+)\s*€', testo, re.IGNORECASE) or \
                    re.search(r'TOTALE\s*DA\s*PAGARE.*?([\d\.,]+)', testo, re.IGNORECASE)
    if match_importo:
        val = match_importo.group(1).replace('.', '').replace(',', '.')
        try: importo = float(val)
        except: pass

    match_kwh = re.search(r'([\d\.,]+)\s*kWh', testo, re.IGNORECASE)
    if match_kwh:
        val_k = match_kwh.group(1).replace('.', '').replace(',', '.')
        try: kwh_tot = float(val_k)
        except: pass
        
    return importo, kwh_tot

# ---------------------------------------------------------
# INIZIALIZZAZIONE & INTERFACCIA
# ---------------------------------------------------------
init_db()

st.title("🏠 DomusSplit Pro — Gestione & Rendicontazione Utenze")

ruolo = st.sidebar.radio("Seleziona Profilo Utente:", ["Sergio (Admin)", "Claudio (Ospite)"])

if ruolo == "Sergio (Admin)":
    tab1, tab2, tab3 = st.tabs(["📄 Nuova Bolletta (PDF/Foto)", "💰 Registro Incassi Claudio", "📊 Storico Saldi & WhatsApp"])
    
    with tab1:
        st.subheader("Caricamento ed Estrazione Automatica Bolletta")
        servizio = st.selectbox("Servizio / Utenza:", ["ENGIE Monofase", "ENEL Trifase", "GPL", "TIM Mobile"])
        
        pdf_file = st.file_uploader("Carica File PDF della Bolletta", type=["pdf"])
        
        imp_estratto, kwh_estratta = 0.0, 0.0
        if pdf_file is not None:
            imp_estratto, kwh_estratta = estrai_dati_pdf(pdf_file, servizio)
            st.success("Estrazione dati da PDF completata!")
            
        col1, col2 = st.columns(2)
        with col1:
            importo_tot = st.number_input("Importo Totale Bolletta (€):", value=imp_estratto, step=0.01)
            data_em = st.date_input("Data Emissione", datetime.now())
            
            kwh_tot, kwh_c, mc_gpl, p_litro = 0.0, 0.0, 0.0, 0.0
            if servizio == "ENGIE Monofase":
                kwh_tot = st.number_input("kWh Totali Bolletta:", value=kwh_estratta)
                kwh_c = st.number_input("kWh Contatore Claudio:", min_value=0.0)
            elif servizio == "GPL":
                mc_gpl = st.number_input("m³ GPL Consumati:", min_value=0.0)
                p_litro = st.number_input("Prezzo/Litro (€):", min_value=0.0)

        with col2:
            st.subheader("Ripartizione Calcolata")
            quota_c, quota_s = 0.0, 0.0
            
            if servizio == "ENGIE Monofase" and kwh_tot > 0:
                quota_c = (kwh_c / kwh_tot) * importo_tot
                quota_s = importo_tot - quota_c
            elif servizio == "ENEL Trifase":
                canone_tv = st.number_input("Canone TV da defalcare (€):", value=0.0)
                netto = importo_tot - canone_tv
                quota_c = netto * 0.40
                quota_s = (netto * 0.60) + canone_tv
            elif servizio == "GPL":
                litri = mc_gpl * 4.17
                valore = litri * p_litro
                quota_c = valore / 2.0
                quota_s = valore / 2.0
            elif servizio == "TIM Mobile":
                quota_c = importo_tot
                quota_s = 0.0
                
            st.metric("Quota Claudio", f"€ {quota_c:.2f}")
            st.metric("Quota Sergio", f"€ {quota_s:.2f}")
            
            if st.button("💾 Registra in Archivio"):
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO bollette (servizio, data_emissione, importo_totale, kwh_totali, kwh_claudio, mc_gpl, prezzo_litro_gpl, quota_claudio, quota_sergio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (servizio, data_em.strftime("%Y-%m-%d"), importo_tot, kwh_tot, kwh_c, mc_gpl, p_litro, quota_c, quota_s))
                conn.commit()
                conn.close()
                st.success("Bolletta salvata correttamente!")

    with tab2:
        st.subheader("Registra Pagamento Ricevuto da Claudio")
        c1, c2 = st.columns(2)
        with c1:
            data_inc = st.date_input("Data Incasso:", datetime.now())
            imp_inc = st.number_input("Importo Ricevuto (€):", min_value=0.0, step=0.01)
        with c2:
            modalita = st.selectbox("Tipologia Pagamento:", ["Bonifico", "Contanti (Cash)"])
            iban_dest = ""
            if modalita == "Bonifico":
                iban_dest = st.text_input("IBAN di Destinazione:", value="IT60X0000000000000000000000")
            note_inc = st.text_input("Note/Causale:")
            
        if st.button("✅ Registra Incasso"):
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO incassi (data_incasso, importo, modalita, iban_destinazione, note)
                VALUES (?, ?, ?, ?, ?)
            ''', (data_inc.strftime("%Y-%m-%d"), imp_inc, modalita, iban_dest, note_inc))
            conn.commit()
            conn.close()
            st.success("Incasso registrato!")

    with tab3:
        st.subheader("Contabilità & Saldo Progressivo")
        conn = get_connection()
        df_b = pd.read_sql_query("SELECT * FROM bollette", conn)
        df_i = pd.read_sql_query("SELECT * FROM incassi", conn)
        conn.close()
        
        tot_dovuto = df_b['quota_claudio'].sum() if not df_b.empty else 0.0
        tot_incassato = df_i['importo'].sum() if not df_i.empty else 0.0
        saldo_netto = tot_dovuto - tot_incassato
        
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Totale Spese Spettanti", f"€ {tot_dovuto:.2f}")
        col_s2.metric("Totale Pagato da Claudio", f"€ {tot_incassato:.2f}")
        col_s3.metric("SALDO ATTUALE (DA SALDARE)", f"€ {saldo_netto:.2f}")
        
        st.markdown("---")
        st.write("### Notifica WhatsApp per Claudio")
        msg = f"Ciao Claudio, ecco il riepilogo contabile aggiornato Domus:\n"
        msg += f"- Addebiti Utenze Totali: € {tot_dovuto:.2f}\n"
        msg += f"- Totale Pagamenti Ricevuti: € {tot_incassato:.2f}\n"
        msg += f"- **SALDO NETTO DA SALDARE: € {saldo_netto:.2f}**\n\n"
        msg += f"Puoi versare tramite Bonifico o Contanti."
        
        st.code(msg, language="markdown")

else:
    st.title("🏡 Vista Trasparenza — Claudio")
    conn = get_connection()
    df_b = pd.read_sql_query("SELECT servizio, data_emissione, importo_totale, quota_claudio FROM bollette", conn)
    df_i = pd.read_sql_query("SELECT data_incasso, importo, modalita, note FROM incassi", conn)
    conn.close()
    
    tot_dovuto = df_b['quota_claudio'].sum() if not df_b.empty else 0.0
    tot_incassato = df_i['importo'].sum() if not df_i.empty else 0.0
    
    st.metric("Tuo Saldo Attuale da Saldare", f"€ {tot_dovuto - tot_incassato:.2f}")
    
    st.subheader("Dettaglio Addebiti Utenze")
    st.dataframe(df_b, use_container_width=True)
    
    st.subheader("Storico Tuoi Pagamenti Effettuati")
    st.dataframe(df_i, use_container_width=True)
