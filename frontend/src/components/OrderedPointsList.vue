<template>
  <section class="ordered-list">
    <h2>Порядок точек</h2>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Тип</th>
          <th>Адрес</th>
          <th>Район</th>
          <th>Нормализованный адрес</th>
          <th>Координаты</th>
          <th>Статус</th>
          <th>Провайдер</th>
          <th>Источник</th>
          <th>Из кэша</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="point in orderedPoints" :key="point.order">
          <td>{{ pointNumber(point) }}</td>
          <td>{{ point.type }}</td>
          <td>{{ formatAddressLabel(point) }}</td>
          <td>{{ point.district || '-' }}</td>
          <td>{{ point.address?.normalized_address || '-' }}</td>
          <td>{{ formatCoordinate(point.latitude) }}, {{ formatCoordinate(point.longitude) }}</td>
          <td>{{ point.address?.geocoding_status || '-' }}</td>
          <td>{{ point.address?.geocoding_provider || '-' }}</td>
          <td>{{ point.address?.source || '-' }}</td>
          <td>{{ point.address?.from_cache ? 'Да' : 'Нет' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { formatAddressLabel, formatCoordinate } from '../utils/formatters';

const props = defineProps({
  orderedPoints: {
    type: Array,
    required: true,
  },
});

function pointNumber(point) {
  const order = Number(point.order);
  return Number.isFinite(order) ? order + 1 : '-';
}
</script>

<style scoped>
.ordered-list {
  margin-top: 24px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
}

th,
td {
  padding: 12px 10px;
  border: 1px solid #e2e8f0;
  text-align: left;
}

th {
  background: #f8fafc;
  font-weight: 700;
}

tbody tr:nth-child(even) {
  background: #f8f9fb;
}
</style>
