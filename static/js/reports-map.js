(function () {
    const mapElement = document.getElementById("reports-map");
    if (!mapElement || typeof L === "undefined") {
        return;
    }

    const endpointUrl = window.reportsMapConfig && window.reportsMapConfig.endpointUrl;
    if (!endpointUrl) {
        return;
    }

    const filterCategory = document.getElementById("filter-category");
    const filterStatus = document.getElementById("filter-status");
    const filterMunicipality = document.getElementById("filter-municipality");

    const map = L.map(mapElement).setView([41.9981, 21.4254], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(map);

    const markersLayer = L.layerGroup().addTo(map);

    function markerClassByStatus(status) {
        if (status === "new") {
            return "pin-new";
        }
        if (status === "in_progress") {
            return "pin-in-progress";
        }
        if (status === "resolved") {
            return "pin-resolved";
        }
        return "pin-unclassified";
    }

    function statusBadgeClass(status) {
        if (status === "new") {
            return "badge bg-primary";
        }
        if (status === "in_progress") {
            return "badge text-dark bg-warning";
        }
        if (status === "resolved") {
            return "badge bg-success";
        }
        return "badge bg-secondary";
    }

    function createMarker(report) {
        const cssClass = markerClassByStatus(report.status);
        const icon = L.divIcon({
            className: "map-pin " + cssClass,
            iconSize: [18, 18],
            iconAnchor: [9, 9],
            popupAnchor: [0, -8],
        });

        const marker = L.marker([report.lat, report.lng], { icon: icon });

        const safeDescription = (report.description || "").replace(/[&<>\"']/g, function (char) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                "\"": "&quot;",
                "'": "&#39;",
            }[char];
        });

        const popupHtml =
            '<div class="map-popup">' +
                '<div class="fw-semibold mb-1">ID: ' + report.id + "</div>" +
                '<div class="small text-muted mb-2">' + safeDescription + "</div>" +
                '<span class="' + statusBadgeClass(report.status) + '">' + report.status_label + "</span>" +
            "</div>";

        marker.bindPopup(popupHtml);
        return marker;
    }

    function buildQueryString() {
        const params = new URLSearchParams();

        if (filterCategory && filterCategory.value) {
            params.set("category", filterCategory.value);
        }
        if (filterStatus && filterStatus.value) {
            params.set("status", filterStatus.value);
        }
        if (filterMunicipality && filterMunicipality.value) {
            params.set("municipality", filterMunicipality.value);
        }

        return params.toString();
    }

    async function loadReports() {
        const query = buildQueryString();
        const url = query ? endpointUrl + "?" + query : endpointUrl;

        const response = await fetch(url, {
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        if (!response.ok) {
            return;
        }

        const payload = await response.json();
        const results = payload.results || [];

        markersLayer.clearLayers();

        const bounds = [];
        results.forEach(function (report) {
            const marker = createMarker(report);
            marker.addTo(markersLayer);
            bounds.push([report.lat, report.lng]);
        });

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
        } else {
            map.setView([41.9981, 21.4254], 12);
        }
    }

    [filterCategory, filterStatus, filterMunicipality].forEach(function (element) {
        if (!element) {
            return;
        }
        element.addEventListener("change", loadReports);
    });

    loadReports();
})();
