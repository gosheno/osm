<template>
  <section class="batches-block">
    <h2>Пакеты маршрута</h2>
    <div v-if="!batches.length" class="empty">Пакеты отсутствуют.</div>
    <div v-for="batch in batches" :key="batch.batch_number" class="batch-card">
      <div class="batch-header">
        <div>
          <strong>Пакет {{ batch.batch_number }}</strong>
          <div>Точек: {{ batch.points_count }}</div>
        </div>
        <div>
          <div>Дистанция: {{ formatDistance(batch.distance_m) }}</div>
          <div>Время: {{ formatDuration(batch.duration_s) }}</div>
        </div>
      </div>

      <div v-if="batch.warnings?.length" class="batch-warnings">
        <strong>Предупреждения:</strong>
        <ul>
          <li v-for="(warning, index) in batch.warnings" :key="index">{{ warning }}</li>
        </ul>
      </div>

      <div class="batch-actions">
        <button
          v-if="batch.yandex_maps_url"
          @click="openYandex(batch.yandex_maps_url)"
          type="button"
        >
          Открыть в Яндекс.Картах
        </button>
        <button
          v-if="batch.yandex_maps_url"
          @click="copyLink(batch.yandex_maps_url, batch.batch_number)"
          type="button"
        >
          {{ copiedBatch === batch.batch_number ? 'Ссылка скопирована' : 'Скопировать ссылку' }}
        </button>
      </div>

      <div class="batch-points">
        <h3>Точки пакета</h3>
        <ol>
          <li v-for="point in batch.points" :key="point.global_order">
            {{ point.batch_order + 1 }}. {{ point.type }} — {{ point.label || '-' }} ({{ point.latitude.toFixed(6) }}, {{ point.longitude.toFixed(6) }})
          </li>
        </ol>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue';
import { formatDistance, formatDuration } from '../utils/formatters';
const props = defineProps({
  batches: {
    type: Array,
    required: true,
  },
});

const copiedBatch = ref(null);

function openYandex(url) {
  window.open(url, '_blank');
}

async function copyLink(url, batchNumber) {
  try {
    await navigator.clipboard.writeText(url);
    copiedBatch.value = batchNumber;
    setTimeout(() => {
      if (copiedBatch.value === batchNumber) {
        copiedBatch.value = null;
      }
    }, 2000);
  } catch (err) {
    console.error('Copy failed', err);
  }
}
</script>

<style scoped>
.batches-block {
  margin-top: 24px;
}

.batch-card {
  padding: 18px;
  border: 1px solid #dbe5f7;
  border-radius: 16px;
  margin-bottom: 18px;
}

.batch-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.batch-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.batch-actions button {
  padding: 10px 16px;
  border-radius: 12px;
  background: #2f6dde;
  color: white;
  border: 0;
  cursor: pointer;
}

.batch-actions button:hover {
  opacity: 0.95;
}

.batch-warnings {
  background: #fffbeb;
  border: 1px solid #f7dfb6;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 14px;
}

.batch-points ol {
  margin: 0;
  padding-left: 20px;
}
</style>
