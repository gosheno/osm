<template>
  <section class="error-block">
    <h2>Ошибка</h2>
    <p>{{ error.message }}</p>

    <div class="error-meta" v-if="error.code || error.details">
      <div v-if="error.code"><strong>Код:</strong> {{ error.code }}</div>
      <button v-if="error.details" @click="showDetails = !showDetails" type="button">
        {{ showDetails ? "Скрыть подробности" : "Показать подробности" }}
      </button>
    </div>

    <pre v-if="showDetails && error.details" class="error-details">{{ error.details }}</pre>

    <section v-if="failedAddresses.length" class="failed-addresses">
      <h3>Не удалось обработать адреса</h3>
      <ul>
        <li v-for="failed in failedAddresses" :key="`${failed.input_index}-${failed.input_address}`">
          <strong>{{ addressTitle(failed) }}</strong>
          <div>Тип: {{ failed.type || failed.role || "-" }}</div>
          <div>Код: {{ failed.code || "ADDRESS_NOT_FOUND" }}</div>
          <div>Причина: {{ failed.reason || failed.error || "-" }}</div>
          <div>Статус: {{ failed.geocoding_status || "-" }}</div>
          <div>Провайдер: {{ failed.geocoding_provider || "-" }}</div>
          <div>Источник: {{ failed.source || "-" }}</div>
          <div v-if="failed.geocoding_context_label">Область поиска: {{ failed.geocoding_context_label }}</div>
          <div v-if="failed.geocoding_query">Запрос: {{ failed.geocoding_query }}</div>
          <div v-if="failed.geocoding_score !== null && failed.geocoding_score !== undefined">
            Оценка: {{ failed.geocoding_score }}
          </div>
          <div v-if="failed.normalized_address">Нормализованный адрес: {{ failed.normalized_address }}</div>
        </li>
      </ul>
    </section>
  </section>
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({
  error: {
    type: Object,
    required: true,
  },
  failedAddresses: {
    type: Array,
    required: false,
    default: () => [],
  },
});

const showDetails = ref(false);

function addressTitle(failed) {
  return failed.input_address || failed.original_address || failed.address_for_geocoding || "-";
}
</script>

<style scoped>
.error-block {
  padding: 18px;
  background: #fff1f0;
  color: #b91c1c;
  border: 1px solid #f8d7da;
  border-radius: 8px;
  margin-bottom: 18px;
}

.failed-addresses {
  margin-top: 16px;
}

.failed-addresses ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.failed-addresses li {
  padding: 12px;
  border: 1px solid #f8d7da;
  border-radius: 8px;
  margin-top: 10px;
  background: #fff7f6;
}

.error-details {
  overflow-x: auto;
  white-space: pre-wrap;
}
</style>
