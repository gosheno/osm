<template>
  <section class="route-map">
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
  routeGeometry: {
    type: Object,
    default: null,
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
  return coordinateValue(point?.latitude) !== null && coordinateValue(point?.longitude) !== null;
}

function pointNumber(point, index) {
  const order = Number(point?.order);
  return Number.isFinite(order) ? order + 1 : index + 1;
}

function pointLabel(point, index) {
  if (point?.type === 'start') {
    return 'S';
  }

  if (point?.type === 'end') {
    return 'F';
  }

  return String(pointNumber(point, index));
}

function createNumberedIcon(point, index) {
  return L.divIcon({
    className: `route-marker route-marker--${point?.type || 'waypoint'}`,
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

function geometryToLatLngs(geometry) {
  if (!geometry || geometry.type !== 'LineString' || !Array.isArray(geometry.coordinates)) {
    return [];
  }

  return geometry.coordinates
    .map((coordinate) => {
      if (!Array.isArray(coordinate) || coordinate.length < 2) {
        return null;
      }

      // GeoJSON/OSRM: [longitude, latitude]. Leaflet: [latitude, longitude].
      const longitude = coordinateValue(coordinate[0]);
      const latitude = coordinateValue(coordinate[1]);

      if (latitude === null || longitude === null) {
        return null;
      }

      return [latitude, longitude];
    })
    .filter(Boolean);
}

function createPopupContent(point, index) {
  const container = document.createElement('div');
  const lines = [
    `Точка ${pointNumber(point, index)}`,
    `Тип: ${point?.type || '-'}`,
    point?.district ? `Район: ${point.district}` : null,
    point?.batch_number != null ? `Пакет: ${point.batch_number}` : null,
    formatAddressLabel(point),
    formatPointCoordinates(point),
    point?.confidence_score != null ? `Точность: ${Math.round(Number(point.confidence_score))}` : null,
  ].filter(Boolean);

  lines.forEach((line) => {
    const item = document.createElement('div');
    item.textContent = line;
    container.appendChild(item);
  });

  return container;
}

function clearMapLayers() {
  markers.forEach((marker) => marker.remove());
  markers = [];

  if (routeLine) {
    routeLine.remove();
    routeLine = null;
  }
}

function updateMap() {
  if (!map) {
    return;
  }

  clearMapLayers();

  const points = (props.orderedPoints || []).filter(isValidPoint);
  const pointLatLngs = points.map((point) => [
    coordinateValue(point.latitude),
    coordinateValue(point.longitude),
  ]);

  if (!points.length) {
    map.setView(DEFAULT_MAP_CENTER, 11);
    setTimeout(() => map?.invalidateSize(), 0);
    return;
  }

  points.forEach((point, index) => {
    const marker = L.marker(pointLatLngs[index], {
      icon: createNumberedIcon(point, index),
    }).addTo(map);

    marker.bindPopup(createPopupContent(point, index));
    markers.push(marker);
  });

  const routeLatLngs = geometryToLatLngs(props.routeGeometry);

  if (routeLatLngs.length > 1) {
    routeLine = L.polyline(routeLatLngs, {
      weight: 5,
      opacity: 0.9,
    }).addTo(map);

    const bounds = L.latLngBounds([...routeLatLngs, ...pointLatLngs]);
    map.fitBounds(bounds, { padding: [40, 40] });
  } else if (pointLatLngs.length > 1) {
    // Fallback: если backend не вернул дорожную геометрию OSRM,
    // показываем пунктирную прямую линию только как индикатор порядка точек.
    routeLine = L.polyline(pointLatLngs, {
      weight: 3,
      opacity: 0.75,
      dashArray: '8 8',
    }).addTo(map);

    const bounds = L.latLngBounds(pointLatLngs);
    map.fitBounds(bounds, { padding: [40, 40] });
  } else {
    map.setView(pointLatLngs[0], 13);
  }

  setTimeout(() => map?.invalidateSize(), 0);
}

function createMap() {
  if (!mapContainer.value) {
    return;
  }

  map = L.map(mapContainer.value, {
    center: DEFAULT_MAP_CENTER,
    zoom: 11,
    scrollWheelZoom: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  setTimeout(() => {
    map?.invalidateSize();
  }, 0);
}

onMounted(() => {
  createMap();
  updateMap();
});

onUnmounted(() => {
  clearMapLayers();

  if (map) {
    map.remove();
    map = null;
  }
});

watch(
  () => [props.orderedPoints, props.routeGeometry],
  () => {
    updateMap();
  },
  { deep: true }
);
</script>

<style scoped>
.route-map {
  width: 100%;
  height: 100%;
  margin: 0;
}

.map-container {
  width: 100%;
  height: 100%;
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
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.25);
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
