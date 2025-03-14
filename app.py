from flask import Flask, jsonify, render_template, request
import time
import jwt as pyjwt
import requests
import pandas as pd
import openpyxl
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

def format_date(date_str):
    if date_str and date_str != "Non renseigné":
        try:
            return time.strftime("%d/%m/%Y", time.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z"))
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

    fiche_de_poste_list, page, limit = [], 1, 100
    contacts_mapping, companies_mapping = {}, {}

    while True:
        params = {"page": page, "limit": limit, "filters[state]": "0,1,2,5"}
        response = requests.get(API_URL, headers=HEADERS, params=params)
        if response.status_code != 200:
            break

        data = response.json()
        fiches, included = data.get("data", []), data.get("included", [])

        for item in included:
            if item["type"] == "contact":
                contacts_mapping[item["id"]] = item["attributes"].get("firstName", "") + " " + item["attributes"].get("lastName", "")
            elif item["type"] == "company":
                companies_mapping[item["id"]] = item["attributes"].get("name", "")

        for fiche in fiches:
            attributes, relationships = fiche["attributes"], fiche.get("relationships", {})

            state_label = ETAT_FICHE_DE_POSTE.get(attributes.get("state"), "État inconnu")
            creation_date = format_date(attributes.get("creationDate"))
            closure_date = format_date(attributes.get("closingDate"))  # ✅ Date de clôture

            if request.args.getlist("etat") and state_label not in request.args.getlist("etat"):
                continue

            if date_debut and date_fin and creation_date != "Non renseigné":
                date_obj = datetime.strptime(creation_date, "%d/%m/%Y")
                if not (datetime.strptime(date_debut, "%d/%m/%Y") <= date_obj <= datetime.strptime(date_fin, "%d/%m/%Y")):
                    continue

            fiche_de_poste_list.append({
                "Titre": attributes.get("title", "Non renseigné"),
                "Référence": attributes.get("reference", "Non renseigné"),
                "Date de création": creation_date,
                "Date de clôture": closure_date,
                "État": state_label,
                "Nombre de positionnements": attributes.get("numberOfActivePositionings", 0),
                "Client": companies_mapping.get(relationships.get("company", {}).get("data", {}).get("id"), "Non attribué"),
                "Opérationnel Client": contacts_mapping.get(relationships.get("contact", {}).get("data", {}).get("id"), "Non attribué")
            })

        if len(fiche_de_poste_list) >= data["meta"]["totals"]["rows"]:
            break
        page += 1

    return jsonify(fiche_de_poste_list)

@app.route("/view_fiches", methods=["GET"])
def view_fiches():
    response = get_fiches()
    data = response.json if hasattr(response, "json") else response
    return render_template("fiches.html", fiches=[] if isinstance(data, dict) else data)

@app.route("/update_fiches", methods=["GET"])
def update_fiches():
    try:
        response = requests.get("http://127.0.0.1:5000/get_fiches")
        if response.status_code != 200:
            return jsonify({"success": False}), 500

        pd.DataFrame(response.json()).to_excel("fiches_de_poste.xlsx", index=False, engine="openpyxl")
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
