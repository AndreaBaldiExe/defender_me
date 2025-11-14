#!/usr/bin/env python3

import rospy
import requests     # Per chiamare Ollama (e in generale per richieste HTTP)
import json         # Per gestire JSON
import os           # Per costruire i percorsi ai file
import csv          # Mantenuto per compatibilità

# --- Librerie per lo Switch Cloud ---
from groq import Groq, APIError # NUOVO: Usiamo la libreria Groq
# Importiamo la NUOVA interfaccia del servizio (DEVI RICOMPILARE DOPO AVER SALVATO ComposeLIS.srv)
from signbot_msgs.srv import ComposeLIS, ComposeLISResponse 

# ----------------------------------------------------
# --- CONFIGURAZIONE E SWITCH DINAMICO LLM ---
# ----------------------------------------------------
SYSTEM_PROMPT = (
    "Sei Tiago, un robot assistente ospedaliero **empatico, conciso e professionale**, specializzato nella generazione di frasi in LIS. "
    "Il tuo scopo è comunicare in modo chiaro e rapido."
)

VINCOLI_LIS = (
    "RISPOSTA TECNICA: "
    "La tua risposta DEVE essere composta SOLO E SOLTANTO da parole presenti nella lista 'Segni Ammessi'. "
    "Le parole devono essere separate da un carattere pipe '|'. "
    "NON aggiungere MAI parole, punteggiatura o testo esplicativo (es. 'Certo', 'La frase è', etc.). "
    "Esempio valido: Ciao|Mario|Appuntamento|Oculista"
)

# Aggiunto per guidare il comportamento sociale (Cruciale)
GUIDA_COMPORTAMENTALE = (
    "PRIORITÀ SOCIALE: Devi usare l'informazione sull'espressione facciale del paziente per determinare il tono emotivo della frase. "
    "Se il paziente è 'irritato', usa un tono calmo (es. 'Calmo|Aspetta'). Se 'confuso', usa un tono rassicurante e lento."
)

# Legge la variabile d'ambiente per decidere la modalità. Default: OLLAMA per test locale.
LLM_MODE = os.environ.get('LLM_MODE', 'OLLAMA').upper() 
ROBOT_FALLBACK_SIGN = "Errore|Sistema|NonCapito"
ROSPARAM_MOTION_PATH = '/motions' # Percorso per i segni statici dal launch file

# --- Configurazione Ollama (Modalità Locale) ---
OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
OLLAMA_MODEL = "llama3:8b"

# --- Configurazione Cloud (Modalità CLOUD) ---
# AGGIORNATO: Passaggio a Groq
GROQ_MODEL = 'llama-3.1-8b-instant' # Modello supportato, veloce e ottimo per istruzioni vincolate
GROQ_CLIENT = None 

# ----------------------------------------------------
# --- Gestione Client API ---
# ----------------------------------------------------

def initialize_groq_client():
    """Inizializza il client Groq Cloud all'avvio se la modalità è CLOUD."""
    global GROQ_CLIENT
    if LLM_MODE == 'CLOUD':
        try:
            # Il client Groq cerca automaticamente la variabile GROQ_API_KEY
            GROQ_CLIENT = Groq() 
            rospy.loginfo("Client Groq Cloud inizializzato con successo.")
        except Exception as e:
            # La libreria solleva un errore se la chiave non è disponibile
            rospy.logerr(f"ERRORE CRITICO: Impossibile inizializzare il client Groq. Controlla GROQ_API_KEY: {e}")
            GROQ_CLIENT = None 


# --- Variabili Globali e Funzioni Helper ADATTATE ---

# NON carichiamo più ALLOWED_SIGNS qui. Viene preso dal Parameter Server.
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
PAZIENTI_DB_PATH = os.path.join(DATA_PATH, 'pazienti.csv')
DIZIONARIO_SEGNI_PATH = os.path.join(DATA_PATH, 'dizionario_segni.csv')


def get_allowed_signs_from_param_server():
    """Recupera i segni LIS validi dal Parameter Server."""
    try:
        # Recupera il dizionario caricato da lis_motions.yaml
        valid_motions_dict = rospy.get_param(ROSPARAM_MOTION_PATH)
        # Estrae solo le chiavi (i nomi dei segni)
        return list(valid_motions_dict.keys())
    except KeyError:
        rospy.logerr(f"Il parametro ROS '{ROSPARAM_MOTION_PATH}' non è stato trovato. Fallimento del caricamento YAML.")
        return []
    except Exception as e:
        rospy.logerr(f"Errore generico nel recupero dei segni: {e}")
        return []


def get_patient_data(person_id):
    """
    Funzione mantenuta solo per mantenere la struttura, ma non più chiamata direttamente 
    dalla logica LLM che usa i dati JSON.
    """
    # Questo è un placeholder. I dati biometrici VENGONO ORA PASSATI TRAMITE JSON dal collega.
    return None 


# ----------------------------------------------------
# --- FUNZIONE DI CHIAMATA UNIVERSALE CON SWITCH ---
# ----------------------------------------------------

def call_llm(prompt_text):
    """
    Funzione universale che chiama Ollama o Groq in base a LLM_MODE.
    """
    # 1. Recupera i segni ammessi in modo dinamico
    allowed_signs = get_allowed_signs_from_param_server()
    if not allowed_signs:
        rospy.logerr("Lista dei segni ammessi vuota. Non posso chiamare l'LLM.")
        return ROBOT_FALLBACK_SIGN

    # 2. Costruiamo il System Prompt (uguale per entrambi)
    system_prompt = f"""
        {SYSTEM_PROMPT}
        {GUIDA_COMPORTAMENTALE}
        {VINCOLI_LIS}
        
        Segni Ammessi: {allowed_signs}
        
        ---
        RICHIESTA SPECIFICA (Include i dati variabili del paziente):
        {prompt_text}
        """
    
    # 3. Logica dello Switch (OLLAMA vs. CLOUD)
    if LLM_MODE == 'OLLAMA':
        # --- Chiamata Ollama (Locale) ---
        rospy.loginfo("Modalità OLLAMA: Invio richiesta...")
        try:
            data = {"model": OLLAMA_MODEL, "prompt": system_prompt, "stream": False}
            response = requests.post(OLLAMA_URL, json=data, timeout=20.0)
            response.raise_for_status()
            response_json = response.json()
            generated_text = response_json.get('response', '').strip()
            generated_text = generated_text.replace('"', '').replace("'", "")
            rospy.loginfo(f"Ollama ha risposto: {generated_text}")
            return generated_text
        except requests.exceptions.RequestException as e:
            rospy.logerr(f"Errore di connessione a Ollama: {e}")
            return ROBOT_FALLBACK_SIGN

    else: # LLM_MODE == 'CLOUD'
        # --- Chiamata Groq (Cloud) ---
        rospy.loginfo("Modalità CLOUD: Invio richiesta Groq...")
        global GROQ_CLIENT
        if not GROQ_CLIENT: return ROBOT_FALLBACK_SIGN
        try:
            # Sintassi standard Groq (simile a OpenAI)
            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL, 
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.01 # Bassa temperatura per risposte vincolate
            )
            generated_text = response.choices[0].message.content.strip()
            rospy.loginfo(f"Groq ha risposto: {generated_text}")
            return generated_text
        except APIError as e:
            rospy.logerr(f"Errore API Groq: {e}")
            return ROBOT_FALLBACK_SIGN
        except Exception as e:
            rospy.logerr(f"Errore Groq inatteso: {e}")
            return ROBOT_FALLBACK_SIGN


# ----------------------------------------------------
# --- Funzione Principale (Callback del Servizio) ADATTATA AL JSON ---
# ----------------------------------------------------

def handle_compose_lis(req):
    """
    Funzione callback adattata alla NUOVA interfaccia: is_known, patient_data_json.
    """
    rospy.loginfo(f"Ricevuta richiesta. Conosciuto: {req.is_known}")

    # 1. Deserializzazione dei dati variabili (patient_data_json)
    try:
        patient_data = json.loads(req.patient_data_json)
    except json.JSONDecodeError:
        rospy.logerr("Errore JSON: I dati del paziente non sono JSON validi.")
        return ComposeLISResponse(lis_phrase="Errore|JSON|Dati", success=False)
    
    
    # 2. Costruiamo il prompt (basato sulla logica JSON e sul flag)
    if not req.is_known:
        # Caso A: Paziente SCONOSCIUTO
        prompt_text = (
            "Genera una frase concisa per un paziente sconosciuto, invitandolo ad andare alla registrazione. "
            f"Dati di contesto: {patient_data}"
        )
    else:
        # Caso B: Paziente CONOSCIUTO
        nome = patient_data.get('nome', 'Paziente')
        appuntamento = patient_data.get('appuntamento', 'nessun appuntamento')
        dottore = patient_data.get('dottore', 'sconosciuto')
        ora = patient_data.get('ora', 'non specificata')
        espressione = patient_data.get('espressione', 'neutra')

        prompt_text = (
            f"Genera una frase per il paziente {nome}. "
            f"Deve recarsi a: {appuntamento} con Dottore {dottore} alle ore {ora}. "
            f"La sua espressione facciale è: {espressione}. Usa queste informazioni per modulare il tono."
        )

    # 3. Chiamiamo l'LLM con la funzione universale
    lis_phrase = call_llm(prompt_text)

    # 4. Prepariamo la risposta del servizio
    response = ComposeLISResponse()
    if lis_phrase and lis_phrase != ROBOT_FALLBACK_SIGN:
        response.lis_phrase = lis_phrase
        response.success = True
    else:
        response.lis_phrase = "Registrazione|Richiesta"
        response.success = False

    return response

# --- Avvio del Nodo ---

def llm_composer_server():
    rospy.init_node('llm_composer_node')

    # Inizializza il client Groq se in modalità CLOUD
    initialize_groq_client()
    
    rospy.loginfo(f"Nodo avviato in modalità: {LLM_MODE}")
    rospy.loginfo(f"Attenzione: Stai usando la NUOVA interfaccia ComposeLIS.srv (JSON).")

    # Registra il servizio
    s = rospy.Service('/compose_lis_phrase', ComposeLIS, handle_compose_lis)
    rospy.loginfo("Servizio LLM Composer pronto a ricevere richieste.")

    rospy.spin()

if __name__ == "__main__":
    llm_composer_server()