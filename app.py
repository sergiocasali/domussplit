import streamlit as st
import pandas as pd
import sqlite3
import urllib.parse
from datetime import datetime

# ---------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="DomusSplit",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "domus.db"

# ---------------------------------------------------------
# FUNZIONI DATABASE (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configurazione (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parametro TEXT UNIQUE NOT NULL,
            valore TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bollette (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            servizio TEXT NOT NULL,
            data_emissione DATE NOT NULL,
            importo_totale REAL NOT NULL,
            consumo_totale REAL,
            consumo_claudio REAL,
            quota_claudio REAL NOT NULL,
            quota_sergio REAL NOT NULL,
            note TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_registrazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            periodo_riferimento TEXT NOT NULL,
            importo_totale REAL NOT NULL,
            quota_sergio REAL NOT NULL,
            quota_claudio REAL NOT NULL,
            stato_pagamento TEXT DEFAULT 'In Attesa',
            note TEXT
        )
    ''')
    
    # Inserimento valori di default se non presenti
    defaults = [
        ('gpl_rapporto_m3_litri', '4.17'),
        ('tim_mobile_quota_fissa', '50.0')
    ]
    for param, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO configurazione (parametro, valore) VALUES (?, ?)', (param, val))
        
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_NAME)

# ---------------------------------------------------------
# INIZIALIZZAZIONE DB E SESSIONE
# ---------------------------------------------------------
init_db()

if 'user_role' not in st.session_state:
    st.session_state['user_role'] = 'Sergio (Admin)'

# ---------------------------------------------------------
# SIDEBAR - NAVIGAZIONE E SELEZIONE RUOLO
# ---------------------------------------------------------
st.sidebar.title("🏠 DomusSplit")
st.sidebar.markdown("---")
role = st.sidebar.radio("Seleziona Profilo Utente:", ["Sergio (Admin)", "Claudio (Ospite)"])
st.session_state['user_role'] = role
st.sidebar.markdown("---")
st.sidebar.info(f"Profilo Attivo: **{st.session_state['user_role']}**")

# ---------------------------------------------------------
# VISTA: SERGIO (ADMINISTRATOR DASHBOARD)
# ---------------------------------------------------------
if st.session_state['user_role'] == "Sergio (Admin)":
    st.title("⚙️ Dashboard Amministratore — Sergio")
    
    tab1, tab2, tab3 = st.tabs(["➕ Nuova Bolletta", "📊 Storico & Conguagli", "⚙️ Impostazioni Sistema"])
    
    with tab1:
        st.subheader("Inserimento e Ripartizione Utenze")
        
        col1, col2 = st.columns(2)
        with col1:
            servizio = st.selectbox("Seleziona Servizio / Utenza", [
                "ENGIE Monofase",
                "ENEL Trifase",
                "GPL (Gas)",
                "TIM Mobile"
            ])
            data_em = st.date_input("Data Emissione", datetime.now())
            importo_tot = st.number_input("Importo Totale Bolletta (€)", min_value=0.0, step=0.01)
            
        with col2:
            quota_claudio = 0.0
            quota_sergio = 0.0
            
            if servizio == "ENGIE Monofase":
                kwh_tot = st.number_input("Consumo Totale kWh", min_value=0.1, step=1.0)
                kwh_claudio = st.number_input("Consumo Claudio kWh", min_value=0.0, step=1.0)
                if kwh_tot > 0:
                    quota_claudio = (kwh_claudio / kwh_tot) * importo_tot
                    quota_sergio = importo_tot - quota_claudio
                    
            elif servizio == "ENEL Trifase":
                perc_claudio = st.slider("Percentuale Quota Claudio (%)", 0, 100, 40)
                quota_claudio = (perc_claudio / 100.0) * importo_tot
                quota_sergio = importo_tot - quota_claudio
                
            elif servizio == "GPL (Gas)":
                st.caption("Conversione: 1 m³ = 4.17 Litri")
                m3_tot = st.number_input("Consumo Totale Gas (m³)", min_value=0.1, step=0.1)
                m3_claudio = st.number_input("Consumo Claudio Gas (m³)", min_value=0.0, step=0.1)
                
                litri_tot = m3_tot * 4.17
                litri_claudio = m3_claudio * 4.17
                
                if litri_tot > 0:
                    costo_litro = importo_tot / litri_tot
                    quota_claudio = litri_claudio * costo_litro
                    quota_sergio = importo_tot - quota_claudio
                    st.write(f"**Litri Claudio:** {litri_claudio:.2f} L | **Costo/Litro:** €{costo_litro:.3f}")
                    
            elif servizio == "TIM Mobile":
                quota_claudio = importo_tot
                quota_sergio = 0.0
                st.caption("Linea mobile Claudio (+39 3914050128): Addebito diretto 100%")

        note_bolletta = st.text_input("Note aggiuntive (opzionale)")
        
        st.markdown("---")
        st.write("### Ripartizione Calcolata:")
        c_res1, c_res2 = st.columns(2)
        c_res1.metric("Quota Claudio", f"€ {quota_claudio:.2f}")
        c_res2.metric("Quota Sergio", f"€ {quota_sergio:.2f}")
        
        if st.button("💾 Registra Bolletta"):
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bollette (servizio, data_emissione, importo_totale, quota_claudio, quota_sergio, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (servizio, data_em.strftime("%Y-%m-%d"), importo_tot, quota_claudio, quota_sergio, note_bolletta))
            
            cursor.execute('''
                INSERT INTO storico (periodo_riferimento, importo_totale, quota_sergio, quota_claudio, note)
                VALUES (?, ?, ?, ?, ?)
            ''', (f"{servizio} - {data_em.strftime('%b %Y')}", importo_tot, quota_sergio, quota_claudio, note_bolletta))
            
            conn.commit()
            conn.close()
            st.success("Bolletta registrata con successo nel database!")

    with tab2:
        st.subheader("Registro Generale Utenze e Saldi")
        conn = get_connection()
        df_bollette = pd.read_sql_query("SELECT * FROM bollette ORDER BY data_emissione DESC", conn)
        conn.close()
        
        if not df_bollette.empty:
            st.dataframe(df_bollette, use_container_width=True)
            
            st.markdown("### 📱 Generatore Notifica WhatsApp per Claudio")
            tot_claudio = df_bollette['quota_claudio'].sum()
            
            msg = f"Ciao Claudio! 👋 Ecco il riepilogo aggiornato delle utenze Domus:\n\n"
            for _, row in df_bollette.head(5).iterrows():
                msg += f"• *{row['servizio']}* ({row['data_emissione']}): €{row['quota_claudio']:.2f}\n"
            msg += f"\n*Totale da saldare: €{tot_claudio:.2f}*\n\nGrazie!"
            
            st.text_area("Anteprima Messaggio:", msg, height=150)
            
            encoded_msg = urllib.parse.quote(msg)
            wa_url = f"https://wa.me/?text={encoded_msg}"
            st.markdown(f"[📲 Invia Notifica via WhatsApp]({wa_url})")
        else:
            st.info("Nessuna bolletta presente nel database.")

    with tab3:
        st.subheader("Parametri di Sistema")
        conn = get_connection()
        df_config = pd.read_sql_query("SELECT * FROM configurazione", conn)
        conn.close()
        st.dataframe(df_config, use_container_width=True)

# ---------------------------------------------------------
# VISTA: CLAUDIO (GUEST VIEW)
# ---------------------------------------------------------
else:
    st.title("🏡 Vista Ospite — Claudio")
    st.write("Benvenuto nel portale trasparente per la consultazione dei consumi e delle quote utenze.")
    
    conn = get_connection()
    df_storico = pd.read_sql_query("SELECT id, data_registrazione, periodo_riferimento, quota_claudio, stato_pagamento FROM storico ORDER BY id DESC", conn)
    conn.close()
    
    if not df_storico.empty:
        tot_da_pagare = df_storico[df_storico['stato_pagamento'] == 'In Attesa']['quota_claudio'].sum()
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Totale Attualmente Dovuto", f"€ {tot_da_pagare:.2f}")
        col_m2.metric("Stato Ultimo Saldo", df_storico['stato_pagamento'].iloc[0])
        
        st.markdown("### Dettaglio Quote Spettanti")
        st.dataframe(df_storico, use_container_width=True)
        
        st.info("💡 Per concordare il saldo o richiedere chiarimenti, contatta Sergio tramite WhatsApp.")
    else:
        st.info("Non ci sono quote o bollette registrate al momento.")
