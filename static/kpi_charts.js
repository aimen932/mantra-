document.addEventListener("DOMContentLoaded", function () {
    fetch("/kpi_data")
        .then(response => response.json())
        .then(data => {
            // ✅ 1. Répartition des fiches de poste (Gagnée, Fermée, Piste identifiée, En cours)
            const etatLabels = Object.keys(data.etat_counts);
            const etatValues = Object.values(data.etat_counts);
            const etatColors = {
                "Gagnée": "#4CAF50",         // ✅ Vert
                "En cours": "#0000FF",       // ✅ Bleu
                "Fermée": "#F44336",         // ✅ Rouge
                "Piste identifiée": "#FF9800" // ✅ Orange
            };

            const etatCtx = document.getElementById("etatChart").getContext("2d");
            new Chart(etatCtx, {
                type: "bar",
                data: {
                    labels: etatLabels,
                    datasets: [{
                        label: "Nombre de Fiches",
                        data: etatValues,
                        backgroundColor: etatLabels.map(etat => etatColors[etat] || "#000000"),
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });

            // ✅ 2. Évolution des fiches de poste créées par mois avec code couleur selon état
            const evolutionLabels = Object.keys(data.evolution_fiches);
            const etats = Object.keys(data.evolution_fiches[evolutionLabels[0]] || {});

            const datasets = etats.map((etat) => ({
                label: etat,
                data: evolutionLabels.map(month => data.evolution_fiches[month][etat] || 0),
                borderColor: etatColors[etat] || "#000000",
                backgroundColor: etatColors[etat] || "#000000",
                fill: false
            }));

            const evolutionCtx = document.getElementById("evolutionChart").getContext("2d");
            new Chart(evolutionCtx, {
                type: "line",
                data: {
                    labels: evolutionLabels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });

        })
        .catch(error => console.error("Erreur lors du chargement des données KPI :", error));
});
