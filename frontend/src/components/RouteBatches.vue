<template>
  <section class="batches-block">
    <h2>Пакеты маршрута</h2>
    <div v-if="!batches.length" class="empty">Пакеты отсутствуют.</div>
    <div v-for="(batch, batchIndex) in batches" :key="batch.batch_number || batchIndex" class="batch-card">
      <div class="batch-header">
        <div>
          <strong>Пакет {{ batch.batch_number }}</strong>
          <div>Точек: {{ batch.points_count }}</div>
          <div v-if="districtText(batch)">Район: {{ districtText(batch) }}</div>
        </div>
        <div>
          <div>Дистанция: {{ formatDistance(batch.distance_m) }}</div>
          <div>Время: {{ formatDuration(batch.duration_s) }}</div>
        </div>
      </div>

      <div v-if="batch.warnings?.length" class="batch-warnings">
        <strong>Предупреждения:</strong>
        <ul>
          <li v-for="(warning, index) in batch.warnings" :key="index">{{ warningText(warning) }}</li>
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
          <li v-for="(point, pointIndex) in batch.points" :key="point.global_order ?? pointIndex">
            {{ batchPointNumber(point) }}. {{ point.type }} — {{ formatAddressLabel(point) }} ({{ formatCoordinate(point.latitude) }}, {{ formatCoordinate(point.longitude) }})
            <span v-if="point.district" class="point-district">· {{ point.district }}</span>
          </li>
        </ol>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue';
import {
  formatAddressLabel,
  formatCoordinate,
  formatDistance,
  formatDuration,
} from '../utils/formatters';
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

function batchPointNumber(point) {
  const order = Number(point.batch_order);
  return Number.isFinite(order) ? order + 1 : '-';
}

function districtText(batch) {
  if (batch.districts?.length) {
    return batch.districts.join(', ');
  }
  return batch.district || '';
}

function warningText(warning) {
  if (typeof warning === 'string') {
    return warning;
  }
  if (warning?.message) {
    return warning.message;
  }
  if (warning?.details) {
    return typeof warning.details === 'string'
      ? warning.details
      : JSON.stringify(warning.details);
  }
  return warning?.code || 'Предупреждение без описания.';
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

.point-district {
  color: #475569;
}
</style>
