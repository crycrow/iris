<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import {
  axisDomain,
  finite,
  chartNumber,
  lineSegments,
} from "../utils/reportCharts.js";
const props = defineProps({
  labels: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  emptyMessage: { type: String, default: "Нет данных для построения графика" },
  integer: Boolean,
  fullLabels: { type: Array, default: () => [] },
  type: { type: String, default: "line" },
  unit: { type: String, default: "ч" },
  label: { type: String, default: "График" },
  height: { type: Number, default: 280 },
});
const emit = defineEmits(["select", "clear", "series-change"]);
const root = ref(),
  width = ref(640),
  selected = ref(null),
  preview = ref(null),
  hidden = ref([]);
const active = computed(() => preview.value ?? selected.value);
const visibleSeries = computed(() =>
  props.series.filter((s) => !hidden.value.includes(s.label)),
);
function choose(index, event) {
  event?.currentTarget?.focus();
  selected.value = index;
  preview.value = null;
  emit("select", {
    index,
    label: props.labels[index],
    fullLabel: props.fullLabels[index] || props.labels[index],
    values: visibleSeries.value.map((s) => ({
      label: s.label,
      color: s.color,
      value: finite(s.values[index]),
    })),
    unit: props.unit,
  });
}
function toggleSeries(label) {
  hidden.value = hidden.value.includes(label)
    ? hidden.value.filter((s) => s !== label)
    : [...hidden.value, label];
  emit(
    "series-change",
    visibleSeries.value.map((s) => s.label),
  );
}
function clearSelection() {
  selected.value = null;
  preview.value = null;
}
function reset() {
  clearSelection();
  hidden.value = [];
  emit("clear");
  emit(
    "series-change",
    props.series.map((s) => s.label),
  );
}
defineExpose({ clearSelection, reset });
let observer;
onMounted(() => {
  if (typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(
      (entries) => (width.value = Math.max(220, entries[0].contentRect.width)),
    );
    observer.observe(root.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());
watch(
  () => JSON.stringify([props.labels, props.fullLabels, props.series]),
  () => {
    clearSelection();
    hidden.value = hidden.value.filter((label) =>
      props.series.some((s) => s.label === label),
    );
  },
);
const domain = computed(() =>
  axisDomain(
    visibleSeries.value.flatMap((s) => s.values),
    4,
    props.integer,
  ),
);
const hasData = computed(
  () =>
    props.labels.length > 0 &&
    props.series.some((s) => s.values.some((v) => finite(v) !== null)),
);
const left = 56,
  right = 16,
  top = 24,
  bottom = 44;
const plotWidth = computed(() => Math.max(80, width.value - left - right));
const plotHeight = computed(() => props.height - top - bottom);
const band = computed(() => plotWidth.value / Math.max(1, props.labels.length));
const x = (i) => left + (i + 0.5) * band.value;
const y = (value) =>
  top +
  plotHeight.value *
    (1 - (value - domain.value.min) / (domain.value.max - domain.value.min));
const barWidth = computed(() =>
  Math.min(44, (band.value * 0.76) / Math.max(1, visibleSeries.value.length)),
);
const barX = (i, j) =>
  x(i) - (barWidth.value * visibleSeries.value.length) / 2 + j * barWidth.value;
const labelStep = computed(() =>
  Math.max(
    1,
    Math.ceil(
      props.labels.length / Math.max(2, Math.floor(plotWidth.value / 76)),
    ),
  ),
);
const showLabel = (i) =>
  i % labelStep.value === 0 || i === props.labels.length - 1;
const tooltipStyle = computed(() => {
  const i = active.value;
  if (i === null) return {};
  const points = visibleSeries.value
    .map((s) => finite(s.values[i]))
    .filter((v) => v !== null)
    .map(y);
  return {
    left: Math.max(8, Math.min(width.value - 232, x(i) - 112)) + "px",
    top:
      Math.max(
        8,
        Math.min(
          props.height - 130,
          (points.length ? Math.min(...points) : 100) - 112,
        ),
      ) + "px",
  };
});
const info = (i) =>
  `${props.fullLabels[i] || props.labels[i]}. ` +
  visibleSeries.value
    .map((s) => `${s.label} ${chartNumber(s.values[i])} ${props.unit}`)
    .join(". ");
</script>
<template>
  <div ref="root" class="trend-chart" @mouseleave="preview = null">
    <div v-if="hasData" class="chart-legend">
      <button
        type="button"
        v-for="s in series"
        :key="s.label"
        class="series-toggle"
        :aria-pressed="!hidden.includes(s.label)"
        :class="{ hidden: hidden.includes(s.label) }"
        @click="toggleSeries(s.label)"
      >
        <i :style="{ background: s.color }" />{{ s.label }}</button
      ><small>{{ unit }}</small>
    </div>
    <div class="chart-plot">
      <svg
        v-if="hasData && visibleSeries.length"
        :viewBox="`0 0 ${width} ${height}`"
        :style="{ height: height + 'px' }"
        role="group"
        :aria-label="label"
      >
        <title>{{ label }}</title>
        <g v-for="tick in domain.ticks" :key="tick" class="axis">
          <line
            :x1="left"
            :x2="width - right"
            :y1="y(tick)"
            :y2="y(tick)"
            :class="{ zero: tick === 0 }"
          />
          <text :x="left - 10" :y="y(tick) + 4" text-anchor="end">
            {{ chartNumber(tick, 2) }}
          </text>
        </g>
        <template v-if="type === 'line'">
          <g v-for="s in visibleSeries" :key="s.label">
            <polyline
              v-for="(segment, i) in lineSegments(s.values, x, y)"
              :key="i"
              :points="segment"
              fill="none"
              :stroke="s.color"
              stroke-width="2.5"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
          </g>
        </template>
        <g
          v-for="(category, i) in labels"
          :key="category + '-' + i"
          class="datum"
          :class="{ chosen: selected === i }"
          tabindex="0"
          role="button"
          :aria-pressed="selected === i"
          :aria-label="info(i) + ' Открыть подробности'"
          @mouseenter="preview = i"
          @focus="preview = i"
          @blur="preview = null"
          @click="choose(i, $event)"
          @keydown.enter.prevent="choose(i, $event)"
          @keydown.space.prevent="choose(i, $event)"
        >
          <rect
            :x="left + i * band"
            :y="top"
            :width="band"
            :height="plotHeight"
            :fill="active === i ? 'var(--chart-highlight)' : 'transparent'"
          />
          <g v-for="(s, j) in visibleSeries" :key="s.label">
            <rect
              v-if="type === 'bar' && finite(s.values[i]) !== null"
              :x="barX(i, j)"
              :y="Math.min(y(0), y(Number(s.values[i])))"
              :width="Math.max(1, barWidth - 3)"
              :height="Math.abs(y(0) - y(Number(s.values[i])))"
              rx="3"
              :fill="s.color"
            />
            <circle
              v-else-if="type === 'line' && finite(s.values[i]) !== null"
              :cx="x(i)"
              :cy="y(Number(s.values[i]))"
              :r="active === i ? 5 : 3"
              :fill="s.color"
              stroke="var(--card)"
              stroke-width="1.5"
            />
          </g>
          <text
            v-if="showLabel(i)"
            :x="x(i)"
            :y="height - 13"
            text-anchor="middle"
            class="x-label"
          >
            {{ category }}
          </text>
          <title>{{ info(i) }}</title>
        </g>
      </svg>
      <div v-else class="chart-empty">
        {{
          hasData && !visibleSeries.length
            ? "Включите ряд в легенде"
            : emptyMessage
        }}
      </div>
      <div
        v-if="hasData && visibleSeries.length && active !== null"
        class="chart-tooltip"
        :style="tooltipStyle"
        role="tooltip"
      >
        <strong>{{ fullLabels[active] || labels[active] }}</strong
        ><span v-for="s in visibleSeries" :key="s.label"
          ><i :style="{ background: s.color }" /><span>{{ s.label }}</span
          ><b
            >{{ chartNumber(s.values[active])
            }}{{ finite(s.values[active]) !== null ? " " + unit : "" }}</b
          ></span
        >
      </div>
    </div>
    <div v-if="hasData" class="chart-readout" aria-live="polite">
      <template v-if="active !== null && labels[active]"
        ><strong>{{ fullLabels[active] || labels[active] }}</strong
        ><span v-for="s in visibleSeries" :key="s.label"
          ><i :style="{ background: s.color }" />{{ s.label }}
          <b
            >{{ chartNumber(s.values[active])
            }}{{ finite(s.values[active]) !== null ? " " + unit : "" }}</b
          ></span
        ></template
      >
    </div>
  </div>
</template>
<style scoped>
.trend-chart {
  width: 100%;
  min-width: 0;
  font-variant-numeric: tabular-nums;
  --chart-highlight: color-mix(in srgb, var(--text) 4%, transparent);
}
svg {
  display: block;
  width: 100%;
  overflow: visible;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin: 0 0 16px;
  color: var(--secondary, var(--muted));
  font-size: 13px;
  line-height: 20px;
}
.chart-legend button,
.chart-readout span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.chart-legend small {
  margin-left: auto;
  font-size: 12px;
}
.chart-legend i,
.chart-readout i {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.series-toggle {
  min-height: 32px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  line-height: 20px;
  font-weight: 400;
}
.series-toggle[aria-pressed="true"] {
  background: var(--inset);
}
.series-toggle.hidden {
  color: var(--muted);
  text-decoration: line-through;
}
.series-toggle.hidden i {
  opacity: 0.4;
}
.chart-legend button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.axis line {
  stroke: var(--border);
  stroke-width: 1;
}
.axis line.zero {
  stroke: var(--muted);
  stroke-opacity: 0.4;
}
.axis text,
.x-label {
  fill: var(--muted);
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 12px;
  font-weight: 400;
}
.datum {
  outline: none;
  cursor: pointer;
}
.datum.chosen > rect {
  stroke: var(--accent);
  stroke-width: 1;
}
.datum:focus-visible > rect {
  stroke: var(--accent);
  stroke-width: 2;
  stroke-dasharray: 4 4;
}
.chart-readout {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  min-height: 44px;
  gap: 8px 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  line-height: 20px;
}
.chart-readout strong,
.chart-readout b {
  font-weight: 500;
}
.chart-empty {
  display: grid;
  place-items: center;
  min-height: 280px;
  padding: 24px;
  color: var(--muted);
  font-size: 14px;
  line-height: 20px;
  text-align: center;
}
.chart-plot {
  position: relative;
}
.chart-tooltip {
  position: absolute;
  z-index: 3;
  width: 224px;
  max-width: calc(100% - 16px);
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card);
  color: var(--text);
  box-shadow: 0 4px 16px #0000000f;
  font-size: 12px;
  line-height: 20px;
  pointer-events: none;
}
.chart-tooltip > strong {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}
.chart-tooltip > span {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}
.chart-tooltip i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.chart-tooltip b {
  white-space: nowrap;
  font-weight: 500;
}
</style>
