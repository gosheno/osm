<template>
  <section class="ordered-list">
    <h2>Порядок точек</h2>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Тип</th>
          <th>Адрес</th>
          <th>Нормализованный адрес</th>
          <th>Координаты</th>
          <th>Статус</th>
          <th>Из кэша</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="point in orderedPoints" :key="point.order">
          <td>{{ point.order + 1 }}</td>
          <td>{{ point.type }}</td>
          <td>{{ point.address?.original_address || point.label || '-' }}</td>
          <td>{{ point.address?.normalized_address || '-' }}</td>
          <td>{{ point.latitude.toFixed(6) }}, {{ point.longitude.toFixed(6) }}</td>
          <td>{{ point.address?.geocoding_status || '-' }}</td>
          <td>{{ point.address?.from_cache ? 'Да' : 'Нет' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
const props = defineProps({
  orderedPoints: {
    type: Array,
    required: true,
  },
});
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
