<template>
  <div class="address-search">
    <label class="address-search__label" :for="inputId">
      {{ label }}
      <span v-if="required" class="address-search__required">*</span>
    </label>

    <div class="address-search__control">
      <input
        :id="inputId"
        v-model="query"
        class="address-search__input"
        type="text"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        autocomplete="off"
        role="combobox"
        :aria-expanded="isDropdownOpen"
        :aria-controls="listboxId"
        :aria-activedescendant="activeDescendant"
        @input="handleInput"
        @focus="handleFocus"
        @keydown.down.prevent="moveHighlight(1)"
        @keydown.up.prevent="moveHighlight(-1)"
        @keydown.enter.prevent="selectHighlighted"
        @keydown.esc.prevent="closeDropdown"
      />

      <span v-if="isLoading" class="address-search__spinner" aria-hidden="true"></span>
      <button
        v-if="query"
        class="address-search__clear"
        type="button"
        :disabled="disabled"
        aria-label="Очистить адрес"
        @click="clearInput"
      >
        ×
      </button>
    </div>

    <div
      v-if="isDropdownOpen"
      :id="listboxId"
      class="address-search__dropdown"
      role="listbox"
    >
      <button
        v-for="(suggestion, index) in suggestions"
        :id="optionId(index)"
        :key="suggestion.id + index"
        class="address-search__option"
        :class="{
          'address-search__option--active': highlightedIndex === index,
          'address-search__option--muted': isLowConfidence(suggestion),
        }"
        type="button"
        role="option"
        :aria-selected="highlightedIndex === index"
        @mousedown.prevent="selectSuggestion(suggestion)"
        @mouseenter="highlightedIndex = index"
      >
        <span class="address-search__main">{{ suggestion.main_text || suggestion.display_name }}</span>
        <span v-if="suggestion.secondary_text" class="address-search__secondary">
          {{ suggestion.secondary_text }}
        </span>
        <span class="address-search__meta">
          <span v-if="suggestion.type">{{ suggestion.type }}</span>
          <span v-if="showConfidence && suggestion.confidence_score != null">
            Точность: {{ Math.round(suggestion.confidence_score) }}
          </span>
          <span v-if="isLowConfidence(suggestion)">Нужно проверить</span>
        </span>
      </button>

      <div v-if="!isLoading && !suggestions.length && query.length >= minLength" class="address-search__empty">
        Адреса не найдены. Проверьте написание или добавьте город/регион.
      </div>
    </div>

    <p v-if="errorMessage" class="address-search__message address-search__message--error">
      {{ errorMessage }}
    </p>
    <p v-else-if="selectedCandidate && isLowConfidence(selectedCandidate)" class="address-search__message address-search__message--warning">
      Адрес может быть неточным. Проверьте его на карте.
    </p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { suggestAddresses } from '../services/addressApi';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    required: true,
  },
  placeholder: {
    type: String,
    default: '',
  },
  role: {
    type: String,
    default: 'waypoint',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  required: {
    type: Boolean,
    default: false,
  },
  defaultCity: {
    type: String,
    default: '',
  },
  defaultRegion: {
    type: String,
    default: '',
  },
  limit: {
    type: Number,
    default: 5,
  },
  showConfidence: {
    type: Boolean,
    default: true,
  },
  mapEnabled: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits([
  'update:modelValue',
  'selected',
  'cleared',
  'error',
  'loading',
]);

const minLength = 3;
const debounceMs = 350;
const query = ref(props.modelValue || '');
const suggestions = ref([]);
const selectedCandidate = ref(null);
const isLoading = ref(false);
const errorMessage = ref('');
const highlightedIndex = ref(-1);
const isDropdownOpen = ref(false);
const searchRunId = ref(0);
let debounceTimer = null;

const inputId = computed(() => `address-search-${props.role}`);
const listboxId = computed(() => `${inputId.value}-listbox`);
const activeDescendant = computed(() => (
  highlightedIndex.value >= 0 ? optionId(highlightedIndex.value) : undefined
));

watch(
  () => props.modelValue,
  (value) => {
    if ((value || '') !== query.value) {
      query.value = value || '';
    }
  },
);

function optionId(index) {
  return `${inputId.value}-option-${index}`;
}

function isLowConfidence(candidate) {
  return Number(candidate?.confidence_score ?? 100) < 75;
}

function setLoading(value) {
  isLoading.value = value;
  emit('loading', value);
}

function closeDropdown() {
  isDropdownOpen.value = false;
  highlightedIndex.value = -1;
}

function resetSuggestions() {
  suggestions.value = [];
  closeDropdown();
}

function normalizeSearchError(error) {
  const message = String(error?.message || error || '');
  if (message.toLowerCase().includes('failed to fetch')) {
    return 'Бэкенд недоступен.';
  }
  if (message.toLowerCase().includes('temporarily unavailable')) {
    return 'Сервис поиска адресов временно недоступен.';
  }
  if (message.toLowerCase().includes('at least 3')) {
    return '';
  }
  return message || 'Сервис поиска адресов временно недоступен.';
}

function scheduleSearch(value) {
  window.clearTimeout(debounceTimer);
  errorMessage.value = '';

  if (value.trim().length < minLength) {
    setLoading(false);
    resetSuggestions();
    return;
  }

  debounceTimer = window.setTimeout(() => {
    runSearch(value.trim());
  }, debounceMs);
}

async function runSearch(value) {
  const runId = searchRunId.value + 1;
  searchRunId.value = runId;
  setLoading(true);

  try {
    const response = await suggestAddresses(value, {
      limit: props.limit,
      contextCity: props.defaultCity || undefined,
      contextRegion: props.defaultRegion || undefined,
    });

    if (searchRunId.value !== runId) {
      return;
    }

    suggestions.value = response.items || [];
    highlightedIndex.value = suggestions.value.length ? 0 : -1;
    isDropdownOpen.value = true;
  } catch (error) {
    if (searchRunId.value !== runId) {
      return;
    }

    const message = normalizeSearchError(error);
    errorMessage.value = message;
    suggestions.value = [];
    isDropdownOpen.value = Boolean(message);
    emit('error', message);
  } finally {
    if (searchRunId.value === runId) {
      setLoading(false);
    }
  }
}

function handleInput() {
  emit('update:modelValue', query.value);

  if (
    selectedCandidate.value
    && query.value !== selectedCandidate.value.display_name
  ) {
    selectedCandidate.value = null;
    emit('cleared');
  }

  scheduleSearch(query.value);
}

function handleFocus() {
  if (suggestions.value.length) {
    isDropdownOpen.value = true;
  }
}

function moveHighlight(delta) {
  if (!suggestions.value.length) {
    return;
  }
  isDropdownOpen.value = true;
  const next = highlightedIndex.value + delta;
  highlightedIndex.value = (next + suggestions.value.length) % suggestions.value.length;
}

function selectHighlighted() {
  if (!isDropdownOpen.value || highlightedIndex.value < 0) {
    return;
  }
  selectSuggestion(suggestions.value[highlightedIndex.value]);
}

function selectSuggestion(suggestion) {
  const originalQuery = query.value;
  selectedCandidate.value = suggestion;
  query.value = suggestion.display_name;
  emit('update:modelValue', suggestion.display_name);
  emit('selected', {
    ...suggestion,
    original_query: originalQuery,
    role: props.role,
  });
  closeDropdown();
}

function clearInput() {
  window.clearTimeout(debounceTimer);
  query.value = '';
  selectedCandidate.value = null;
  suggestions.value = [];
  errorMessage.value = '';
  emit('update:modelValue', '');
  emit('cleared');
  setLoading(false);
  closeDropdown();
}
</script>

<style scoped>
.address-search {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.address-search__label {
  display: flex;
  flex-direction: row;
  gap: 4px;
  color: #22303f;
  font-weight: 600;
}

.address-search__required {
  color: #dc2626;
}

.address-search__control {
  position: relative;
}

.address-search__input {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #d2dae6;
  border-radius: 8px;
  padding: 10px 42px 10px 12px;
  font-size: 0.97rem;
  background: #fff;
}

.address-search__clear {
  position: absolute;
  top: 50%;
  right: 8px;
  width: 28px;
  height: 28px;
  transform: translateY(-50%);
  border: none;
  border-radius: 50%;
  background: #e5eaf3;
  color: #334155;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.address-search__spinner {
  position: absolute;
  top: 50%;
  right: 42px;
  width: 16px;
  height: 16px;
  margin-top: -8px;
  border: 2px solid #cbd5e1;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: address-search-spin 0.8s linear infinite;
}

.address-search__dropdown {
  position: absolute;
  z-index: 1000;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.16);
}

.address-search__option {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 3px;
  border: none;
  border-bottom: 1px solid #eef2f7;
  padding: 10px 12px;
  background: #fff;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
}

.address-search__option:last-child {
  border-bottom: none;
}

.address-search__option--active {
  background: #edf4ff;
}

.address-search__option--muted {
  color: #475569;
}

.address-search__main {
  font-weight: 700;
}

.address-search__secondary,
.address-search__meta {
  color: #64748b;
  font-size: 0.84rem;
}

.address-search__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.address-search__empty {
  padding: 12px;
  color: #475569;
}

.address-search__message {
  margin: 0;
  font-size: 0.88rem;
}

.address-search__message--error {
  color: #b91c1c;
}

.address-search__message--warning {
  color: #92400e;
}

@keyframes address-search-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
