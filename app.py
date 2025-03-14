from flask import Flask, jsonify, send_file, render_template, request
import time
import jwt
import requests
import pandas as pd
import os
import openpyxl
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app)

# 🔑 Authentification BoondManager
USER_TOKEN = "37332e6d616e747261"
CLIENT_TOKEN = "6d616e747261"
CLIENT_KEY = "06daebfc3aae9ef09791"

# 🔑 Génération du token JWT
jwt_token = jwt.encode({
    "userToken": USER_TOKEN,
    "clientToken": CLIENT_TOKEN,
    "time": int(time.time()),
    "mode": "normal"
}, CLIENT_KEY, algorithm="HS256")

# 📌 Headers pour l'API BoondManager
HEADERS = {
    "X-Jwt-Client-BoondManager": jwt_token,
    "Accept": "application/json"
}

API_URL = "https://ui.boondmanager.com/api/opportunities"

# 📌 Dictionnaire des états de fiche de poste
ETAT_FICHE_DE_POSTE = {
    0: "Piste identifiée",
    5: "En cours",
    1: "Gagnée",
    2: "Fermée"
}

def format_date(date_str):
    """Formate la date en JJ/MM/AAAA"""
    if date_str and date_str != "Non renseigné":
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z").strftime("%d/%m/%Y")
        except ValueError:
            return date_str  
    return "Non renseigné"

@app.route("/get_fiches", methods=["GET"])
def get_fiches():
    """Récupère et retourne les fiches de poste sous forme de JSON avec filtres."""
    
    # 📌 Récupération des paramètres des filtres
    filtres_etats = request.args.getlist("etat")  # Liste de plusieurs états sélectionnés
    date_debut = request.args.get("date_debut", "").strip()
    date_fin = request.args.get("date_fin", "").strip()

    page = 1
    limit = 100
    all_fiches = []
    contacts_mapping = {}
    companies_mapping = {}

    while True:
        response = requests.get(API_URL, headers=HEADERS, params={"page": page, "limit": limit, "filters[state]": "0,1,2,5"})
        if response.status_code != 200:
            return jsonify({"error": "Erreur API", "status": response.status_code}), response.status_code

        data = response.json()
        fiches = data.get("data", [])
        total_rows = data.get("meta", {}).get("totals", {}).get("rows", 0)

        included = data.get("included", [])
        for item in included:
            if item.get("type") == "contact":
                contacts_mapping[item.get("id")] = item.get("attributes", {}).get("firstName", "Inconnu") + " " + item.get("attributes", {}).get("lastName", "Inconnu")
            if item.get("type") == "company":
                companies_mapping[item.get("id")] = item.get("attributes", {}).get("name", "Non attribué")

        all_fiches.extend(fiches)

        if len(all_fiches) >= total_rows:
            break
        page += 1

    if not all_fiches:
        return jsonify({"message": "Aucune fiche de poste trouvée"}), 200

    fiche_de_poste_list = []
    for item in all_fiches:
        attributes = item.get("attributes", {})
        relationships = item.get("relationships", {})

        company_data = relationships.get("company", {}).get("data", {})
        company_id = company_data.get("id") if isinstance(company_data, dict) else None
        client_company_name = companies_mapping.get(company_id, "Non attribué")

        contact_data = relationships.get("contact", {}).get("data", {})
        contact_id = contact_data.get("id") if isinstance(contact_data, dict) else None
        client_contact_name = contacts_mapping.get(contact_id, "Non attribué")

        state_code = attributes.get("state", -1)
        state_label = ETAT_FICHE_DE_POSTE.get(state_code, f"État inconnu ({state_code})")
        nombre_positionnements = attributes.get("numberOfActivePositionings", 0)

        # ✅ Récupération correcte de la date de clôture
        date_cloture = attributes.get("closingDate", "Non renseigné")  # Vérifie bien la clé "closingDate"
        formatted_cloture_date = format_date(date_cloture)

        # 📌 Vérification des filtres multi-états
        if filtres_etats and state_label not in filtres_etats:
            continue

        # 📌 Vérification du filtre date
        fiche_date = attributes.get("creationDate", "Non renseigné")
        formatted_date = format_date(fiche_date)
        if date_debut and date_fin and formatted_date != "Non renseigné":
            date_obj = datetime.strptime(formatted_date, "%d/%m/%Y")
            date_debut_obj = datetime.strptime(date_debut, "%d/%m/%Y")
            date_fin_obj = datetime.strptime(date_fin, "%d/%m/%Y")
            if not (date_debut_obj <= date_obj <= date_fin_obj):
                continue

        fiche_de_poste_list.append({
            "Titre": attributes.get("title", "Non renseigné"),
            "Référence": attributes.get("reference", "Non renseigné"),
            "Date de création": formatted_date,
            "Date de clôture": formatted_cloture_date,  # ✅ Ajout de la date de clôture
            "État": state_label,
            "Nombre de positionnements": nombre_positionnements,
            "Client": client_company_name,
            "Opérationnel Client": client_contact_name
        })


    return jsonify(fiche_de_poste_list)

@app.route("/view_fiches", methods=["GET"])
def view_fiches():
    """Affiche toutes les fiches de poste dans une page HTML."""
    response = get_fiches()
    data = response.json if hasattr(response, "json") else response

    if isinstance(data, dict) and "message" in data:
        return render_template("fiches.html", fiches=[])

    return render_template("fiches.html", fiches=data)

@app.route("/update_fiches", methods=["GET"])
def update_fiches():
    """Met à jour les fiches de poste en récupérant les nouvelles données depuis l'API BoondManager."""
    try:
        response = requests.get("http://127.0.0.1:5000/get_fiches")
        if response.status_code != 200:
            return jsonify({"success": False, "error": "Erreur API BoondManager"}), 500

        data = response.json()
        df = pd.DataFrame(data)

        # 📂 Sauvegarde des nouvelles fiches dans un fichier Excel
        file_path = "fiches_de_poste.xlsx"
        df.to_excel(file_path, index=False, engine="openpyxl")

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/")
def home():
    """Affiche la page d'accueil."""
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
