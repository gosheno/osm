<template>
  <form class="route-form" @submit.prevent="handleSubmit">
    <fieldset :disabled="loading">
      <legend>Создать маршрут</legend>

      <div class="test-sets" aria-label="Тестовые наборы адресов">
        <div class="test-sets__header">
          <span>Тестовые наборы</span>
          <button type="button" class="test-sets__random" @click="applyRandomTestSet">
            Случайный набор
          </button>
        </div>
        <div class="test-sets__buttons">
          <button
            v-for="set in TEST_ADDRESS_SETS"
            :key="set.id"
            type="button"
            @click="applyTestSet(set)"
          >
            {{ set.label }} · {{ set.addresses.length }}
          </button>
        </div>
        <p v-if="testSetMessage" class="test-sets__message">{{ testSetMessage }}</p>
      </div>

      <div class="search-area">
        <span class="search-area__label">Область поиска адресов</span>
        <div class="search-area__options">
          <label
            v-for="option in GEOCODING_AREA_OPTIONS"
            :key="option.value"
            class="search-area__option"
          >
            <input
              v-model="form.search_area_mode"
              type="radio"
              name="search-area"
              :value="option.value"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
        <label v-if="form.search_area_mode === 'custom_area'" class="search-area__custom">
          Район или населенный пункт
          <input
            v-model.trim="form.geocoding_area"
            type="text"
            placeholder="Кудрово, Мурино, Всеволожск"
          />
        </label>
      </div>

      <AddressSearchInput
        v-model="form.start_address"
        label="Начальный адрес"
        placeholder="Санкт-Петербург, Невский проспект, 10"
        role="start"
        required
        :disabled="loading"
        :defaultCity="form.default_city"
        :defaultRegion="defaultRegion"
        @selected="handleAddressSelected('start', $event)"
        @cleared="handleAddressCleared('start')"
        @error="handleAddressSearchError"
      />

      <label v-if="startCandidate && isLowConfidence(startCandidate)" class="verification-check">
        <input v-model="startLowConfidenceAccepted" type="checkbox" />
        <span>Начальный адрес может быть неточным. Я проверил его на карте.</span>
      </label>

      <AddressSearchInput
        v-model="form.end_address"
        label="Конечный адрес"
        placeholder="Санкт-Петербург, Московский вокзал"
        role="end"
        required
        :disabled="loading"
        :defaultCity="form.default_city"
        :defaultRegion="defaultRegion"
        @selected="handleAddressSelected('end', $event)"
        @cleared="handleAddressCleared('end')"
        @error="handleAddressSearchError"
      />

      <label v-if="endCandidate && isLowConfidence(endCandidate)" class="verification-check">
        <input v-model="endLowConfidenceAccepted" type="checkbox" />
        <span>Конечный адрес может быть неточным. Я проверил его на карте.</span>
      </label>

      <div class="waypoints-panel">
        <div class="waypoints-panel__header">
          <span>Промежуточные адреса</span>
          <div class="waypoint-mode" role="group" aria-label="Режим промежуточных адресов">
            <label
              class="waypoint-mode__option"
              :class="{ 'waypoint-mode__option--active': waypointMode === 'list' }"
            >
              <input v-model="waypointMode" type="radio" value="list" />
              <span>Список</span>
            </label>
            <label
              class="waypoint-mode__option"
              :class="{ 'waypoint-mode__option--active': waypointMode === 'search' }"
            >
              <input v-model="waypointMode" type="radio" value="search" />
              <span>Поиск</span>
            </label>
          </div>
        </div>

        <label v-if="waypointMode === 'list'">
          <span class="visually-hidden">Промежуточные адреса списком</span>
          <textarea v-model="form.addresses_text" rows="8" placeholder="Санкт-Петербург, Набережная Кутузова 12&#10;Кудрово, Ленинградская улица 7"></textarea>
        </label>

        <div v-else class="waypoint-search-mode">
          <div class="waypoint-search-mode__actions">
            <button
              type="button"
              class="secondary-button"
              @click="showWaypointSearch = true"
            >
              Добавить промежуточный адрес
            </button>
            <label class="online-toggle">
              <input
                v-model="onlineOptimization"
                type="checkbox"
                @change="handleOnlineOptimizationChange"
              />
              <span>Онлайн-оптимизация</span>
            </label>
            <button
              type="button"
              class="secondary-button"
              :disabled="!canOptimizeWaypoints"
              @click="optimizeWaypointOrder"
            >
              Оптимизировать порядок
            </button>
          </div>

          <AddressSearchInput
            v-if="showWaypointSearch"
            :key="waypointInputKey"
            v-model="waypointSearchQuery"
            label="Новый промежуточный адрес"
            placeholder="Санкт-Петербург, Набережная Кутузова 12"
            role="waypoint-add"
            :disabled="loading"
            :defaultCity="form.default_city"
            :defaultRegion="defaultRegion"
            @selected="handleWaypointSelected"
            @cleared="clearWaypointSearch"
            @error="handleAddressSearchError"
          />

          <ol v-if="waypointCandidates.length" class="selected-waypoints">
            <li
              v-for="(waypoint, index) in waypointCandidates"
              :key="waypoint.client_id"
              class="selected-waypoints__item"
            >
              <div class="selected-waypoints__content">
                <span class="selected-waypoints__index">{{ index + 1 }}</span>
                <div class="selected-waypoints__text">
                  <span class="selected-waypoints__name">{{ waypoint.display_name }}</span>
                  <span class="selected-waypoints__meta">
                    Точность: {{ Math.round(Number(waypoint.confidence_score ?? 100)) }}
                  </span>
                </div>
              </div>

              <label v-if="isLowConfidence(waypoint)" class="waypoint-verification">
                <input v-model="waypoint.verified" type="checkbox" />
                <span>Проверено на карте</span>
              </label>

              <div class="selected-waypoints__actions">
                <button
                  type="button"
                  :disabled="index === 0"
                  @click="moveWaypoint(index, -1)"
                >
                  Вверх
                </button>
                <button
                  type="button"
                  :disabled="index === waypointCandidates.length - 1"
                  @click="moveWaypoint(index, 1)"
                >
                  Вниз
                </button>
                <button type="button" @click="removeWaypoint(index)">
                  Удалить
                </button>
              </div>
            </li>
          </ol>
        </div>
      </div>

      <div class="row">
        <label>
          Размер пакета
          <input v-model.number="form.batch_size" type="number" min="1" max="20" />
        </label>

        <label>
          Метрика
          <select v-model="form.optimization_metric">
            <option value="duration">По времени</option>
            <option value="distance">По расстоянию</option>
          </select>
        </label>
      </div>

      <div class="row">
        <label>
          Город по умолчанию
          <input v-model.trim="form.default_city" type="text" placeholder="Санкт-Петербург" />
        </label>

        <label>
          City slug
          <input v-model.trim="form.city_slug" type="text" placeholder="saint-petersburg" />
        </label>
      </div>

      <div class="errors" v-if="errors.length">
        <p class="errors__title">Пожалуйста, исправьте ошибки:</p>
        <ul>
          <li v-for="(error, index) in errors" :key="index">{{ error }}</li>
        </ul>
      </div>

      <button type="submit" class="primary-button">Оптимизировать маршрут</button>
    </fieldset>
  </form>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import AddressSearchInput from './AddressSearchInput.vue';
import {
  TEST_ADDRESS_SETS,
  pickRandomAddressSet,
  shuffleAddresses,
} from '../data/testAddressSets';
import { confirmAddress } from '../services/addressApi';

const emit = defineEmits(['submit', 'selected-points-change']);
defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
});

const GEOCODING_AREA_OPTIONS = [
  { value: 'default_spb', label: 'Санкт-Петербург' },
  { value: 'spb_lenobl', label: 'СПб + ближайшая Ленобласть' },
  { value: 'custom_area', label: 'Район или город' },
];

const form = reactive({
  start_address: '',
  end_address: '',
  addresses_text: '',
  batch_size: 15,
  optimization_metric: 'duration',
  city_slug: 'saint-petersburg',
  default_city: 'Санкт-Петербург',
  search_area_mode: 'default_spb',
  geocoding_area: '',
});

const errors = ref([]);
const testSetMessage = ref('');
const startCandidate = ref(null);
const endCandidate = ref(null);
const startLowConfidenceAccepted = ref(false);
const endLowConfidenceAccepted = ref(false);
const waypointMode = ref('list');
const waypointCandidates = ref([]);
const waypointSearchQuery = ref('');
const waypointInputKey = ref(0);
const showWaypointSearch = ref(false);
const onlineOptimization = ref(false);

const defaultRegion = computed(() => (
  form.search_area_mode === 'spb_lenobl'
    ? 'Ленинградская область'
    : ''
));

const canOptimizeWaypoints = computed(() => (
  waypointCandidates.value.length > 1
  && hasCoordinates(startCandidate.value)
  && hasCoordinates(endCandidate.value)
));

watch(waypointMode, () => {
  emitSelectedPoints();
});

function parseAddresses(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function activeWaypointAddresses() {
  if (waypointMode.value === 'search') {
    return waypointCandidates.value.map((candidate) => candidate.display_name);
  }

  return parseAddresses(form.addresses_text);
}

function validate() {
  const list = [];
  if (!startCandidate.value || !hasCoordinates(startCandidate.value)) {
    list.push('Выберите начальный адрес из подсказок.');
  }
  if (!endCandidate.value || !hasCoordinates(endCandidate.value)) {
    list.push('Выберите конечный адрес из подсказок.');
  }
  if (startCandidate.value?.outside_supported_region) {
    list.push('Выбранный начальный адрес находится вне поддерживаемой зоны.');
  }
  if (endCandidate.value?.outside_supported_region) {
    list.push('Выбранный конечный адрес находится вне поддерживаемой зоны.');
  }
  if (startCandidate.value && isLowConfidence(startCandidate.value) && !startLowConfidenceAccepted.value) {
    list.push('Начальный адрес найден с низкой точностью, его нужно проверить.');
  }
  if (endCandidate.value && isLowConfidence(endCandidate.value) && !endLowConfidenceAccepted.value) {
    list.push('Конечный адрес найден с низкой точностью, его нужно проверить.');
  }
  if (waypointMode.value === 'search') {
    waypointCandidates.value.forEach((candidate, index) => {
      if (!hasCoordinates(candidate)) {
        list.push(`Промежуточная точка ${index + 1} без координат.`);
      }
      if (candidate.outside_supported_region) {
        list.push(`Промежуточная точка ${index + 1} находится вне поддерживаемой зоны.`);
      }
      if (isLowConfidence(candidate) && !candidate.verified) {
        list.push(`Промежуточная точка ${index + 1} найдена с низкой точностью, ее нужно проверить.`);
      }
    });
  }
  if (form.batch_size < 1 || form.batch_size > 20 || Number.isNaN(form.batch_size)) {
    list.push('Размер пакета должен быть от 1 до 20.');
  }
  if (!['duration', 'distance'].includes(form.optimization_metric)) {
    list.push('Выберите метрику оптимизации.');
  }
  if (form.search_area_mode === 'custom_area' && !form.geocoding_area.trim()) {
    list.push('Укажите район или населенный пункт для поиска.');
  }
  const addresses = activeWaypointAddresses();
  if (addresses.length > 100) {
    list.push('Слишком много адресов для MVP. Максимум: 100.');
  }
  return list;
}

function hasCoordinates(candidate) {
  return Number.isFinite(Number(candidate?.latitude)) && Number.isFinite(Number(candidate?.longitude));
}

function isLowConfidence(candidate) {
  return Number(candidate?.confidence_score ?? 100) < 75;
}

function selectedRouteAddress(candidate) {
  if (!candidate || !hasCoordinates(candidate)) {
    return null;
  }

  return {
    address_id: candidate.address_id || null,
    display_name: candidate.display_name,
    latitude: Number(candidate.latitude),
    longitude: Number(candidate.longitude),
    confidence_score: candidate.confidence_score ?? null,
    geocoding_status: candidate.geocoding_status || 'found',
  };
}

function selectedWaypointAddresses() {
  if (waypointMode.value !== 'search') {
    return [];
  }

  return waypointCandidates.value.map((candidate) => selectedRouteAddress(candidate));
}

function previewPoint(candidate, type, order) {
  if (!candidate || !hasCoordinates(candidate)) {
    return null;
  }

  return {
    order,
    type,
    label: candidate.display_name,
    latitude: Number(candidate.latitude),
    longitude: Number(candidate.longitude),
    confidence_score: candidate.confidence_score ?? null,
    original_index: order,
    address: {
      original_address: candidate.display_name,
      input_address: candidate.original_query || candidate.display_name,
    },
  };
}

function emitSelectedPoints() {
  const waypointPreviewPoints = waypointMode.value === 'search'
    ? waypointCandidates.value.map((candidate, index) => previewPoint(candidate, 'waypoint', index + 1))
    : [];
  const endOrder = waypointPreviewPoints.length + 1;

  emit(
    'selected-points-change',
    [
      previewPoint(startCandidate.value, 'start', 0),
      ...waypointPreviewPoints,
      previewPoint(endCandidate.value, 'end', endOrder),
    ].filter(Boolean),
  );
}

function waypointEntry(candidate) {
  return {
    ...candidate,
    client_id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    verified: !isLowConfidence(candidate),
  };
}

function candidateDistanceMeters(first, second) {
  if (!hasCoordinates(first) || !hasCoordinates(second)) {
    return Number.POSITIVE_INFINITY;
  }

  const toRadians = (degrees) => degrees * Math.PI / 180;
  const radiusM = 6371000;
  const lat1 = toRadians(Number(first.latitude));
  const lat2 = toRadians(Number(second.latitude));
  const deltaLat = toRadians(Number(second.latitude) - Number(first.latitude));
  const deltaLon = toRadians(Number(second.longitude) - Number(first.longitude));
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;

  return radiusM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function bestWaypointInsertionIndex(candidate, existingWaypoints = waypointCandidates.value) {
  if (
    !onlineOptimization.value
    || !hasCoordinates(startCandidate.value)
    || !hasCoordinates(endCandidate.value)
    || !hasCoordinates(candidate)
  ) {
    return existingWaypoints.length;
  }

  const anchors = [
    startCandidate.value,
    ...existingWaypoints,
    endCandidate.value,
  ];
  let bestIndex = existingWaypoints.length;
  let bestDelta = Number.POSITIVE_INFINITY;

  for (let index = 0; index < anchors.length - 1; index += 1) {
    const before = anchors[index];
    const after = anchors[index + 1];
    const delta = candidateDistanceMeters(before, candidate)
      + candidateDistanceMeters(candidate, after)
      - candidateDistanceMeters(before, after);

    if (delta < bestDelta) {
      bestDelta = delta;
      bestIndex = index;
    }
  }

  return bestIndex;
}

function insertWaypoint(candidate) {
  const entry = waypointEntry(candidate);
  const insertAt = bestWaypointInsertionIndex(entry);
  waypointCandidates.value.splice(insertAt, 0, entry);
  emitSelectedPoints();
  return entry.client_id;
}

function replaceWaypoint(clientId, patch) {
  const index = waypointCandidates.value.findIndex((candidate) => candidate.client_id === clientId);
  if (index < 0) {
    return;
  }

  waypointCandidates.value[index] = {
    ...waypointCandidates.value[index],
    ...patch,
  };
  emitSelectedPoints();
}

function clearWaypointSearch() {
  waypointSearchQuery.value = '';
}

async function handleWaypointSelected(candidate) {
  const clientId = insertWaypoint(candidate);
  waypointSearchQuery.value = '';
  waypointInputKey.value += 1;
  showWaypointSearch.value = true;

  try {
    const saved = await confirmAddress({
      original_query: candidate.original_query || candidate.display_name,
      selected_candidate: candidate,
    });
    replaceWaypoint(clientId, {
      address_id: saved.address_id,
      geocoding_status: saved.geocoding_status || candidate.geocoding_status,
    });
  } catch (error) {
    errors.value = [String(error?.message || error || 'Не удалось сохранить выбранный адрес.')];
  }
}

function removeWaypoint(index) {
  waypointCandidates.value.splice(index, 1);
  emitSelectedPoints();
}

function moveWaypoint(index, direction) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= waypointCandidates.value.length) {
    return;
  }

  const [candidate] = waypointCandidates.value.splice(index, 1);
  waypointCandidates.value.splice(nextIndex, 0, candidate);
  emitSelectedPoints();
}

function optimizeWaypointOrder() {
  if (!canOptimizeWaypoints.value) {
    return;
  }

  const previousOnlineValue = onlineOptimization.value;
  onlineOptimization.value = true;
  const ordered = [];
  for (const candidate of waypointCandidates.value) {
    const insertAt = bestWaypointInsertionIndex(candidate, ordered);
    ordered.splice(insertAt, 0, candidate);
  }
  waypointCandidates.value = ordered;
  onlineOptimization.value = previousOnlineValue;
  emitSelectedPoints();
}

function handleOnlineOptimizationChange() {
  if (onlineOptimization.value && canOptimizeWaypoints.value) {
    optimizeWaypointOrder();
  }
}

async function handleAddressSelected(role, candidate) {
  const target = role === 'start' ? startCandidate : endCandidate;
  const accepted = role === 'start' ? startLowConfidenceAccepted : endLowConfidenceAccepted;
  target.value = candidate;
  accepted.value = !isLowConfidence(candidate);
  emitSelectedPoints();
  if (onlineOptimization.value && canOptimizeWaypoints.value) {
    optimizeWaypointOrder();
  }

  try {
    const saved = await confirmAddress({
      original_query: candidate.original_query || candidate.display_name,
      selected_candidate: candidate,
    });
    target.value = {
      ...candidate,
      address_id: saved.address_id,
      geocoding_status: saved.geocoding_status || candidate.geocoding_status,
    };
    emitSelectedPoints();
    if (onlineOptimization.value && canOptimizeWaypoints.value) {
      optimizeWaypointOrder();
    }
  } catch (error) {
    errors.value = [String(error?.message || error || 'Не удалось сохранить выбранный адрес.')];
  }
}

function handleAddressCleared(role) {
  if (role === 'start') {
    startCandidate.value = null;
    startLowConfidenceAccepted.value = false;
  } else {
    endCandidate.value = null;
    endLowConfidenceAccepted.value = false;
  }
  emitSelectedPoints();
}

function handleAddressSearchError(message) {
  if (message) {
    errors.value = [message];
  }
}

function applySearchAreaFromSet(set) {
  const defaultCity = (set.defaultCity || '').toLowerCase();
  const startAddress = (set.startAddress || '').toLowerCase();
  const joined = `${defaultCity} ${startAddress}`;

  if (joined.includes('кириши')) {
    form.search_area_mode = 'custom_area';
    form.geocoding_area = 'Кириши';
    return;
  }
  if (joined.includes('петергоф')) {
    form.search_area_mode = 'custom_area';
    form.geocoding_area = 'Петергоф';
    return;
  }

  form.search_area_mode = 'default_spb';
  form.geocoding_area = '';
}

function applyTestSet(set) {
  form.addresses_text = shuffleAddresses(set.addresses).join('\n');
  form.city_slug = set.citySlug || 'saint-petersburg';
  form.default_city = set.defaultCity || 'Санкт-Петербург';
  form.start_address = set.startAddress || form.start_address || 'Санкт-Петербург, Дворцовая площадь';
  form.end_address = set.endAddress || form.end_address || 'Санкт-Петербург, Московский вокзал';
  waypointMode.value = 'list';
  waypointCandidates.value = [];
  waypointSearchQuery.value = '';
  showWaypointSearch.value = false;
  onlineOptimization.value = false;
  startCandidate.value = null;
  endCandidate.value = null;
  startLowConfidenceAccepted.value = false;
  endLowConfidenceAccepted.value = false;
  emitSelectedPoints();
  applySearchAreaFromSet(set);
  errors.value = [];
  testSetMessage.value = `${set.label} вставлен: ${set.addresses.length} адресов, порядок перемешан.`;
}

function applyRandomTestSet() {
  applyTestSet(pickRandomAddressSet());
}

function buildGeocodingPayload() {
  if (form.search_area_mode === 'custom_area') {
    return {
      geocoding_area: form.geocoding_area.trim(),
    };
  }

  return {
    geocoding_context: {
      type: form.search_area_mode,
      bounded: false,
    },
  };
}

function handleSubmit() {
  errors.value = validate();
  if (errors.value.length) {
    return;
  }

  emit('submit', {
    start_address: form.start_address,
    end_address: form.end_address,
    start_selected: selectedRouteAddress(startCandidate.value),
    end_selected: selectedRouteAddress(endCandidate.value),
    addresses: activeWaypointAddresses(),
    waypoints_selected: selectedWaypointAddresses(),
    batch_size: Number(form.batch_size),
    optimization_metric: form.optimization_metric,
    city_slug: form.city_slug,
    default_city: form.default_city || null,
    ...buildGeocodingPayload(),
  });
}
</script>

<style scoped>
.route-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

fieldset {
  border: none;
  margin: 0;
  padding: 0;
}

legend {
  font-size: 1.2rem;
  margin-bottom: 12px;
}

label,
.search-area__label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-weight: 600;
  color: #22303f;
}

input,
textarea,
select {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #d2dae6;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.97rem;
  background: #fff;
}

textarea {
  min-height: 150px;
  resize: vertical;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.search-area,
.test-sets {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid #dbe5f7;
  border-radius: 8px;
  background: #f8fbff;
}

.search-area__options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.search-area__option {
  align-items: center;
  flex-direction: row;
  gap: 8px;
  min-height: 42px;
  padding: 8px 10px;
  border: 1px solid #bfd0ef;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.search-area__option input {
  width: auto;
}

.search-area__custom {
  margin-top: 2px;
}

.verification-check {
  align-items: flex-start;
  flex-direction: row;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #f5c56b;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 0.9rem;
  font-weight: 600;
}

.verification-check input {
  width: auto;
  margin-top: 2px;
}

.waypoints-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.waypoints-panel__header {
  display: flex;
  align-items: stretch;
  flex-direction: column;
  gap: 12px;
  color: #22303f;
  font-weight: 700;
}

.waypoint-mode {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 4px;
  border: 1px solid #d2dae6;
  border-radius: 8px;
  background: #f8fbff;
}

.waypoint-mode__option,
.online-toggle,
.waypoint-verification {
  align-items: center;
  flex-direction: row;
  gap: 8px;
}

.waypoint-mode__option {
  min-height: 32px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.waypoint-mode__option--active {
  background: #dceaff;
  color: #123d7a;
}

.waypoint-mode__option input,
.online-toggle input,
.waypoint-verification input {
  width: auto;
}

.waypoint-search-mode {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.waypoint-search-mode__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.secondary-button,
.selected-waypoints__actions button {
  border: 1px solid #bfd0ef;
  border-radius: 8px;
  padding: 9px 10px;
  background: #ffffff;
  color: #1a3d7c;
  font-weight: 700;
  cursor: pointer;
}

.secondary-button:hover,
.selected-waypoints__actions button:hover {
  border-color: #2f6dde;
}

.secondary-button:disabled,
.selected-waypoints__actions button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.selected-waypoints {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.selected-waypoints__item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid #dbe5f7;
  border-radius: 8px;
  background: #f8fbff;
}

.selected-waypoints__content {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  align-items: start;
}

.selected-waypoints__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #2f6dde;
  color: #fff;
  font-size: 0.85rem;
  font-weight: 800;
}

.selected-waypoints__text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.selected-waypoints__name {
  overflow-wrap: anywhere;
}

.selected-waypoints__meta {
  color: #64748b;
  font-size: 0.84rem;
}

.selected-waypoints__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.waypoint-verification {
  color: #92400e;
  font-size: 0.88rem;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.test-sets__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #22303f;
  font-weight: 700;
}

.test-sets__buttons {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.test-sets button {
  border: 1px solid #bfd0ef;
  border-radius: 8px;
  padding: 9px 10px;
  background: #ffffff;
  color: #1a3d7c;
  font-weight: 700;
  cursor: pointer;
}

.test-sets button:hover {
  border-color: #2f6dde;
}

.test-sets__random {
  flex: 0 0 auto;
}

.test-sets__message {
  margin: 0;
  color: #475569;
  font-size: 0.9rem;
}

.errors {
  background: #fff1f0;
  border: 1px solid #ffccd5;
  border-radius: 8px;
  padding: 14px;
  color: #92140c;
}

.errors__title {
  margin: 0 0 8px;
  font-weight: 700;
}

.primary-button {
  width: 100%;
  border: none;
  border-radius: 8px;
  padding: 14px 18px;
  background: #2f6dde;
  color: white;
  font-size: 1rem;
  cursor: pointer;
}

.primary-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .row,
  .search-area__options {
    grid-template-columns: 1fr;
  }

  .test-sets__header {
    align-items: stretch;
    flex-direction: column;
  }

  .test-sets__buttons {
    grid-template-columns: 1fr;
  }

  .waypoints-panel__header,
  .waypoint-search-mode__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .waypoint-mode {
    width: 100%;
  }
}
</style>
