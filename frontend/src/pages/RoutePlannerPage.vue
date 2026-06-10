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
        <ErrorBlock v-if="error" :message="error" />
        <WarningBlock v-if="warnings.length" :warnings="warnings" />

        <RouteSummary v-if="result" :result="result" />
        <RouteMap v-if="result" :orderedPoints="result.ordered_points" />
        <OrderedPointsList v-if="result" :orderedPoints="result.ordered_points" />
        <RouteBatches v-if="result" :batches="result.batches" />

        <section v-if="failedAddresses.length" class="failed-addresses">
          <h2>Не удалось обработать адреса</h2>
          <ul>
            <li v-for="failed in failedAddresses" :key="`${failed.input_index}-${failed.input_address}`">
              <strong>{{ failed.input_address }}</strong>
              <div>Тип: {{ failed.role }}</div>
              <div>Причина: {{ failed.error }}</div>
              <div>Статус: {{ failed.geocoding_status || "-" }}</div>
              <div v-if="failed.normalized_address">Нормализованный адрес: {{ failed.normalized_address }}</div>
            </li>
          </ul>
        </section>
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
    error.value = err?.message || 'Произошла ошибка при запросе маршрута.';
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

.failed-addresses {
  margin-top: 24px;
}

.failed-addresses ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.failed-addresses li {
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  margin-bottom: 12px;
  background: #fff7f6;
}

@media (min-width: 1000px) {
  .layout {
    grid-template-columns: 360px 1fr;
    align-items: start;
  }
}
</style>
