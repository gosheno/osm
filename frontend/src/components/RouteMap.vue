<template>
  <section class="route-map">
    <h2>Карта порядка посещения точек</h2>
    <p class="map-note">Ломаная линия показывает порядок точек, а не точный дорожный маршрут.</p>
    <div ref="mapContainer" class="map-container"></div>
  </section>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import { formatAddressLabel, formatCoordinate } from '../utils/formatters';
import { DEFAULT_MAP_CENTER } from '../utils/mapUtils';

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const props = defineProps({
  orderedPoints: {
    type: Array,
    required: true,
  },
});

const mapContainer = ref(null);
let map = null;
let markers = [];
let routeLine = null;

function coordinateValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function isValidPoint(point) {
  return coordinateValue(point.latitude) !== null && coordinateValue(point.longitude) !== null;
}

function pointNumber(point, index) {
  const order = Number(point.order);
  return Number.isFinite(order) ? order + 1 : index + 1;
}

function pointLabel(point, index) {
  if (point.type === 'start') {
    return 'S';
  }
  if (point.type === 'end') {
    return 'F';
  }
  return String(pointNumber(point, index));
}

function createNumberedIcon(point, index) {
  return L.divIcon({
    className: `route-marker route-marker--${point.type || 'waypoint'}`,
    html: `<span>${pointLabel(point, index)}</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 34],
    popupAnchor: [0, -38],
  });
}

function formatPointCoordinates(point) {
  if (!isValidPoint(point)) {
    return '-';
  }
  return `${formatCoordinate(point.latitude)}, ${formatCoordinate(point.longitude)}`;
}

function createPopupContent(point, index) {
  const container = document.createElement('div');
  const lines = [
    `Точка ${pointNumber(point, index)}`,
    `Тип: ${point.type || '-'}`,
    point.district ? `Район: ${point.district}` : null,
    point.batch_number != null ? `Пакет: ${point.batch_number}` : null,
    formatAddressLabel(point),
    formatPointCoordinates(point),
  ].filter(Boolean);

  lines.forEach((line) => {
    const item = document.createElement('div');
    item.textContent = line;
    container.appendChild(item);
  });

  return container;
}

function updateMap() {
  if (!map) {
    return;
  }

  markers.forEach((marker) => map.removeLayer(marker));
  markers = [];
  if (routeLine) {
    map.removeLayer(routeLine);
    routeLine = null;
  }

  const points = (props.orderedPoints || []).filter(isValidPoint);
  if (!points.length) {
    map.setView(DEFAULT_MAP_CENTER, 11);
    return;
  }

  const latLngs = points.map((point) => [
    coordinateValue(point.latitude),
    coordinateValue(point.longitude),
  ]);

  points.forEach((point, index) => {
    const latLng = latLngs[index];
    const marker = L.marker(latLng, {
      icon: createNumberedIcon(point, index),
    }).addTo(map);

    marker.bindPopup(createPopupContent(point, index));
    markers.push(marker);
  });

  if (latLngs.length > 1) {
    routeLine = L.polyline(latLngs, { color: '#2563eb', weight: 4 }).addTo(map);
    const bounds = L.latLngBounds(latLngs);
    map.fitBounds(bounds, { padding: [40, 40] });
  } else {
    map.setView(latLngs[0], 13);
  }
}

function createMap() {
  map = L.map(mapContainer.value, {
    center: DEFAULT_MAP_CENTER,
    zoom: 11,
    scrollWheelZoom: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);
}

onMounted(() => {
  createMap();
  updateMap();
});

onUnmounted(() => {
  if (map) {
    map.remove();
    map = null;
  }
});

watch(
  () => props.orderedPoints,
  () => {
    updateMap();
  },
  { deep: true }
);
</script>

<style scoped>
.route-map {
  margin-bottom: 24px;
}

.map-note {
  margin: 0 0 12px;
  color: #475569;
  font-size: 0.95rem;
}

.map-container {
  height: 460px;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid #cbd5e1;
}

</style>

<style>
.route-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 2px solid #ffffff;
  color: #ffffff;
  font-size: 14px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

.route-marker--start {
  background: #16a34a;
}

.route-marker--end {
  background: #dc2626;
}

.route-marker--waypoint {
  background: #2563eb;
}
</style>
