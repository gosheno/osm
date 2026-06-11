<template>
  <section class="summary-card">
    <h2>Сводка маршрута</h2>
    <dl>
      <div>
        <dt>Статус</dt>
        <dd>{{ result.status }}</dd>
      </div>
      <div v-if="result.route_job_id">
        <dt>ID маршрута</dt>
        <dd>{{ result.route_job_id }}</dd>
      </div>
      <div>
        <dt>Адресов</dt>
        <dd>{{ result.total_input_addresses }}</dd>
      </div>
      <div>
        <dt>Всего точек</dt>
        <dd>{{ result.total_points }}</dd>
      </div>
      <div>
        <dt>Пакетов</dt>
        <dd>{{ result.batches.length }}</dd>
      </div>
      <div>
        <dt>Дистанция</dt>
        <dd>{{ formatDistance(result.total_distance_m) }}</dd>
      </div>
      <div>
        <dt>Время</dt>
        <dd>{{ formatDuration(result.total_duration_s) }}</dd>
      </div>
      <div>
        <dt>Метрика</dt>
        <dd>{{ result.optimization_metric }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { formatDistance, formatDuration } from '../utils/formatters';
const props = defineProps({
  result: {
    type: Object,
    required: true,
  },
});
</script>

<style scoped>
.summary-card {
  padding: 18px;
  background: #f8fbff;
  border: 1px solid #dbe9ff;
  border-radius: 16px;
  margin-bottom: 24px;
}

.summary-card h2 {
  margin-top: 0;
}

dl {
  display: grid;
  gap: 12px;
  margin: 0;
}

dt {
  font-weight: 700;
  color: #0f2040;
}

dd {
  margin: 0;
  color: #334155;
}
</style>
