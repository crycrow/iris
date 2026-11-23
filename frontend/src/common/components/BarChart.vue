<script setup>
import { ref, computed, watch } from "vue";
import { number } from "../utils/format.js";
const props = defineProps({
  items: { type: Array, default: () => [] },
  label: { type: String, default: "Показатели" },
});
const selected = ref(null);
const max = computed(() =>
  Math.max(1, ...props.items.map((x) => Number(x.value) || 0)),
);
watch(() => props.items, () => (selected.value = null));
</script>
<template>
  <div class="chart" role="group" :aria-label="label">
    <button
      v-for="item in items"
      :key="item.label"
      type="button"
      class="bar-row"
      :class="{ selected: selected === item }"
      :aria-pressed="selected === item"
      :aria-label="`${item.label} ${number(item.value)}`"
      @click="selected = item"
      @focus="selected = item"
      @mouseenter="selected = item"
    >
      <span class="bar-caption">
        <span>{{ item.label }}</span><strong>{{ number(item.value) }}</strong>
      </span>
      <span class="bar-track" aria-hidden="true">
        <span
          :style="{
            width: Math.max(0, (Number(item.value) / max) * 100) + '%',
            background: item.color || 'var(--accent)',
          }"
        />
      </span>
    </button>
    <p v-if="selected" class="readout" role="status">
      {{ selected.label }} · {{ number(selected.value) }}
    </p>
  </div>
</template>
<style scoped>
.chart {
  display: grid;
  gap: 16px;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.bar-row {
  display: grid;
  gap: 8px;
  width: 100%;
  min-width: 0;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  text-align: left;
}
.bar-row:hover,
.bar-row.selected {
  background: var(--inset);
}
.bar-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.bar-caption {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
  font-size: 14px;
  line-height: 20px;
  font-weight: 400;
}
.bar-caption > span {
  overflow-wrap: anywhere;
}
.bar-caption strong {
  flex: none;
  font-size: 14px;
  font-weight: 500;
}
.bar-track {
  height: 8px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--border);
}
.bar-track > span {
  display: block;
  height: 100%;
  border-radius: 4px;
}
.readout {
  margin: 0;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  line-height: 20px;
}
@media print {
  .bar-row {
    display: grid !important;
    break-inside: avoid;
  }
}
</style>
