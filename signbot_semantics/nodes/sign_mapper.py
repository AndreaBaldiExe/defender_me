#!/usr/bin/env python3

import rospy
import os
import json # Non strettamente necessario, ma utile per debug
from signbot_msgs.srv import MapToSign, MapToSignResponse

# --- Configurazione ---
ROSPARAM_MOTION_PATH = '/motions'
FALLBACK_SIGN = "NonCapito"  # Deve esistere come chiave in lis_motions.yaml
COMMAND_PREFIX = "phase execution2|" # Prefisso richiesto dal nodo di esecuzione di Tiago

def handle_map_to_sign(req):
    """
    Gestisce la richiesta di mappatura LIS, convalida i segni e imposta /sign.
    """
    rospy.loginfo(f"Mapper: Ricevuta frase LIS: {req.lis_phrase}")
    
    # 1. Recupera la lista dei segni validi dal Parameter Server
    try:
        # Ottiene il dizionario dei movimenti caricato dal launch file
        valid_motions_dict = rospy.get_param(ROSPARAM_MOTION_PATH)
        valid_signs = set(valid_motions_dict.keys())
        
        if not valid_signs:
            rospy.logerr("Mapper: Set di segni LIS vuoto. Controlla il caricamento di lis_motions.yaml.")
            return MapToSignResponse(success=False)

    except KeyError:
        rospy.logerr(f"Mapper: Parametro ROS '{ROSPARAM_MOTION_PATH}' non trovato.")
        return MapToSignResponse(success=False)
    except Exception as e:
        rospy.logerr(f"Mapper: Errore nel recupero parametri: {e}")
        return MapToSignResponse(success=False)


    # 2. Convalida e ricostruzione della frase LIS
    received_signs = req.lis_phrase.split('|')
    final_signs = []
    
    for sign in received_signs:
        # Rimuove eventuali spazi bianchi lasciati dall'LLM
        clean_sign = sign.strip() 
        
        if clean_sign in valid_signs:
            final_signs.append(clean_sign)
        else:
            # Segno non valido: Logga e usa il fallback
            rospy.logwarn(f"Mapper: Segno '{clean_sign}' non valido. Sostituito con '{FALLBACK_SIGN}'.")
            
            # Assicurati che il fallback sia nel set valido prima di usarlo
            if FALLBACK_SIGN in valid_signs:
                final_signs.append(FALLBACK_SIGN)
            else:
                rospy.logerr(f"Mapper: Fallback '{FALLBACK_SIGN}' non definito. Impossibile correggere l'errore.")
                # Se anche il fallback non esiste, la validazione fallisce.
                return MapToSignResponse(success=False) 

    # 3. Costruzione del comando finale ROS
    command_payload = "|".join(final_signs)
    final_string = COMMAND_PREFIX + command_payload
    
    # 4. Impostazione del parametro ROS /sign
    try:
        rospy.set_param('/sign', final_string)
        rospy.loginfo(f"Mapper: Parametro /sign impostato con successo: {final_string}")
        return MapToSignResponse(success=True)
    except Exception as e:
        rospy.logerr(f"Mapper: Impossibile impostare il parametro /sign: {e}")
        return MapToSignResponse(success=False)


def sign_mapper_server():
    rospy.init_node('sign_mapper_node')
    # Registra il servizio
    s = rospy.Service('map_and_execute_sign', MapToSign, handle_map_to_sign)
    rospy.loginfo("Servizio Sign Mapper pronto a ricevere richieste.")
    rospy.spin()

if __name__ == "__main__":
    sign_mapper_server()