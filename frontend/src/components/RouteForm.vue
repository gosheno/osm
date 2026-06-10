<template>
  <form class="route-form" @submit.prevent="handleSubmit">
    <fieldset :disabled="loading">
      <legend>Создать маршрут</legend>

      <label>
        Начальный адрес
        <input v-model.trim="form.start_address" type="text" placeholder="Санкт-Петербург, Дворцовая площадь" />
      </label>

      <label>
        Конечный адрес
        <input v-model.trim="form.end_address" type="text" placeholder="Санкт-Петербург, Московский вокзал" />
      </label>

      <label>
        Промежуточные адреса (каждый с новой строки)
        <textarea v-model="form.addresses_text" rows="8" placeholder="Санкт-Петербург, Набережная Кутузова 12\nСанкт-Петербург, Большой проспект П.С. 35"></textarea>
      </label>

      <div class="row">
        <label>
          Размер пакета
          <input v-model.number="form.batch_size" type="number" min="1" max="20" />
        </label>

        <label>
          Метрика
          <select v-model="form.optimization_metric">
            <option value="duration">По времени</option>
            <option value="distance">По расстоянию</option>
          </select>
        </label>
      </div>

      <label>
        City slug
        <input v-model.trim="form.city_slug" type="text" placeholder="saint-petersburg" />
      </label>

      <div class="errors" v-if="errors.length">
        <p class="errors__title">Пожалуйста, исправьте ошибки:</p>
        <ul>
          <li v-for="(error, index) in errors" :key="index">{{ error }}</li>
        </ul>
      </div>

      <button type="submit" class="primary-button">Оптимизировать маршрут</button>
    </fieldset>
  </form>
</template>

<script setup>
import { reactive, ref } from 'vue';

const emit = defineEmits(['submit']);
const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
});

const form = reactive({
  start_address: '',
  end_address: '',
  addresses_text: '',
  batch_size: 15,
  optimization_metric: 'duration',
  city_slug: 'saint-petersburg',
});

const errors = ref([]);

function parseAddresses(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function validate() {
  const list = [];
  if (!form.start_address.trim()) {
    list.push('Введите начальный адрес.');
  }
  if (!form.end_address.trim()) {
    list.push('Введите конечный адрес.');
  }
  if (form.batch_size < 1 || form.batch_size > 20 || Number.isNaN(form.batch_size)) {
    list.push('Размер пакета должен быть от 1 до 20.');
  }
  if (!['duration', 'distance'].includes(form.optimization_metric)) {
    list.push('Выберите метрику оптимизации.');
  }
  const addresses = parseAddresses(form.addresses_text);
  if (addresses.length > 100) {
    list.push('Слишком много адресов для MVP. Максимум: 100.');
  }
  return list;
}

function handleSubmit() {
  errors.value = validate();
  if (errors.value.length) {
    return;
  }

  emit('submit', {
    start_address: form.start_address,
    end_address: form.end_address,
    addresses: parseAddresses(form.addresses_text),
    batch_size: Number(form.batch_size),
    optimization_metric: form.optimization_metric,
    city_slug: form.city_slug,
  });
}
</script>

<style scoped>
.route-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

fieldset {
  border: none;
  margin: 0;
  padding: 0;
}

legend {
  font-size: 1.2rem;
  margin-bottom: 12px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-weight: 600;
  color: #22303f;
}

input,
textarea,
select {
  width: 100%;
  border: 1px solid #d2dae6;
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 0.97rem;
  background: #fff;
}

textarea {
  min-height: 150px;
  resize: vertical;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.errors {
  background: #fff1f0;
  border: 1px solid #ffccd5;
  border-radius: 12px;
  padding: 14px;
  color: #92140c;
}

.errors__title {
  margin: 0 0 8px;
  font-weight: 700;
}

.primary-button {
  width: 100%;
  border: none;
  border-radius: 12px;
  padding: 14px 18px;
  background: #2f6dde;
  color: white;
  font-size: 1rem;
  cursor: pointer;
}

.primary-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .row {
    grid-template-columns: 1fr;
  }
}
</style>
