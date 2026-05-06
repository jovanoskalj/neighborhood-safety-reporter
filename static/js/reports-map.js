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
    const heatmapToggle = document.getElementById("heatmap-toggle");

    const map = L.map(mapElement).setView([41.9981, 21.4254], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(map);

    const markersLayer = L.layerGroup().addTo(map);
    let heatmapLayer = null;

    const heatmapUrl = window.reportsMapConfig && window.reportsMapConfig.heatmapUrl;

    async function toggleHeatmap() {
        if (!heatmapToggle || !heatmapUrl) return;

        if (heatmapToggle.checked) {
            if (!heatmapLayer) {
                try {
                    const response = await fetch(heatmapUrl);
                    if (!response.ok) throw new Error("Failed to fetch heatmap data");
                    
                    const data = await response.json();
                    heatmapLayer = L.heatLayer(data, {
                        radius: 20,
                        blur: 15,
                        maxZoom: 17,
                        max: 1.0,
                    });
                } catch (error) {
                    console.error("Error loading heatmap:", error);
                    heatmapToggle.checked = false;
                    return;
                }
            }
            heatmapLayer.addTo(map);
        } else {
            if (heatmapLayer) {
                map.removeLayer(heatmapLayer);
            }
        }
    }

    if (heatmapToggle) {
        heatmapToggle.addEventListener("change", toggleHeatmap);
    }

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

        // Add bounding box parameters from visible map area
        const bounds = map.getBounds();
        params.set("minLat", bounds.getSouth().toFixed(6));
        params.set("maxLat", bounds.getNorth().toFixed(6));
        params.set("minLng", bounds.getWest().toFixed(6));
        params.set("maxLng", bounds.getEast().toFixed(6));

        return params.toString();
    }

    async function loadReports() {
        const query = buildQueryString();
        const url = query ? endpointUrl + "?" + query : endpointUrl;

        try {
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

            results.forEach(function (report) {
                const marker = createMarker(report);
                marker.addTo(markersLayer);
            });
        } catch (error) {
            console.error("Error loading reports:", error);
        }
    }

    // Load reports on filter changes
    [filterCategory, filterStatus, filterMunicipality].forEach(function (element) {
        if (!element) {
            return;
        }
        element.addEventListener("change", loadReports);
    });

    // Load reports on map move events (pan and zoom)
    // Debounce the load to prevent too many requests during rapid panning/zooming
    let loadReportsTimeout;
    function debouncedLoadReports() {
        clearTimeout(loadReportsTimeout);
        loadReportsTimeout = setTimeout(loadReports, 300);
    }

    map.on("moveend", debouncedLoadReports);
    map.on("zoomend", debouncedLoadReports);

    // Initial load
    loadReports();
})();
