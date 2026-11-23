<script setup>
import { computed, ref, watch } from "vue";
import { finite, chartNumber } from "../utils/reportCharts.js";
const props = defineProps({
  items: { type: Array, default: () => [] },
  unit: { type: String, default: "ч" },
  label: { type: String, default: "Сравнение" },
  diverging: Boolean,
});
const emit = defineEmits(["select", "clear"]);
const selected = ref(null),
  preview = ref(null);
const active = computed(() => preview.value || selected.value);
function choose(item, event) {
  event?.currentTarget?.focus();
  selected.value = item;
  preview.value = null;
  emit("select", { ...item });
}
function clearSelection() {
  selected.value = null;
  preview.value = null;
}
function reset() {
  clearSelection();
  emit("clear");
}
defineExpose({ clearSelection, reset });
watch(() => props.items, clearSelection);
const valid = computed(() =>
  props.items.map((s, i) => ({
    ...s,
    index: i,
    value: finite(s.value),
    color: s.color || "var(--accent)",
  })),
);
const scale = computed(() =>
  Math.max(1, ...valid.value.map((s) => Math.abs(s.value || 0))),
);
const x = (s) =>
  props.diverging
    ? s.value < 0
      ? 50 - (50 * Math.abs(s.value)) / scale.value
      : 50
    : 0;
const barWidth = (s) =>
  s.value === null
    ? 0
    : (Math.abs(s.value) / scale.value) * (props.diverging ? 50 : 100);
</script>
<template>
  <div
    class="comparison-chart"
    @mouseleave="preview = null"
    :aria-label="label"
  >
    <div v-if="diverging" class="directions">
      <span>Перерасход</span><span>Освоенный объём выше затрат</span>
    </div>
    <div
      v-for="(item, i) in valid"
      :key="item.label + '-' + i"
      class="bar-row"
      :class="{
        selected: selected?.index === i,
        dimmed: selected && selected.index !== i,
      }"
      tabindex="0"
      role="button"
      :aria-pressed="selected?.index === i"
      :aria-label="`${item.label} ${chartNumber(item.value)} ${unit}`"
      @mouseenter="preview = item"
      @focus="preview = item"
      @blur="preview = null"
      @click="choose(item, $event)"
      @keydown.enter.prevent="choose(item, $event)"
      @keydown.space.prevent="choose(item, $event)"
    >
      <div class="bar-caption">
        <span>{{ item.label }}</span
        ><strong
          >{{ chartNumber(item.value)
          }}<small v-if="item.value !== null"> {{ unit }}</small></strong
        >
      </div>
      <svg
        viewBox="0 0 100 5"
        preserveAspectRatio="none"
        role="img"
        :aria-label="item.label"
      >
        <rect x="0" y="0" width="100" height="5" rx="1" class="track" />
        <rect
          v-if="item.value !== null"
          :x="x(item)"
          y="0"
          :width="barWidth(item)"
          height="5"
          rx="1"
          :fill="item.color"
        />
        <line
          v-if="diverging"
          x1="50"
          x2="50"
          y1="0"
          y2="5"
          stroke="var(--muted)"
          stroke-width=".25"
        />
        <title>
          {{ item.label }} · {{ chartNumber(item.value) }} {{ unit }}
        </title>
      </svg>
    </div>
    <div v-if="!valid.length" class="empty-bars">Нет данных для сравнения</div>
    <div class="readout" aria-live="polite">
      <template v-if="active"
        >{{ active.label }} · {{ chartNumber(active.value)
        }}{{ active.value !== null ? " " + unit : "" }}</template
      >
    </div>
  </div>
</template>
<style scoped>
.comparison-chart {
  display: grid;
  align-content: start;
  gap: 20px;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.bar-row {
  padding: 8px;
  margin: -8px;
  border: 1px solid transparent;
  border-radius: 8px;
  outline: none;
  cursor: pointer;
  transition: background-color 160ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
.bar-row:hover,
.bar-row.selected {
  background: var(--inset);
}
.bar-row.selected {
  border-color: var(--accent);
}
.bar-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.bar-row.dimmed {
  opacity: 0.65;
}
.bar-caption {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 20px;
}
.bar-caption span {
  overflow-wrap: anywhere;
}
.bar-caption strong {
  flex: none;
  font-size: 14px;
  font-weight: 500;
}
.bar-caption small {
  margin-left: 4px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 400;
}
svg {
  display: block;
  width: 100%;
  height: 8px;
  overflow: visible;
}
.track {
  fill: var(--border);
}
.directions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: var(--muted);
  font-size: 12px;
  line-height: 20px;
}
.directions span:last-child {
  text-align: right;
}
.readout {
  display: flex;
  align-items: center;
  min-height: 36px;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  line-height: 20px;
}
.empty-bars {
  display: grid;
  place-items: center;
  min-height: 208px;
  color: var(--muted);
  font-size: 14px;
}
</style>
