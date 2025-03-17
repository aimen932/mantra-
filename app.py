from flask import Flask, jsonify, render_template, request
import time
import jwt as pyjwt
import requests
import pandas as pd
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app)

# 🔑 Authentification BoondManager
USER_TOKEN = "37332e6d616e747261"
CLIENT_TOKEN = "6d616e747261"
CLIENT_KEY = "06daebfc3aae9ef09791"

API_URL = "https://ui.boondmanager.com/api/opportunities"

ETAT_FICHE_DE_POSTE = {0: "Piste identifiée", 5: "En cours", 1: "Gagnée", 2: "Fermée"}

def format_date_closing(date_str):
    if date_str and date_str != "Non renseigné":
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return "Non renseigné"
    return "Non renseigné"

def format_date_created(date_str):
    if date_str and date_str != "Non renseigné":
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z").strftime("%d/%m/%Y")
        except Exception:
            return "Non renseigné"
    return "Non renseigné"

def get_jwt_token():
    jwt_token = pyjwt.encode({
        "userToken": USER_TOKEN,
        "clientToken": CLIENT_TOKEN,
        "time": int(time.time()),
        "mode": "normal"
    }, CLIENT_KEY, algorithm="HS256")

    return jwt_token if isinstance(jwt_token, str) else jwt_token.decode("utf-8")

HEADERS = {
    "X-Jwt-Client-BoondManager": get_jwt_token(),
    "Accept": "application/json"
}

@app.route("/get_fiches", methods=["GET"])
def get_fiches():
    filtres_etats = request.args.getlist("etat")
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

    fiche_de_poste_list = []

    for item in all_fiches:
        attributes = item.get("attributes", {})
        relationships = item.get("relationships", {})

        company_data = relationships.get("company", {}).get("data")
        company_id = company_data.get("id") if isinstance(company_data, dict) else None
        client_company_name = companies_mapping.get(company_id, "Non attribué")

        contact_data = relationships.get("contact", {}).get("data", {})
        contact_id = contact_data.get("id") if isinstance(contact_data, dict) else None
        client_contact_name = contacts_mapping.get(contact_id, "Non attribué")

        state_code = attributes.get("state", -1)
        state_label = ETAT_FICHE_DE_POSTE.get(state_code, f"État inconnu ({state_code})")
        nombre_positionnements = attributes.get("numberOfActivePositionings", 0)

        # ✅ Utilisation correcte de 'answerDate'
        date_cloture_raw = attributes.get("closingDate")
        formatted_cloture_date = format_date_closing(date_cloture_raw)

        fiche_date = attributes.get("creationDate")
        formatted_date = format_date_created(fiche_date)

        if filtres_etats and state_label not in filtres_etats:
            continue

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
            "Date de clôture": formatted_cloture_date,
            "État": state_label,
            "Nombre de positionnements": nombre_positionnements,
            "Client": client_company_name,
            "Opérationnel Client": client_contact_name
        })

    return jsonify(fiche_de_poste_list)

@app.route("/view_fiches", methods=["GET"])
def view_fiches():
    response = get_fiches()
    data = response.json if hasattr(response, "json") else response
    return render_template("fiches.html", fiches=[] if isinstance(data, dict) else data)

@app.route("/update_fiches", methods=["GET"])
def update_fiches():
    try:
        response = get_fiches()
        fiches_data = response.get_json()

        if isinstance(fiches_data, dict) and fiches_data.get("error"):
            return jsonify({"success": False, "error": fiches_data["error"]}), 500
        
        df = pd.DataFrame(fiches_data)
        file_path = "fiches_de_poste.xlsx"
        df.to_excel(file_path, index=False, engine="openpyxl")

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/")
def home():
    return render_template("index.html")

# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
