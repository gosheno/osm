<template>
  <main class="planner-page">
    <h1>Оптимизация маршрута по адресам</h1>

    <div class="layout">
      <section class="layout__form">
        <RouteForm :loading="loading" @submit="handleSubmit" />
      </section>

      <section class="layout__result">
        <div v-if="message" class="empty-state">{{ message }}</div>
        <div v-if="loading" class="loading-state">Строим маршрут...</div>
        <ErrorBlock
          v-if="error"
          :error="error"
          :failedAddresses="failedAddresses"
        />
        <WarningBlock v-if="warnings.length" :warnings="warnings" />

        <RouteSummary v-if="result" :result="result" />
        <RouteMap v-if="result" :orderedPoints="result.ordered_points || []" />
        <OrderedPointsList v-if="result" :orderedPoints="result.ordered_points || []" />
        <RouteBatches v-if="result" :batches="result.batches || []" />
      </section>
    </div>
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

const message = computed(() => {
  if (loading.value) {
    return '';
  }
  if (!result.value && !error.value) {
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
</script>

<style scoped>
.planner-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

h1 {
  margin-bottom: 24px;
  font-size: 2rem;
}

.layout {
  display: grid;
  gap: 24px;
}

.layout__form,
.layout__result {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
  padding: 20px;
}

.loading-state,
.empty-state {
  padding: 18px 20px;
  background: #f4f8ff;
  color: #1a3d7c;
  border-radius: 12px;
  margin-bottom: 18px;
}

@media (min-width: 1000px) {
  .layout {
    grid-template-columns: 360px 1fr;
    align-items: start;
  }
}
</style>
