let map;
let markers = [];
let allStations = [];

const greenIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

const redIcon = L.icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadStations();
    setupFilters();
});

function initMap() {
    map = L.map('map', { attributionControl: false }).setView([55.7558, 37.6173], 11);

    L.tileLayer(
        'https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png',
        { attribution: '© CartoDB' }
    ).addTo(map);

    L.control.attribution({ prefix: 'Leaflet' }).addTo(map);
}

async function loadStations() {
    try {
        const response = await fetch('/api/stations');
        allStations = await response.json();
        displayStations(allStations);
        populateAdmareaFilter();
    } catch (error) {
        console.error(error);
    }
}

function displayStations(stations) {
    markers.forEach(marker => map.removeLayer(marker));
    markers = [];

    stations.forEach(station => {
        if (!station.latitude || !station.longitude) return;

        const icon = station.eco_status ? greenIcon : redIcon;

        const marker = L.marker([station.latitude, station.longitude], { icon }).addTo(map);

        const popup = `
            <div class="marker-popup">
                <h3>${station.name}</h3>
                <p class="status ${station.eco_status ? 'eco' : 'non-eco'}">
                    ${station.eco_status ? '✓ Экологичная' : '✗ Неэкологичная'}
                </p>
                <p><strong>Адрес:</strong> ${station.address}</p>
                <p><strong>Владелец:</strong> ${station.owner || 'Не указано'}</p>
                <p><strong>Округ:</strong> ${station.admarea}</p>
                ${station.test_date ? `<p><strong>Проверка:</strong> ${new Date(station.test_date).toLocaleDateString('ru-RU')}</p>` : ""}
                <p><strong>Рейтинг:</strong> ${station.average_rating} ⭐</p>
                <a href="/station/${station.id}" class="btn btn-primary" style="margin-top: 0.7rem;">Подробнее</a>
            </div>
        `;

        marker.bindPopup(popup);
        markers.push(marker);
    });

    document.getElementById('results-count').textContent = stations.length;
}

function populateAdmareaFilter() {
    const admareas = [...new Set(allStations.map(s => s.admarea))].filter(Boolean).sort();
    const select = document.getElementById('admarea-filter');

    admareas.forEach(area => {
        const opt = document.createElement('option');
        opt.value = area;
        opt.textContent = area;
        select.appendChild(opt);
    });
}

function setupFilters() {
    const search = document.getElementById('search-input');
    const filterAll = document.getElementById('filter-all');
    const filterEco = document.getElementById('filter-eco');
    const filterNonEco = document.getElementById('filter-non-eco');
    const admareaSelect = document.getElementById('admarea-filter');

    search.addEventListener('input', applyFilters);
    filterAll.addEventListener('change', handleFilterAll);
    filterEco.addEventListener('change', applyFilters);
    filterNonEco.addEventListener('change', applyFilters);
    admareaSelect.addEventListener('change', applyFilters);
}

function handleFilterAll() {
    const all = document.getElementById('filter-all');
    const eco = document.getElementById('filter-eco');
    const nonEco = document.getElementById('filter-non-eco');

    if (all.checked) {
        eco.checked = true;
        nonEco.checked = true;
    }

    applyFilters();
}

function applyFilters() {
    const query = document.getElementById('search-input').value.toLowerCase();
    const showEco = document.getElementById('filter-eco').checked;
    const showNonEco = document.getElementById('filter-non-eco').checked;
    const adm = document.getElementById('admarea-filter').value;

    const filtered = allStations.filter(station => {
        const matchesSearch =
            !query ||
            station.name.toLowerCase().includes(query) ||
            station.address.toLowerCase().includes(query) ||
            (station.owner && station.owner.toLowerCase().includes(query));

        const matchesEco =
            (station.eco_status && showEco) ||
            (!station.eco_status && showNonEco);

        const matchesAdm = !adm || station.admarea === adm;

        return matchesSearch && matchesEco && matchesAdm;
    });

    displayStations(filtered);
}
