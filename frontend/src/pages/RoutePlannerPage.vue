<template>
  <main class="planner-page">
    <RouteMap
      class="planner-map"
      :orderedPoints="result?.ordered_points || []"
    />

    <aside class="side-panel">
      <h1>Оптимизация маршрута</h1>

      <RouteForm :loading="loading" @submit="handleSubmit" />

      <div class="side-panel__result">
        <div v-if="message" class="empty-state">{{ message }}</div>

        <div v-if="loading" class="loading-state">Строим маршрут...</div>

        <ErrorBlock
          v-if="error"
          :error="error"
          :failedAddresses="failedAddresses"
        />

        <WarningBlock v-if="warnings.length" :warnings="warnings" />

        <RouteSummary v-if="result" :result="result" />

        <OrderedPointsList
          v-if="result"
          :orderedPoints="result.ordered_points || []"
        />

        <RouteBatches
          v-if="result"
          :batches="result.batches || []"
        />
      </div>
    </aside>
  </main>
</template>

<script setup>
import { ref, computed } from 'vue';
import RouteForm from '../components/RouteForm.vue';
import RouteSummary from '../components/RouteSummary.vue';
import RouteMap from '../components/RouteMap.vue';
import OrderedPointsList from '../components/OrderedPointsList.vue';
import RouteBatches from '../components/RouteBatches.vue';
import ErrorBlock from '../components/ErrorBlock.vue';
import WarningBlock from '../components/WarningBlock.vue';
import { optimizeRoute } from '../api/routesApi';
import { normalizeApiError } from '../utils/errorUtils';

const loading = ref(false);
const result = ref(null);
const error = ref('');
const warnings = ref([]);
const failedAddresses = ref([]);
const draftSelectedPoints = ref([]);

const mapPoints = computed(() => (
  result.value
    ? result.value.ordered_points || []
    : draftSelectedPoints.value
));

const message = computed(() => {
  if (loading.value) {
    return '';
  }
  if (!result.value && !error.value && !draftSelectedPoints.value.length) {
    return 'Введите адреса и нажмите «Оптимизировать маршрут».';
  }
  return '';
});

async function handleSubmit(payload) {
  loading.value = true;
  error.value = '';
  result.value = null;
  warnings.value = [];
  failedAddresses.value = [];

  try {
    const response = await optimizeRoute(payload);
    result.value = response;
    warnings.value = response.warnings || [];
    failedAddresses.value = response.failed_addresses || [];
  } catch (err) {
    const normalizedError = normalizeApiError(err);
    error.value = {
      message: normalizedError.message,
      code: normalizedError.code,
      details: normalizedError.details,
    };
    warnings.value = normalizedError.warnings;
    failedAddresses.value = normalizedError.failed_addresses;
  } finally {
    loading.value = false;
  }
}

function handleSelectedPointsChange(points) {
  draftSelectedPoints.value = points || [];
}
</script>

<style scoped>
.planner-page {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #e5e7eb;
}

.planner-map {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.side-panel {
  position: absolute;
  top: 16px;
  left: 16px;
  bottom: 16px;
  z-index: 10;

  width: 420px;
  max-width: calc(100vw - 32px);

  overflow-y: auto;
  overscroll-behavior: contain;

  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.22);
}

h1 {
  margin: 0 0 16px;
  font-size: 1.35rem;
}

.side-panel__result {
  margin-top: 18px;
}

.loading-state,
.empty-state {
  padding: 14px 16px;
  background: #f4f8ff;
  color: #1a3d7c;
  border-radius: 12px;
  margin-bottom: 14px;
}

@media (max-width: 720px) {
  .side-panel {
    top: auto;
    right: 12px;
    left: 12px;
    bottom: 12px;
    width: auto;
    max-height: 55vh;
  }
}
</style>
