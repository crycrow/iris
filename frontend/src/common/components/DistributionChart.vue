<script setup>
import { computed, ref, watch } from "vue";
import { finite, chartNumber } from "../utils/reportCharts.js";
const props = defineProps({
  items: { type: Array, default: () => [] },
  label: { type: String, default: "Распределение" },
  unit: { type: String, default: "всего" },
});
const emit = defineEmits(["select", "clear"]);
const selected = ref(null),
  preview = ref(null),
  circumference = 2 * Math.PI * 78;
const values = computed(() =>
  props.items.map((s, i) => ({
    ...s,
    index: i,
    value: Math.max(0, finite(s.value) || 0),
    color: s.color || ["var(--accent)", "var(--secondary)", "var(--muted)", "var(--border)"][i % 4],
  })),
);
const total = computed(() => values.value.reduce((sum, s) => sum + s.value, 0));
const segments = computed(() => {
  let offset = 0;
  return values.value.map((s) => {
    const length = total.value ? (s.value / total.value) * circumference : 0;
    const row = { ...s, length, offset };
    offset += length;
    return row;
  });
});
const active = computed(() => preview.value || selected.value);
function choose(item, event) {
  event?.currentTarget?.focus();
  selected.value = item;
  preview.value = null;
  emit("select", {
    ...item,
    percentage: total.value ? (item.value / total.value) * 100 : 0,
    total: total.value,
  });
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
</script>
<template>
  <div class="distribution-chart" @mouseleave="preview = null">
    <div class="ring">
      <svg viewBox="0 0 220 220" role="group" :aria-label="label">
        <title>{{ label }}</title>
        <circle
          cx="110"
          cy="110"
          r="78"
          class="track"
          fill="none"
          stroke-width="25"
        />
        <circle
          v-for="(s, i) in segments.filter((s) => s.value > 0)"
          :key="s.label"
          cx="110"
          cy="110"
          r="78"
          fill="none"
          stroke-width="25"
          :stroke="s.color"
          :stroke-dasharray="`${s.length} ${circumference - s.length}`"
          :stroke-dashoffset="-s.offset"
          transform="rotate(-90 110 110)"
          tabindex="0"
          role="button"
          :class="{
            chosen: active?.index === s.index,
            dimmed: selected && selected.index !== s.index,
          }"
          :aria-pressed="selected?.index === s.index"
          :aria-label="`${s.label} ${chartNumber(s.value)} (${chartNumber((s.value / total) * 100)} %)`"
          @mouseenter="preview = s"
          @focus="preview = s"
          @blur="preview = null"
          @click="choose(s, $event)"
          @keydown.enter.prevent="choose(s, $event)"
          @keydown.space.prevent="choose(s, $event)"
        >
          <title>
            {{ s.label }} · {{ chartNumber(s.value) }} ·
            {{ chartNumber((s.value / total) * 100) }} %
          </title>
        </circle>
        <text x="110" y="109" text-anchor="middle" class="total">
          {{ chartNumber(total, 0) }}
        </text>
        <text x="110" y="132" text-anchor="middle" class="unit">
          {{ unit }}
        </text>

      </svg>
      <div v-if="active" class="ring-tooltip" role="tooltip">
        <i :style="{ background: active.color }" />{{ active.label }}
        <b
          >{{ chartNumber(active.value) }} ·
          {{ total ? chartNumber((active.value / total) * 100) : 0 }} %</b
        >
      </div>
    </div>
    <div class="legend">
      <button
        type="button"
        v-for="s in values"
        :key="s.label"
        :class="{ selected: selected?.index === s.index }"
        :aria-pressed="selected?.index === s.index"
        @click="choose(s, $event)"
        @focus="preview = s"
        @blur="preview = null"
      >
        <i :style="{ background: s.color }" /><span>{{ s.label }}</span
        ><strong>{{ chartNumber(s.value, 0) }}</strong
        ><small
          >{{ total ? chartNumber((s.value / total) * 100, 0) : 0 }} %</small
        >
      </button>
    </div>
    <div class="readout" aria-live="polite">
      <template v-if="active"
        >{{ active.label }} · {{ chartNumber(active.value, 0) }} ·
        {{ total ? chartNumber((active.value / total) * 100) : 0 }} %</template
      ><template v-else-if="!total">Пока нет данных для распределения</template>
    </div>
  </div>
</template>
<style scoped>
.distribution-chart {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.ring {
  position: relative;
  flex: 1 1 144px;
  max-width: 208px;
  margin: auto;
}
.ring svg {
  display: block;
  width: 100%;
}
.track {
  stroke: var(--border);
}
.total {
  font-size: 36px;
  font-weight: 500;
  fill: var(--text);
}
.unit {
  font-size: 18px;
  fill: var(--muted);
}
circle[role="button"] {
  cursor: pointer;
  transition: opacity 160ms cubic-bezier(0.22, 1, 0.36, 1);
}
circle[role="button"]:focus-visible {
  outline: none;
  stroke-width: 32;
}
.ring circle.chosen {
  stroke-width: 28;
}
.ring circle.dimmed {
  opacity: 0.45;
}
.legend {
  display: grid;
  flex: 1 1 232px;
  gap: 4px;
  align-content: center;
  min-width: 0;
}
.legend button {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) 40px 40px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  min-height: 36px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  font-size: 13px;
  line-height: 20px;
  font-weight: 400;
  text-align: left;
}
.legend button:hover,
.legend button.selected {
  background: var(--inset);
}
.legend button.selected {
  border-color: var(--border);
}
.legend button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.legend i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.legend span {
  overflow-wrap: anywhere;
}
.legend strong,
.legend small {
  text-align: right;
  font-size: 12px;
  font-weight: 400;
}
.legend small {
  color: var(--muted);
}
.readout {
  display: flex;
  flex: 1 0 100%;
  align-items: center;
  min-height: 36px;
  gap: 12px;
  padding-top: 12px;
  margin: 0;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  line-height: 20px;
}
.ring-tooltip {
  position: absolute;
  top: 0;
  left: 50%;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  width: max-content;
  max-width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--text);
  box-shadow: 0 4px 16px #0000000f;
  font-size: 12px;
  line-height: 20px;
  transform: translateX(-50%);
  pointer-events: none;
}
.ring-tooltip i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.ring-tooltip b {
  white-space: nowrap;
  font-weight: 500;
}
@media (max-width: 640px) {
  .ring {
    max-width: 192px;
  }
}
</style>

