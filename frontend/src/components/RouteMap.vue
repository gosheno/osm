<template>
  <section class="route-map">
    <h2>Карта маршрута</h2>
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
import { DEFAULT_MAP_CENTER, orderedPointsToLatLngs } from '../utils/mapUtils';

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

  const points = props.orderedPoints || [];
  const latLngs = orderedPointsToLatLngs(points);

  if (!points.length) {
    map.setView(DEFAULT_MAP_CENTER, 11);
    return;
  }

  points.forEach((point, index) => {
    const marker = L.marker([point.latitude, point.longitude]).addTo(map);
    marker.bindPopup(`Точка ${point.order + 1}<br>Тип: ${point.type}<br>${point.address?.original_address || point.label || '-'}<br>${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)}`);
    markers.push(marker);
  });

  routeLine = L.polyline(latLngs, { color: '#2563eb', weight: 4 }).addTo(map);

  const bounds = L.latLngBounds(latLngs);
  map.fitBounds(bounds, { padding: [40, 40] });
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

.map-container {
  height: 460px;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid #cbd5e1;
}
</style>
