#!/usr/bin/env python3

import rospy
import json
import os
# Importa i servizi necessari
from signbot_msgs.srv import ComposeLIS, ComposeLISRequest 
from signbot_msgs.srv import MapToSign, MapToSignRequest # Nuovo import per il Mapper

def call_mapper(lis_phrase_result):
    """
    Chiama il servizio del Sign Mapper (/map_and_execute_sign) 
    con la frase LIS ottenuta.
    """
    rospy.wait_for_service('map_and_execute_sign', timeout=5.0)
    try:
        map_to_sign = rospy.ServiceProxy('map_and_execute_sign', MapToSign)
        
        req = MapToSignRequest()
        req.lis_phrase = lis_phrase_result
        
        resp = map_to_sign(req)
        
        rospy.loginfo(f"Mapper: Chiamata riuscita. Successo finale: {resp.success}")
        return resp.success

    except rospy.ServiceException as e:
        rospy.logerr(f"Mapper: La chiamata al servizio è fallita: {e}")
        return False
    except rospy.exceptions.ROSException:
        rospy.logerr("Mapper: Servizio non disponibile.")
        return False

def client_test():
    """
    Simula il nodo CV/Manager inviando richieste e chiamando in cascata il Mapper.
    """
    rospy.wait_for_service('compose_lis_phrase', timeout=5.0)
    try:
        compose_lis = rospy.ServiceProxy('compose_lis_phrase', ComposeLIS)
        rospy.loginfo("Connessione al servizio /compose_lis_phrase riuscita.")

        # --- TEST 1: PAZIENTE CONOSCIUTO (Full Chain) ---
        rospy.loginfo("\n--- INIZIO TEST 1: PAZIENTE CONOSCIUTO (Full Chain) ---")
        
        data_known = {
            "nome": "Mario", 
            "cognome": "Rossi", 
            "eta": 45, 
            "espressione": "irritato", 
            "azione_richiesta": "Oculista Dott. Bianchi alle ore 10:00",
            "dati_biometrici": "ha una giacca blu"
        }
        
        req1 = ComposeLISRequest()
        req1.is_known = True
        req1.patient_data_json = json.dumps(data_known) 

        # 1. CHIAMA IL COMPOSER (LLM)
        resp1 = compose_lis(req1)
        
        rospy.loginfo(f"Composer: Risposta LIS: {resp1.lis_phrase}")
        
        if resp1.success and resp1.lis_phrase:
            # 2. CHIAMA IL MAPPER IN CASCATA
            call_mapper(resp1.lis_phrase)
        else:
            rospy.logerr("Composer fallito. Salto la mappatura.")

        rospy.sleep(2) 

        # --- TEST 2: PAZIENTE SCONOSCIUTO (Full Chain) ---
        rospy.loginfo("\n--- INIZIO TEST 2: PAZIENTE SCONOSCIUTO (Full Chain) ---")

        data_unknown = {
            "eta": 22, 
            "espressione": "confusa",
            "tempo_attesa": "5 minuti" 
        }

        req2 = ComposeLISRequest()
        req2.is_known = False
        req2.patient_data_json = json.dumps(data_unknown) 

        # 1. CHIAMA IL COMPOSER (LLM)
        resp2 = compose_lis(req2)
        
        rospy.loginfo(f"Composer: Risposta LIS: {resp2.lis_phrase}")
        
        if resp2.success and resp2.lis_phrase:
            # 2. CHIAMA IL MAPPER IN CASCATA
            call_mapper(resp2.lis_phrase)
        else:
            rospy.logerr("Composer fallito. Salto la mappatura.")

        rospy.loginfo("\n--- TEST COMPLESSIVO TERMINATO ---")


    except rospy.ServiceException as e:
        rospy.logerr(f"La chiamata al servizio è fallita: {e}")
    except rospy.exceptions.ROSException:
        rospy.logerr("Il servizio /compose_lis_phrase non è disponibile. roscore o il nodo server sono spenti.")
    except Exception as e:
        rospy.logerr(f"Si è verificato un errore generale: {e}")

if __name__ == "__main__":
    rospy.init_node('lis_test_client', anonymous=True)
    client_test()