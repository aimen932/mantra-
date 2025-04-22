from flask import Flask, jsonify, render_template, request
import time
import jwt as pyjwt
import requests
import pandas as pd
from datetime import datetime
from flask_cors import CORS
import threading
import os
import pickle
import matplotlib.pyplot as plt

app = Flask(__name__, template_folder="templates")
CORS(app)

# 🔑 Authentification BoondManager
USER_TOKEN = "37332e6d616e747261"
CLIENT_TOKEN = "6d616e747261"
CLIENT_KEY = "06daebfc3aae9ef09791"

API_URL = "https://ui.boondmanager.com/api/opportunities"

ETAT_FICHE_DE_POSTE = {0: "Piste identifiée", 5: "En cours", 1: "Gagnée", 2: "Fermée", 4: "Cv envoyé"}

_fiches_cache = {"data": None, "timestamp": 0}
_cache_lock = threading.Lock()
CACHE_DURATION = 180  # secondes (3 minutes)
CACHE_FILE = "fiches_cache.pkl"

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

def get_fiches_cached():
    now = time.time()
    # Vérifie le cache disque
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
            if now - cache["timestamp"] < CACHE_DURATION:
                return cache["data"]
    # Sinon, recharge depuis l'API
    data = fetch_all_fiches()
    with open(CACHE_FILE, "wb") as f:
        pickle.dump({"data": data, "timestamp": now}, f)
    return data

def warmup_cache():
    with app.app_context():
        get_fiches_cached()

def fetch_all_fiches(filtres_etats=None, date_debut=None, date_fin=None):
    page = 1
    limit = 1000
    all_fiches = []
    contacts_mapping = {}
    companies_mapping = {}

    # Calcul de la date de début (1er janvier de l'année la plus ancienne à garder)
    current_year = datetime.now().year
    min_year = current_year - 2
    min_date = datetime(min_year, 1, 1).strftime("%Y-%m-%d")

    while True:
        params = {
            "page": page,
            "limit": limit,
            "filters[state]": "0,1,2,5,4",
            "filters[creationDate][min]": min_date,
            "fields[opportunities]": "title,reference,creationDate,closingDate,state,numberOfActivePositionings,company,contact"
        }
        response = requests.get(API_URL, headers=HEADERS, params=params)
        if response.status_code != 200:
            return {"error": "Erreur API", "status": response.status_code}

        data = response.json()
        fiches = data.get("data", [])
        total_rows = data.get("meta", {}).get("totals", {}).get("rows", 0)

        # Arrêt anticipé si plus de fiches récentes
        for item in fiches:
            attributes = item.get("attributes", {})
            fiche_date = attributes.get("creationDate")
            if fiche_date:
                try:
                    fiche_date_obj = datetime.strptime(fiche_date[:10], "%Y-%m-%d")
                    if fiche_date_obj < datetime.strptime(min_date, "%Y-%m-%d"):
                        break
                except Exception:
                    pass

        all_fiches.extend(fiches)
        if len(all_fiches) >= total_rows:
            break
        page += 1

    fiche_de_poste_list = []

    for item in all_fiches:
        attributes = item.get("attributes", {})
        fiche_date = attributes.get("creationDate")
        if fiche_date:
            try:
                fiche_date_obj = datetime.strptime(fiche_date[:10], "%Y-%m-%d")
                if fiche_date_obj < datetime.strptime(min_date, "%Y-%m-%d"):
                    break  # On arrête la récupération, les fiches suivantes sont trop anciennes
            except Exception:
                pass

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

    return fiche_de_poste_list

@app.route("/get_fiches", methods=["GET"])
def get_fiches():
    filtres_etats = request.args.getlist("etat")
    date_debut = request.args.get("date_debut", "").strip()
    date_fin = request.args.get("date_fin", "").strip()
    data = fetch_all_fiches(filtres_etats, date_debut, date_fin)
    if isinstance(data, dict) and data.get("error"):
        return jsonify(data), 500
    return jsonify(data)

@app.route("/view_fiches", methods=["GET"])
def view_fiches():
    fiches = get_fiches_cached()
    return render_template("fiches.html", fiches=fiches)

@app.route("/update_fiches", methods=["GET"])
def update_fiches():
    try:
        # Force la récupération des données fraîches depuis l'API
        data = fetch_all_fiches()
        # Mets à jour le cache disque
        now = time.time()
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"data": data, "timestamp": now}, f)
        # Génère le fichier Excel si besoin
        df = pd.DataFrame(data)
        file_path = "fiches_de_poste.xlsx"
        df.to_excel(file_path, index=False, engine="openpyxl")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/kpi")
def kpi():
    fiches = get_fiches_cached()
    return render_template("kpi.html", fiches=fiches)

@app.route("/kpi/annuel")
def kpi_annuel():
    fiches = get_fiches_cached()
    # ...reste du code inchangé...
    current_year = datetime.now().year
    years = [current_year - i for i in range(2, -1, -1)]
    mois_labels = [
        "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
        "Juil", "Août", "Sep", "Oct", "Nov", "Déc"
    ]

    fiches_par_annee = {year: [0]*12 for year in years}
    fiches_gagnees_par_annee = {year: [0]*12 for year in years}

    for fiche in fiches:
        date_creation = fiche.get("Date de création")
        etat = fiche.get("État")
        if date_creation and date_creation != "Non renseigné":
            try:
                date_obj = datetime.strptime(date_creation, "%d/%m/%Y")
                if date_obj.year in years:
                    mois = date_obj.month - 1
                    fiches_par_annee[date_obj.year][mois] += 1
                    if etat == "Gagnée":
                        fiches_gagnees_par_annee[date_obj.year][mois] += 1
            except Exception:
                continue

    return render_template(
        "kpi_annuel.html",
        mois_labels=mois_labels,
        years=years,
        fiches_par_annee=fiches_par_annee,
        fiches_gagnees_par_annee=fiches_gagnees_par_annee
    )

# @app.route("/kpi/evolution_consultants")
# def kpi_evolution_consultants():
#     fichiers = [
#         "Suivi Canal 2021.xlsx",
#         "Suivi Canal 2022.xlsx",
#         "Suivi Canal 2023.xlsx",
#         "Suivi Canal 2024.xlsx",
#         "Suivi Canal 2025.xlsx"
#     ]
#     plot_evolution_consultants(fichiers)
#     return render_template("kpi_evolution.html")

def background_cache_refresh():
    while True:
        with app.app_context():
            get_fiches_cached()
        time.sleep(CACHE_DURATION)

# def nettoyer_fichier_suivi_canal(fichier_path):
#     df = pd.read_excel(fichier_path, header=1)
#     df.columns = df.columns.str.replace('\n', ' ', regex=True).str.replace(' +', ' ', regex=True).str.strip()
#     df = df.loc[:, ~df.columns.duplicated()]

#     premiere_ligne = df.iloc[0].astype(str).str.cat(sep='').replace(' ', '')
#     if 'TJMFacturé' in premiere_ligne or 'TJMPayé' in premiere_ligne or 'TJMConsultantpayé' in premiere_ligne or 'TJMClientfacturé' in premiere_ligne:
#         df = df.iloc[1:].reset_index(drop=True)

#     colonnes_map = {
#         'tjm_payé': None,
#         'tjm_facturé': None,
#         'marge': None,
#         'pourcentage': None
#     }

#     for col in df.columns:
#         col_lower = col.lower()
#         if 'tjm' in col_lower and 'payé' in col_lower:
#             colonnes_map['tjm_payé'] = col
#         elif 'tjm' in col_lower and 'facturé' in col_lower:
#             colonnes_map['tjm_facturé'] = col
#         elif 'marge' in col_lower:
#             colonnes_map['marge'] = col
#         elif '%' in col or 'pourcent' in col_lower:
#             colonnes_map['pourcentage'] = col

#     for key, col in colonnes_map.items():
#         if col:
#             df[col] = df[col].replace({'€': '', ',': '.', '\s': ''}, regex=True)
#             df[col] = pd.to_numeric(df[col], errors='coerce')

#     colonnes_critiques = [col for col in colonnes_map.values() if col]
#     df = df.dropna(subset=colonnes_critiques)

#     return df

# def evolution_consultants(df, annee):
#     nom_consultant = next((col for col in df.columns if 'consultant' in col.lower()), None)
#     date_entree = next((col for col in df.columns if "entrée" in col.lower()), None)
#     date_fin = next((col for col in df.columns if "fin" in col.lower()), None)

#     df[date_entree] = pd.to_datetime(df[date_entree], errors='coerce', dayfirst=True)
#     df[date_fin] = pd.to_datetime(df[date_fin], errors='coerce', dayfirst=True)

#     mois = pd.date_range(start=f"{annee}-01-01", end=f"{annee}-12-31", freq='MS')
#     evolution = []

#     for m in mois:
#         present = df[
#             (
#                 (df[date_entree].isna()) | (df[date_entree] <= m + pd.offsets.MonthEnd(1))
#             ) & (
#                 (df[date_fin].isna()) | (df[date_fin] >= m)
#             )
#         ][nom_consultant].nunique()
#         evolution.append(present)

#     return mois, evolution

# def plot_evolution_consultants(fichiers, output_path="static/evolution_consultants.png"):
#     plt.style.use('seaborn-v0_8-darkgrid')
#     plt.figure(figsize=(14, 7))
#     couleurs = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
#     for idx, fichier in enumerate(fichiers):
#         if os.path.exists(fichier):
#             df_nettoye = nettoyer_fichier_suivi_canal(fichier)
#             annee = fichier.split()[-1].split('.')[0]
#             mois, evolution = evolution_consultants(df_nettoye, annee)
#             plt.plot(mois, evolution, marker='o', label=f"Année {annee}", color=couleurs[idx % len(couleurs)], linewidth=2)
#     plt.title("Évolution mensuelle du nombre de consultants", fontsize=18, fontweight='bold')
#     plt.xlabel("Mois", fontsize=14)
#     plt.ylabel("Nombre de consultants", fontsize=14)
#     plt.xticks(rotation=45)
#     plt.legend(title="Année", fontsize=12)
#     plt.grid(True, linestyle='--', alpha=0.6)
#     plt.tight_layout()
#     plt.savefig(output_path)
#     plt.close()

if __name__ == "__main__":
    import threading
    threading.Thread(target=background_cache_refresh, daemon=True).start()
    app.run(debug=True, port=5001)
