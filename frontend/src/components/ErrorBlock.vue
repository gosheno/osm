<template>
  <section class="error-block">
    <h2>Ошибка</h2>
    <p>{{ message }}</p>
  </section>
</template>

<script setup>
const props = defineProps({
  message: {
    type: String,
    required: true,
  },
});
</script>

<style scoped>
.error-block {
  padding: 18px;
  background: #fff1f0;
  color: #b91c1c;
  border: 1px solid #f8d7da;
  border-radius: 14px;
  margin-bottom: 18px;
}
</style>
