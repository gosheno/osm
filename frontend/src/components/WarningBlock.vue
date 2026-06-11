<template>
  <section class="warning-block">
    <h2>Предупреждения</h2>
    <ul>
      <li v-for="(warning, index) in warnings" :key="index">
        {{ warningText(warning) }}
      </li>
    </ul>
  </section>
</template>

<script setup>
const props = defineProps({
  warnings: {
    type: Array,
    required: true,
  },
});

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
</script>

<style scoped>
.warning-block {
  padding: 18px;
  background: #fffbeb;
  border: 1px solid #f9e5b0;
  border-radius: 14px;
  margin-bottom: 18px;
}

.warning-block ul {
  margin: 0;
  padding-left: 20px;
}
</style>
