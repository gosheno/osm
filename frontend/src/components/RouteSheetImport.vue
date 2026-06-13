<template>
  <section class="route-import">
    <div class="route-import__header">
      <div>
        <h2>Импорт маршрутного листа</h2>
        <p>Загрузите фото печатных маршрутных листов, проверьте распознанные адреса и постройте маршрут.</p>
      </div>
      <button type="button" class="ghost-button" :disabled="busy" @click="loadSample">
        Загрузить sample
      </button>
    </div>

    <div class="upload-panel">
      <label class="upload-panel__drop">
        <input
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
          :disabled="busy"
          @change="handleFileChange"
        />
        <span>Выбрать фото маршрутных листов</span>
      </label>
      <button type="button" class="primary-button" :disabled="busy || !selectedFiles.length" @click="uploadFiles">
        Распознать
      </button>
    </div>

    <div v-if="selectedFiles.length" class="file-list">
      <span v-for="file in selectedFiles" :key="file.name + file.size">{{ file.name }}</span>
    </div>

    <p v-if="progressMessage" class="route-import__progress">{{ progressMessage }}</p>
    <p v-if="errorMessage" class="route-import__error">{{ errorMessage }}</p>

    <div v-if="routeImport" class="import-summary">
      <span>Import #{{ routeImport.import_id }}</span>
      <span :class="['status-pill', `status-pill--${routeImport.status}`]">{{ importStatusText(routeImport.status) }}</span>
      <span>Строк: {{ routeImport.items.length }}</span>
      <span>Готово: {{ readyItems.length }}</span>
      <span>На проверку: {{ reviewItems.length }}</span>
    </div>

    <div v-if="routeImport?.images?.length" class="image-strip">
      <div v-for="image in routeImport.images" :key="image.id" class="image-strip__item">
        <span>{{ image.original_filename }}</span>
        <small>{{ image.ocr_status }}</small>
        <small v-if="image.error_message">{{ image.error_message }}</small>
      </div>
    </div>

    <div v-if="routeImport?.items?.length" class="review-area">
      <div class="review-toolbar">
        <div>
          <strong>Проверка OCR-строк</strong>
          <span>OCR считается черновиком: подтвердите, исправьте или исключите строки.</span>
        </div>
        <label class="inline-toggle">
          <input v-model="excludeProblematic" type="checkbox" />
          <span>Строить только по готовым строкам</span>
        </label>
      </div>

      <div class="review-table-wrap">
        <table class="review-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Статус</th>
              <th>Магазин</th>
              <th>Адрес</th>
              <th>Нормализованный адрес</th>
              <th>Точность</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in routeImport.items" :key="item.id" :class="`review-table__row--${itemStatusKind(item)}`">
              <td>{{ item.row_number }}</td>
              <td>
                <span :class="['status-pill', `status-pill--${itemStatusKind(item)}`]">
                  {{ itemStatusText(item) }}
                </span>
              </td>
              <td>
                <input v-model="item.store_name" type="text" />
              </td>
              <td>
                <textarea v-model="item.address" rows="2"></textarea>
                <small v-if="item.raw_ocr_text">OCR: {{ item.raw_ocr_text }}</small>
              </td>
              <td>{{ item.normalized_address || "-" }}</td>
              <td>{{ formatConfidence(item.confidence_score) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" :disabled="busy" @click="saveItem(item)">Сохранить</button>
                  <button type="button" :disabled="busy" @click="retryItem(item)">Геокодировать</button>
                  <button type="button" :disabled="busy" @click="confirmItem(item)">Подтвердить</button>
                  <button type="button" :disabled="busy" @click="rejectItem(item)">Исключить</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="route-build-panel">
        <label>
          Начальный адрес
          <input v-model.trim="buildForm.start_address" type="text" placeholder="Санкт-Петербург, Дворцовая площадь" />
        </label>
        <label>
          Конечный адрес
          <input v-model.trim="buildForm.end_address" type="text" placeholder="Санкт-Петербург, Московский вокзал" />
        </label>
        <label>
          Размер пакета
          <input v-model.number="buildForm.batch_size" type="number" min="1" max="20" />
        </label>
        <button type="button" class="primary-button" :disabled="busy || !buildableItems.length" @click="buildRoute">
          Построить маршрут из OCR
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import {
  confirmRouteImport,
  getRouteImport,
  importLocalRouteSheet,
  patchRouteImportItem,
  retryRouteImportItem,
  uploadRouteSheet,
} from '../services/routeImportsApi';

const emit = defineEmits(['route-created']);

const busy = ref(false);
const selectedFiles = ref([]);
const routeImport = ref(null);
const errorMessage = ref('');
const progressMessage = ref('');
const excludeProblematic = ref(false);
const buildForm = reactive({
  start_address: 'Санкт-Петербург, Дворцовая площадь',
  end_address: 'Санкт-Петербург, Московский вокзал',
  batch_size: 15,
});

const readyItems = computed(() => (
  (routeImport.value?.items || []).filter((item) => itemStatusKind(item) === 'ready')
));
const reviewItems = computed(() => (
  (routeImport.value?.items || []).filter((item) => ['review', 'failed', 'duplicate'].includes(itemStatusKind(item)))
));
const buildableItems = computed(() => (
  (routeImport.value?.items || []).filter((item) => (
    item.address_id
    && item.geocoding_status === 'found'
    && !['rejected', 'duplicate'].includes(item.status)
  ))
));

function handleFileChange(event) {
  selectedFiles.value = Array.from(event.target.files || []);
  errorMessage.value = '';
}

async function uploadFiles() {
  await runImportTask('Загружаем изображения...', async () => {
    const created = await uploadRouteSheet(selectedFiles.value);
    routeImport.value = await getRouteImport(created.import_id);
  });
}

async function loadSample() {
  await runImportTask('Загружаем sample-файлы из data/routes...', async () => {
    routeImport.value = await importLocalRouteSheet('route22');
  });
}

async function saveItem(item) {
  await runImportTask('Сохраняем строку...', async () => {
    routeImport.value = await patchRouteImportItem(routeImport.value.import_id, item.id, {
      store_name: item.store_name,
      address: item.address,
      status: item.status,
    });
  });
}

async function retryItem(item) {
  await runImportTask('Повторяем геокодирование...', async () => {
    routeImport.value = await retryRouteImportItem(routeImport.value.import_id, item.id);
  });
}

async function confirmItem(item) {
  await runImportTask('Подтверждаем строку...', async () => {
    routeImport.value = await patchRouteImportItem(routeImport.value.import_id, item.id, {
      store_name: item.store_name,
      address: item.address,
      status: 'confirmed',
    });
  });
}

async function rejectItem(item) {
  await runImportTask('Исключаем строку...', async () => {
    routeImport.value = await patchRouteImportItem(routeImport.value.import_id, item.id, {
      status: 'rejected',
    });
  });
}

async function buildRoute() {
  if (!buildForm.start_address || !buildForm.end_address) {
    errorMessage.value = 'Укажите начальный и конечный адрес.';
    return;
  }

  await runImportTask('Строим маршрут из подтвержденных строк...', async () => {
    const response = await confirmRouteImport(routeImport.value.import_id, {
      start_address: buildForm.start_address,
      end_address: buildForm.end_address,
      batch_size: Number(buildForm.batch_size),
      include_item_ids: buildableItems.value.map((item) => item.id),
      exclude_problematic: excludeProblematic.value,
    });
    if (response.route) {
      emit('route-created', response.route);
    }
    routeImport.value = await getRouteImport(routeImport.value.import_id);
  });
}

async function runImportTask(message, task) {
  busy.value = true;
  progressMessage.value = message;
  errorMessage.value = '';
  try {
    await task();
  } catch (error) {
    errorMessage.value = String(error?.message || error || 'Не удалось выполнить действие.');
  } finally {
    busy.value = false;
    progressMessage.value = '';
  }
}

function itemStatusKind(item) {
  if (item.status === 'rejected') {
    return 'rejected';
  }
  if (item.status === 'duplicate') {
    return 'duplicate';
  }
  if (item.geocoding_status === 'found' && item.address_id) {
    return 'ready';
  }
  if (['not_found', 'error'].includes(item.geocoding_status)) {
    return 'failed';
  }
  return 'review';
}

function itemStatusText(item) {
  const kind = itemStatusKind(item);
  if (kind === 'ready') return 'Готово';
  if (kind === 'duplicate') return 'Дубликат';
  if (kind === 'failed') return 'Не найден';
  if (kind === 'rejected') return 'Исключено';
  return 'Проверить';
}

function importStatusText(status) {
  const labels = {
    uploaded: 'Загружено',
    processing: 'Обработка',
    completed: 'Готово к проверке',
    failed: 'Ошибка',
    confirmed: 'Маршрут создан',
  };
  return labels[status] || status;
}

function formatConfidence(value) {
  if (value == null) {
    return '-';
  }
  return `${Math.round(Number(value) * 100)}%`;
}
</script>

<style scoped>
.route-import {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 20px 0;
  padding-top: 18px;
  border-top: 1px solid #dbe5f7;
}

.route-import__header,
.upload-panel,
.review-toolbar,
.route-build-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.route-import h2 {
  margin: 0 0 6px;
  font-size: 1.25rem;
}

.route-import p {
  margin: 0;
  color: #475569;
}

.upload-panel__drop {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border: 1px dashed #93b4e8;
  border-radius: 8px;
  padding: 12px;
  color: #1a3d7c;
  font-weight: 700;
  cursor: pointer;
}

.upload-panel__drop input {
  max-width: 220px;
}

.primary-button,
.ghost-button,
.row-actions button {
  border: 1px solid #bfd0ef;
  border-radius: 8px;
  padding: 9px 12px;
  background: #ffffff;
  color: #1a3d7c;
  font-weight: 700;
  cursor: pointer;
}

.primary-button {
  border-color: #2f6dde;
  background: #2f6dde;
  color: #fff;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.file-list,
.import-summary,
.image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.file-list span,
.image-strip__item {
  border: 1px solid #dbe5f7;
  border-radius: 8px;
  padding: 8px 10px;
  background: #f8fbff;
}

.image-strip__item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.route-import__progress {
  padding: 10px 12px;
  border-radius: 8px;
  background: #f4f8ff;
}

.route-import__error {
  padding: 10px 12px;
  border: 1px solid #ffccd5;
  border-radius: 8px;
  background: #fff1f0;
  color: #92140c;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 3px 8px;
  background: #e2e8f0;
  color: #334155;
  font-size: 0.82rem;
  font-weight: 800;
}

.status-pill--ready,
.status-pill--completed,
.status-pill--confirmed {
  background: #dcfce7;
  color: #166534;
}

.status-pill--review,
.status-pill--processing {
  background: #fef3c7;
  color: #92400e;
}

.status-pill--failed,
.status-pill--failed {
  background: #fee2e2;
  color: #991b1b;
}

.status-pill--duplicate {
  background: #e0e7ff;
  color: #3730a3;
}

.status-pill--rejected {
  background: #e5e7eb;
  color: #4b5563;
}

.review-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-toolbar > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.inline-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
}

.review-table-wrap {
  overflow-x: auto;
}

.review-table {
  width: 100%;
  min-width: 920px;
  border-collapse: collapse;
}

.review-table th,
.review-table td {
  border-bottom: 1px solid #e2e8f0;
  padding: 8px;
  vertical-align: top;
  text-align: left;
}

.review-table th {
  background: #f8fbff;
  color: #22303f;
  font-size: 0.86rem;
}

.review-table input,
.review-table textarea,
.route-build-panel input {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #d2dae6;
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}

.review-table textarea {
  min-width: 220px;
  resize: vertical;
}

.review-table small {
  display: block;
  margin-top: 5px;
  color: #64748b;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.route-build-panel {
  align-items: end;
  padding-top: 10px;
}

.route-build-panel label {
  display: flex;
  min-width: 180px;
  flex: 1 1 180px;
  flex-direction: column;
  gap: 5px;
  color: #22303f;
  font-weight: 700;
}

@media (max-width: 760px) {
  .route-import__header,
  .upload-panel,
  .review-toolbar,
  .route-build-panel {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
