<script setup>
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import RiskBadge from "../../../common/components/RiskBadge.vue";
import UiIcon from "../../../common/components/UiIcon.vue";
import Gantt from "frappe-gantt";
import "frappe-gantt-style";
import { date, today, taskStatuses } from "../../../common/utils/format.js";
import {
  buildGanttRows,
  ganttRange,
  fitGantt,
  dayNumber,
  canDragGanttRow,
} from "../ganttLayout.js";
const props = defineProps({
  tasks: { type: Array, default: () => [] },
  editable: Boolean,
  indicators: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["open", "dates", "progress"]);
const host = ref();
const panel = ref();
const labels = ref();
const mode = ref("fit");
const includeToday = ref(true);
const activeRow = ref(null);
const selectedRow = ref(null);
const fullscreen = ref(false);
const fullscreenAvailable =
  typeof document !== "undefined" && document.fullscreenEnabled;
const screenHeight = ref(
  typeof window !== "undefined" ? window.innerHeight : 900,
);
const canScrollBack = ref(false);
const canScrollForward = ref(false);
const rows = computed(() => buildGanttRows(props.tasks));
const range = computed(() =>
  ganttRange(rows.value, includeToday.value ? today() : undefined),
);
const missingDates = computed(
  () =>
    props.tasks.filter((task) => task.status !== "cancelled").length -
    rows.value.length,
);
const rowHeight = 104;
const headerHeight = 76;
const viewportHeight = computed(() =>
  Math.min(
    fullscreen.value ? Math.max(300, screenHeight.value - 215) : 590,
    headerHeight + rows.value.length * rowHeight + 22,
  ),
);
const taskCount = computed(
  () => rows.value.filter((row) => !row.summary && !row.milestone).length,
);
const milestoneCount = computed(
  () => rows.value.filter((row) => row.milestone).length,
);
const statusLegend = computed(() => [
  ...new Set(
    rows.value
      .filter((row) => !row.summary && !row.milestone)
      .map((row) => row.status),
  ),
]);
const rowById = computed(() => new Map(rows.value.map((row) => [row.id, row])));
const calendarMonths = new Intl.DateTimeFormat("ru-RU", {
  month: "long",
  year: "numeric",
});
const shortDate = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
});
const monthOnly = new Intl.DateTimeFormat("ru-RU", { month: "long" });
let chart;
let observer;
let frame;
let lastWidth = 0;
let scrollTarget = "start";
let unmounted = false;
let pointerStart;
let pointerMoved = false;

function upperMonth(day, previous) {
  return !previous ||
    day.getMonth() !== previous.getMonth() ||
    day.getFullYear() !== previous.getFullYear()
    ? calendarMonths.format(day)
    : "";
}
function currentMode(width) {
  const padding = [`${range.value.before}d`, `${range.value.after}d`];
  const base = {
    padding,
    date_format: "YYYY-MM-DD",
    upper_text: upperMonth,
    thick_line: (day) => day.getDate() === 1,
    snap_at: "1d",
  };
  if (mode.value === "fit") {
    const fit = fitGantt(range.value, width);
    const calendarStart = dayNumber(range.value.start) - 2;
    const monthsPerLabel = Math.max(
      1,
      Math.ceil((width < 500 ? 50 : 110) / (30 * fit.columnWidth)),
    );
    const monthFormat = new Intl.DateTimeFormat("ru-RU", {
      month: width < 500 ? "short" : "long",
      ...(width >= 700 ? { year: "numeric" } : {}),
    });
    const monthGroup = (day) =>
      Math.floor((day.getFullYear() * 12 + day.getMonth()) / monthsPerLabel) *
      monthsPerLabel;
    const dayIndex = (day) =>
      Math.round(
        Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()) / 86400000,
      ) - calendarStart;
    return {
      ...base,
      name: "Overview",
      step: "1d",
      column_width: fit.columnWidth,
      lower_text: (day) =>
        dayIndex(day) % fit.labelEveryDays === 0 &&
        dayIndex(day) * fit.columnWidth <= width - 50
          ? shortDate.format(day)
          : "",
      upper_text: (day, previous) => {
        const group = monthGroup(day);
        return previous && monthGroup(previous) === group
          ? ""
          : monthFormat.format(new Date(Math.floor(group / 12), group % 12, 1));
      },
      thick_line: (day) => dayIndex(day) % fit.labelEveryDays === 0,
    };
  }
  if (mode.value === "day")
    return {
      ...base,
      name: "Days",
      step: "1d",
      column_width: 44,
      lower_text: (day) =>
        `${day.getDate()} ${["вс", "пн", "вт", "ср", "чт", "пт", "сб"][day.getDay()]}`,
      thick_line: (day) => day.getDay() === 1,
    };
  if (mode.value === "week")
    return {
      ...base,
      name: "Weeks",
      step: "7d",
      column_width: 112,
      lower_text: (day) => shortDate.format(day),
    };

  return {
    ...base,
    name: "Months",
    step: "1d",
    column_width: 6,
    lower_text: (day, previous) =>
      (!previous && day.getDate() <= 15) || day.getDate() === 1
        ? monthOnly.format(day)
        : "",
    upper_text: (day, previous) =>
      !previous || day.getFullYear() !== previous.getFullYear()
        ? String(day.getFullYear())
        : "",
  };
}
async function openRow(row) {
  if (row) {
    selectedRow.value = row.id;
    host.value
      ?.querySelectorAll(".bar-wrapper")
      .forEach((bar) =>
        bar.classList.toggle(
          "row-selected",
          bar.getAttribute("data-id") === row.id,
        ),
      );
    if (document.fullscreenElement === panel.value)
      await document.exitFullscreen();
    emit("open", row.task);
  }
}
function updateScrollState() {
  if (!chart) return;
  canScrollBack.value = chart.$container.scrollLeft > 2;
  canScrollForward.value =
    chart.$container.scrollLeft + chart.$container.clientWidth <
    chart.$container.scrollWidth - 2;
}
function panCalendar(direction) {
  chart?.$container.scrollBy({
    left: direction * chart.$container.clientWidth * 0.75,
    behavior: "smooth",
  });
}
async function toggleFullscreen() {
  if (document.fullscreenElement === panel.value)
    await document.exitFullscreen();
  else await panel.value.requestFullscreen();
}
function fullscreenChanged() {
  fullscreen.value = document.fullscreenElement === panel.value;
  screenHeight.value = window.innerHeight;
  scheduleRender();
}
function guardDrag(event) {
  pointerStart = { x: event.clientX, y: event.clientY };
  pointerMoved = false;
  const id = event.target.closest?.(".bar-wrapper")?.getAttribute("data-id");
  if (id && !canDragGanttRow(rowById.value.get(id), props.editable))
    event.stopPropagation();
}
function trackPointer(event) {
  if (
    pointerStart &&
    event.buttons &&
    Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) >
      4
  )
    pointerMoved = true;
}
function syncLabels(event) {
  if (labels.value && labels.value.scrollTop !== event.target.scrollTop)
    labels.value.scrollTop = event.target.scrollTop;
  updateScrollState();
}
function syncCalendar(event) {
  if (chart && chart.$container.scrollTop !== event.target.scrollTop)
    chart.$container.scrollTop = event.target.scrollTop;
}
function highlightRow(id) {
  activeRow.value = id;
  host.value
    ?.querySelectorAll(".bar-wrapper")
    .forEach((bar) =>
      bar.classList.toggle("row-hover", bar.getAttribute("data-id") === id),
    );
}
function decorateBars() {
  host.value
    .querySelectorAll("animate")
    .forEach((animation) => animation.remove());
  const headings = [...chart.$container.querySelectorAll(".upper-text")];
  if (
    headings.length > 1 &&
    parseFloat(headings[1].style.left) - parseFloat(headings[0].style.left) <
      headings[0].clientWidth + 12
  ) {
    headings[0].style.visibility = "hidden";
  }
  for (const bar of chart.bars) {
    const row = rowById.value.get(bar.task.id);
    if (!row) continue;
    bar.group.classList.toggle("summary", row.summary);
    bar.group.classList.toggle(
      "has-risk",
      Boolean(props.indicators[row.task.task_id]?.length),
    );
    bar.group.classList.toggle("milestone", row.milestone);
    bar.group.classList.toggle("row-selected", selectedRow.value === row.id);
    const title = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "title",
    );
    title.textContent = `${row.wbs} ${row.name}\n${date(row.start)} → ${date(row.end)}\n${taskStatuses[row.status]} · ${row.progress}%`;
    bar.group.prepend(title);
    bar.group.setAttribute("role", "button");
    bar.group.setAttribute("tabindex", "0");
    bar.group.setAttribute(
      "aria-label",
      title.textContent.replaceAll("\n", ". "),
    );
    bar.group.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        openRow(row);
      }
    });
    bar.group.addEventListener("mouseenter", () => highlightRow(row.id));
    bar.group.addEventListener("mouseleave", () => highlightRow(null));
    if (!canDragGanttRow(row, props.editable))
      bar.group
        .querySelectorAll(".handle")
        .forEach((handle) => handle.remove());
    const label = bar.group.querySelector(".bar-label");
    if (label) {
      label.textContent = row.milestone ? "" : `${row.progress}%`;
      label.classList.remove("big");
      label.setAttribute(
        "x",
        Number(bar.$bar.getAttribute("x")) +
          Number(bar.$bar.getAttribute("width")) / 2,
      );
      label.style.display =
        Number(bar.$bar.getAttribute("width")) < 44 ? "none" : "";
    }
    if (row.milestone) {
      const point =
        Number(bar.$bar.getAttribute("x")) +
        Math.min(8, Number(bar.$bar.getAttribute("width")) / 2);
      const x = Math.max(
        10,
        Math.min(point, chart.dates.length * chart.config.column_width - 10),
      );
      const y = Number(bar.$bar.getAttribute("y")) + 15;
      const marker = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "polygon",
      );
      marker.setAttribute(
        "points",
        `${x},${y - 9} ${x + 9},${y} ${x},${y + 9} ${x - 9},${y}`,
      );
      marker.setAttribute("class", "milestone-diamond");
      bar.bar_group.append(marker);
    }
  }

  chart.$container
    .querySelectorAll(
      ".current-highlight, .current-ball-highlight, .gantt-today-line",
    )
    .forEach((node) => node.remove());
  const localStart = `${chart.gantt_start.getFullYear()}-${String(chart.gantt_start.getMonth() + 1).padStart(2, "0")}-${String(chart.gantt_start.getDate()).padStart(2, "0")}`;
  const offset =
    ((dayNumber(today()) - dayNumber(localStart) + 0.5) / chart.config.step) *
    chart.config.column_width;
  if (offset >= 0 && offset <= chart.dates.length * chart.config.column_width) {
    const marker = document.createElement("div");
    marker.className = "gantt-today-line";
    marker.style.cssText = `left:${offset}px;top:${headerHeight}px;height:${rows.value.length * rowHeight}px`;
    marker.setAttribute("title", `Сегодня ${date(today())}`);
    const caption = document.createElement("span");
    caption.textContent = "Сегодня";
    marker.append(caption);
    chart.$container.append(marker);
  }
}
async function render() {
  await nextTick();
  if (unmounted || !host.value || !rows.value.length) return;
  const width = Math.max(120, host.value.clientWidth - 16);
  const view = currentMode(width);
  const scrollTop = chart?.$container.scrollTop || 0;
  const scrollLeft = chart?.$container.scrollLeft || 0;
  const options = {
    view_modes: [view],
    view_mode: view.name,
    language: "ru",
    today_button: false,
    infinite_padding: false,
    scroll_to: "start",
    container_height: viewportHeight.value,
    upper_header_height: 36,
    lower_header_height: 30,
    bar_height: 30,
    padding: rowHeight - 30,
    column_width: view.column_width,
    bar_corner_radius: 12,
    snap_at: "1d",
    move_dependencies: false,
    readonly: !props.editable,
    readonly_dates: !props.editable,
    readonly_progress: !props.editable,
    holidays:
      mode.value === "day"
        ? { "var(--g-weekend-highlight-color)": "weekend" }
        : {},
    popup: false,
    on_click: (task) => {
      if (!pointerMoved && !chart?.bar_being_dragged)
        openRow(rowById.value.get(task.id));
    },
    on_date_change: (task, start, end) => {
      if (canDragGanttRow(rowById.value.get(task.id), props.editable))
        emit("dates", Number(task.id), start, end);
    },
    on_progress_change: (task, progress) => {
      if (canDragGanttRow(rowById.value.get(task.id), props.editable))
        emit("progress", Number(task.id), Math.round(progress));
    },
  };
  const data = rows.value.map(
    ({ id, name, start, end, progress, custom_class }) => ({
      id,
      name,
      start,
      end,
      progress,
      custom_class,
    }),
  );
  if (!chart) {
    chart = new Gantt(host.value, data, options);
    chart.$container.addEventListener("scroll", syncLabels, { passive: true });
  } else {
    chart.$container
      .querySelectorAll(".gantt-today-line")
      .forEach((node) => node.remove());
    chart.$container.scrollTo({ left: 0, behavior: "instant" });
    chart.setup_options(options);
    chart.refresh(data);
  }
  decorateBars();
  chart.$container.scrollTop = scrollTop;
  if (scrollTarget === "today") {
    const marker = chart.$container.querySelector(".gantt-today-line");
    chart.$container.scrollLeft = Math.max(
      0,
      parseFloat(marker?.style.left || "0") - width / 2,
    );
  } else
    chart.$container.scrollLeft =
      mode.value === "fit" || scrollTarget === "start" ? 0 : scrollLeft;
  scrollTarget = null;
  updateScrollState();
}
function scheduleRender() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(render);
}
function selectMode(value) {
  if (value === "fit") includeToday.value = true;
  mode.value = value;
  scrollTarget = "start";
  scheduleRender();
}
function goToday() {
  includeToday.value = true;
  scrollTarget = "today";
  scheduleRender();
}
watch(
  [() => props.tasks, () => props.editable, () => props.indicators],
  scheduleRender,
  { deep: true },
);
onMounted(() => {
  document.addEventListener("fullscreenchange", fullscreenChanged);
  observer = new ResizeObserver(([entry]) => {
    if (Math.abs(entry.contentRect.width - lastWidth) > 1) {
      lastWidth = entry.contentRect.width;
      scheduleRender();
    }
  });
  observer.observe(host.value);
  scheduleRender();
});
onBeforeUnmount(() => {
  unmounted = true;
  observer?.disconnect();
  cancelAnimationFrame(frame);
  chart?.$container.removeEventListener("scroll", syncLabels);
  document.removeEventListener("fullscreenchange", fullscreenChanged);
});
</script>
<template>
  <section ref="panel" class="gantt-card" aria-label="Календарный план проекта">
    <div class="gantt-toolbar">
      <div class="gantt-heading">
        <h3>Календарный план</h3>
        <p v-if="range">
          {{ date(range.start) }} <span aria-hidden="true">→</span>
          {{ date(range.end) }}
          <span class="gantt-count"
            >Задачи {{ taskCount }} · Вехи {{ milestoneCount }}</span
          >
        </p>
      </div>
      <div v-if="rows.length" class="gantt-controls">
        <div
          class="gantt-navigation"
          role="group"
          aria-label="Прокрутка календаря"
        >
          <button
            type="button"
            :disabled="!canScrollBack"
            aria-label="Предыдущий период"
            title="Предыдущий период"
            @click="panCalendar(-1)"
          >
            ‹</button
          ><button
            type="button"
            :disabled="!canScrollForward"
            aria-label="Следующий период"
            title="Следующий период"
            @click="panCalendar(1)"
          >
            ›
          </button>
        </div>
        <div class="gantt-scale" role="group" aria-label="Масштаб календаря">
          <button
            v-for="item in [
              { id: 'fit', label: 'Весь проект' },
              { id: 'day', label: 'Дни' },
              { id: 'week', label: 'Недели' },
              { id: 'month', label: 'Месяцы' },
            ]"
            :key="item.id"
            type="button"
            :class="{ selected: mode === item.id }"
            :aria-pressed="mode === item.id"
            @click="selectMode(item.id)"
          >
            {{ item.label }}
          </button>
        </div>
        <button type="button" class="gantt-today" @click="goToday">
          <span aria-hidden="true" />Сегодня
        </button>
        <button
          v-if="fullscreenAvailable"
          type="button"
          class="gantt-expand"
          :aria-label="
            fullscreen ? 'Свернуть диаграмму' : 'Развернуть диаграмму'
          "
          :title="fullscreen ? 'Свернуть диаграмму' : 'Развернуть диаграмму'"
          :aria-pressed="fullscreen"
          @click="toggleFullscreen"
        >
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4" />
          </svg>
        </button>
      </div>
    </div>
    <div
      v-show="rows.length"
      class="gantt-split"
      :class="`scale-${mode}`"
      :style="{
        '--gantt-height': `${viewportHeight}px`,
        '--gantt-row-height': `${rowHeight}px`,
        '--gantt-header-height': `${headerHeight}px`,
      }"
    >
      <div ref="labels" class="gantt-labels" @scroll="syncCalendar">
        <div class="gantt-label-header">
          <span>Структура работ</span><span>Готовность</span>
        </div>
        <div
          v-for="row in rows"
          :key="row.id"
          class="gantt-task-row"
          :class="[
            {
              'has-risk': indicators[row.task.task_id]?.length,
              'is-summary': row.summary,
              'is-hovered': activeRow === row.id,
              'is-selected': selectedRow === row.id,
            },
            `status-${row.status}`,
          ]"
          @mouseenter="highlightRow(row.id)"
          @mouseleave="highlightRow(null)"
          @focusin="highlightRow(row.id)"
          @focusout="highlightRow(null)"
        >
          <div
            class="gantt-task-content"
            :style="{ paddingLeft: `${Math.min(row.depth, 8) * 20}px` }"
          >
            <button
              type="button"
              class="gantt-task-title"
              :title="`${row.wbs} ${row.name}`"
              @click="openRow(row)"
            >
              <span class="gantt-wbs">{{ row.wbs }}</span>
              <span
                v-if="row.milestone"
                class="gantt-milestone-icon"
                aria-label="Веха"
                >◆</span
              >
              <span
                v-else
                class="gantt-status-dot"
                :class="{ completed: row.status === 'done' }"
                aria-hidden="true"
                ><UiIcon v-if="row.status === 'done'" name="check" /></span
              >
              <span class="gantt-task-name">{{ row.name }}</span>
            </button>
            <div class="gantt-task-dates">
              <span>{{ date(row.start) }}</span
              ><span v-if="!row.milestone">→ {{ date(row.end) }}</span>
            </div>
            <div
              v-if="indicators[row.task.task_id]?.length"
              class="gantt-task-risks"
            >
              <RiskBadge :risks="indicators[row.task.task_id].slice(0, 1)" />
              <button
                v-if="indicators[row.task.task_id].length > 1"
                type="button"
                class="gantt-more-risks"
                :aria-label="`Показать все риски задачи ${row.name}`"
                @click="openRow(row)"
              >
                +{{ indicators[row.task.task_id].length - 1 }}
              </button>
            </div>
          </div>
          <span class="gantt-row-progress"
            ><strong>{{ row.progress }}<small>%</small></strong
            ><span class="gantt-progress-track"
              ><span :style="{ width: `${row.progress}%` }" /></span
          ></span>
        </div>
        <div class="gantt-label-tail" aria-hidden="true" />
      </div>
      <div
        ref="host"
        class="gantt-calendar"
        aria-label="Диаграмма Ганта"
        @mousedown.capture="guardDrag"
        @mousemove.capture="trackPointer"
      />
    </div>
    <div v-if="rows.length" class="gantt-footer">
      <div class="gantt-legend" aria-label="Обозначения диаграммы">
        <span
          v-for="status in statusLegend"
          :key="status"
          :class="`status-${status}`"
          ><i />{{ taskStatuses[status] }}</span
        ><span v-if="milestoneCount" class="legend-milestone"><i />Веха</span
        ><span class="legend-today"><i />Сегодня</span>
      </div>
    </div>
    <p v-if="missingDates && rows.length" class="gantt-missing">
      Без корректных дат {{ missingDates }}. Задайте начало и окончание, чтобы
      показать эти задачи на диаграмме.
    </p>
    <div v-if="!rows.length" class="gantt-empty">
      <h3>Здесь появится календарный план</h3>
      <p>
        {{
          tasks.length
            ? "Задайте даты начала и окончания активных задач."
            : "Добавьте задачи с датами начала и окончания."
        }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.gantt-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card);
  box-shadow: none;
}
.gantt-card:fullscreen {
  width: 100%;
  height: 100%;
  padding: 20px;
  border: 0;
  border-radius: 0;
  overflow-y: auto;
}
.gantt-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
}
.gantt-heading h3 {
  margin: 0 0 4px;
  font-size: 16px;
}
.gantt-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.gantt-heading p > span:first-child {
  margin: 0 6px;
}
.gantt-count {
  margin-left: 16px;
}
.gantt-controls,
.gantt-scale {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
}
.gantt-controls {
  flex-wrap: wrap;
}
.gantt-navigation {
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.gantt-navigation button {
  display: grid;
  place-items: center;
  min-height: 36px;
  width: 2rem;
  padding: 0;
  border: 0;
  border-radius: 0;
  font-size: 20px;
  font-weight: 400;
  color: var(--muted);
  background: var(--card);
}
.gantt-navigation button + button {
  border-left: 1px solid var(--border);
}
.gantt-navigation button:disabled {
  opacity: 0.3;
}
.gantt-navigation button:hover:not(:disabled) {
  color: var(--accent);
  background: var(--inset);
}
.gantt-expand {
  display: grid;
  place-items: center;
  min-height: 2.5rem;
  width: 2.5rem;
  padding: 8px;
  border-radius: 8px;
  color: var(--muted);
}
.gantt-expand svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.5;
}
.gantt-scale {
  padding: 4px;
  gap: 4px;
  background: var(--inset);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.gantt-scale button {
  min-height: 32px;
  padding: 4px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  font-size: 12px;
  white-space: nowrap;
}
.gantt-scale button.selected {
  color: var(--accent);
  background: var(--card);
  border-color: var(--border);
  box-shadow: none;
  font-weight: 600;
}
.gantt-today {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  font-size: 12px;
}
.gantt-today > span {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--accent);
}
.gantt-split {
  display: grid;
  grid-template-columns: clamp(245px, 29%, 390px) minmax(0, 1fr);
  min-width: 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.gantt-labels {
  height: var(--gantt-height);
  min-width: 0;
  overflow-y: auto;
  scrollbar-width: none;
  border-right: 1px solid var(--border);
  background: var(--card);
  z-index: 2;
}
.gantt-labels::-webkit-scrollbar {
  display: none;
}
.gantt-label-header {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: var(--gantt-header-height);
  padding: 0 16px;
  background: var(--inset);
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}
.gantt-task-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  height: var(--gantt-row-height);
  padding: 8px 16px;
  border: 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  text-align: left;
  background: var(--card);
}
.gantt-task-row.is-summary {
  background: var(--inset);
}
.gantt-task-row:hover,
.gantt-task-row.is-hovered {
  background: var(--accent-soft);
}
.gantt-task-row.is-selected {
  background: var(--accent-soft);
  outline: 1px solid var(--accent);
  outline-offset: -2px;
  box-shadow: inset 3px 0 var(--accent);
}
.gantt-task-content {
  display: block;
  flex: 1;
  min-width: 0;
}
.gantt-task-title {
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1.3;
  font-size: 13px;
}
.gantt-task-name {
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.gantt-wbs {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.is-summary .gantt-task-name {
  font-weight: 600;
}
.gantt-task-dates {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}
.gantt-row-progress {
  flex: 0 0 43px;
  text-align: right;
}
.gantt-row-progress strong {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.gantt-row-progress small {
  margin-left: 1px;
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
}
.gantt-progress-track,
.gantt-progress-track > span {
  display: block;
  height: 3px;
  border-radius: 2px;
}
.gantt-progress-track {
  margin-top: 6px;
  background: var(--border);
}
.gantt-progress-track > span {
  background: var(--task-color, var(--accent));
}
.gantt-label-tail {
  height: 22px;
  background: var(--inset);
}
.gantt-milestone-icon {
  color: var(--milestone);
  font-size: 12px;
}
.gantt-status-dot {
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--task-color, var(--accent));
  border-radius: 50%;
}
.gantt-status-dot > svg {
  width: 12px;
  height: 12px;
}
.gantt-status-dot.completed {
  background: color-mix(in srgb, var(--success) 8%, var(--card));
  border-color: var(--success);
  color: var(--success);
}
.is-summary .gantt-status-dot {
  width: 8px;
  height: 8px;
  background: var(--task-color, var(--accent));
  border: 0;
}
.gantt-calendar {
  position: relative;
  min-width: 0;
  overflow: hidden;
  height: var(--gantt-height);
}
.gantt-calendar :deep(.gantt-container) {
  border-radius: 0;
  max-width: 100%;
  height: var(--gantt-height) !important;
  background: var(--card);
  --g-row-color: var(--card);
  --g-header-background: var(--inset);
  --g-border-color: var(--border);
  --g-text-dark: var(--text);
  --g-text-light: var(--muted);
  --g-weekend-highlight-color: color-mix(
    in srgb,
    var(--inset) 80%,
    transparent
  );
  --g-today-highlight: var(--accent-soft);
  --g-progress-color: var(--accent);
}
.gantt-calendar :deep(.gantt) {
  max-width: none;
}
.gantt-calendar :deep(.grid-header) {
  overflow: hidden;
  background: var(--inset);
  border-bottom: 1px solid var(--border);
}
.gantt-calendar :deep(.upper-text) {
  top: 12px !important;
  color: var(--text);
  font:
    600 12px "Segoe UI",
    sans-serif;
  white-space: nowrap;
  text-transform: capitalize;
}
.gantt-calendar :deep(.lower-text) {
  color: var(--muted);
  font:
    12px "Segoe UI",
    sans-serif;
  white-space: nowrap;
}
.scale-fit :deep(.lower-text) {
  width: auto;
  min-width: 44px;
  margin-left: 4px;
  text-align: left;
}
.scale-month :deep(.lower-text) {
  width: auto;
  min-width: 76px;
  margin-left: 6px;
  text-align: left;
  text-transform: capitalize;
}
.gantt-calendar :deep(.side-header),
.gantt-calendar :deep(.adjust) {
  display: none;
}
.gantt-calendar :deep(.gantt .grid-row) {
  fill: var(--card);
}
.gantt-calendar :deep(.gantt .row-line) {
  stroke: var(--border);
  stroke-width: 1;
}
.gantt-calendar :deep(.gantt .tick) {
  stroke: var(--border);
  opacity: 0.45;
}
.gantt-calendar :deep(.gantt .tick.thick) {
  opacity: 1;
  stroke-width: 1;
}
.scale-month :deep(.gantt .tick:not(.thick)) {
  display: none;
}
.scale-fit :deep(.gantt .tick:not(.thick)) {
  display: none;
}
.gantt-calendar :deep(.bar-wrapper) {
  --task-color: var(--accent);
  --task-soft: var(--inset);
  cursor: pointer;
}
.status-backlog,
.gantt-calendar :deep(.status-backlog) {
  --task-color: var(--muted);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-todo,
.gantt-calendar :deep(.status-todo) {
  --task-color: var(--muted);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-dev,
.gantt-calendar :deep(.status-dev) {
  --task-color: var(--accent);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-review,
.gantt-calendar :deep(.status-review) {
  --task-color: var(--secondary);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-testing,
.gantt-calendar :deep(.status-testing) {
  --task-color: var(--secondary);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-release_wait,
.gantt-calendar :deep(.status-release_wait) {
  --task-color: var(--warning);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.status-done,
.gantt-calendar :deep(.status-done) {
  --task-color: var(--success);
  --task-soft: color-mix(in srgb, var(--task-color) 8%, var(--card));
}
.gantt-calendar :deep(.gantt .bar-wrapper .bar) {
  fill: var(--task-soft);
  stroke: var(--task-color);
  stroke-width: 1;
  outline: none;
}
.gantt-calendar :deep(.gantt .bar-wrapper .bar-progress) {
  fill: color-mix(in srgb, var(--task-color) 24%, var(--card));
  opacity: 1;
}
.gantt-calendar :deep(.gantt .bar-wrapper .bar-label) {
  fill: var(--text);
  font:
    600 12px "Segoe UI",
    sans-serif;
  text-anchor: middle;
  pointer-events: none;
}
.gantt-calendar :deep(.gantt .bar-wrapper.status-done .bar-label) {
  fill: var(--text);
}
.gantt-calendar :deep(.gantt .bar-wrapper.summary) {
  --task-color: var(--secondary);
  --task-soft: var(--inset);
}
.gantt-calendar :deep(.gantt .bar-wrapper.summary .bar) {
  stroke-width: 1.5;
}
.gantt-calendar :deep(.gantt .bar-wrapper.row-hover .bar),
.gantt-calendar :deep(.gantt .bar-wrapper:focus .bar) {
  filter: brightness(0.96);
  stroke-width: 2;
}
.gantt-calendar :deep(.gantt .bar-wrapper.row-selected .bar) {
  stroke: var(--accent);
  stroke-width: 2.5;
  filter: none;
}
.gantt-calendar :deep(.gantt .milestone .bar),
.gantt-calendar :deep(.gantt .milestone .bar-progress),
.gantt-calendar :deep(.gantt .milestone .handle) {
  visibility: hidden;
}
.gantt-calendar :deep(.milestone-diamond) {
  fill: var(--milestone);
  stroke: var(--card);
  stroke-width: 2;
}
.gantt-calendar :deep(.gantt-today-line) {
  position: absolute;
  width: 2px;
  background: var(--accent);
  pointer-events: none;
  z-index: 4;
  opacity: 0.85;
}
.gantt-calendar :deep(.gantt-today-line::before) {
  content: "";
  position: absolute;
  width: 7px;
  height: 7px;
  top: -4px;
  left: -2.5px;
  border-radius: 50%;
  background: var(--accent);
}
.gantt-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 8px 24px;
  padding: 12px 20px;
}
.gantt-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.gantt-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}
.gantt-legend i {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 2px;
  background: var(--task-color);
}
.gantt-legend .legend-milestone i {
  background: var(--milestone);
  transform: rotate(45deg);
  width: 0.48rem;
  height: 0.48rem;
}
.gantt-legend .legend-today i {
  width: 2px;
  height: 0.8rem;
  background: var(--accent);
}
.gantt-footer p,
.gantt-missing {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.gantt-missing {
  padding: 0 20px 12px;
}
.gantt-empty {
  padding: 48px 16px;
  text-align: center;
}
.gantt-empty h3 {
  margin: 8px 0;
  font-size: 16px;
}
.gantt-empty p {
  color: var(--muted);
  font-size: 14px;
}
@media (max-width: 900px) {
  .gantt-toolbar {
    align-items: flex-start;
  padding: 20px;
    gap: 16px;
}
  .gantt-split {
    grid-template-columns: 245px minmax(0, 1fr);
  }
  .gantt-task-row {
    padding: 8px 12px;
    gap: 8px;
  }
  .gantt-row-progress {
    flex-basis: 35px;
  }
  .gantt-label-header {
    padding: 0 12px;
  }
}
@media (max-width: 600px) {
  .gantt-toolbar,
  .gantt-controls {
    gap: 8px;
  }
  .gantt-controls {
    flex-wrap: wrap;
    width: 100%;
  }
  .gantt-scale {
    flex: 1;
    justify-content: space-between;
    padding: 4px;
  gap: 4px;
  border-radius: 12px;
}
  .gantt-scale button {
  padding: 4px 12px;
    font-size: 12px;
    min-height: 32px;
  border-radius: 8px;
}
  .gantt-today {
  min-height: 40px;
    font-size: 12px;
    padding: 8px 12px;
  gap: 8px;
}
  .gantt-split {
    grid-template-columns: minmax(0, 58%) minmax(0, 1fr);
  }
  .gantt-task-row {
    padding: 6px 8px;
    gap: 4px;
  }
  .gantt-task-title {
    font-size: 12px;
    gap: 4px;
  }
  .gantt-task-dates {
    font-size: 12px;
  }
  .gantt-row-progress {
    flex-basis: 27px;
  }
  .gantt-row-progress strong {
    font-size: 12px;
  }
  .gantt-label-header {
    padding: 0 8px;
    font-size: 12px;
  }
  .gantt-label-header > span:last-child {
    font-size: 0;
  }
  .gantt-label-header > span:last-child::after {
    content: "%";
    font-size: 12px;
  }
  .gantt-count {
    display: block;
    margin: 4px 0 0;
  }
  .gantt-footer {
    padding: 12px 12px;
  }
}
.gantt-task-row.has-risk {
  box-shadow: inset 3px 0 var(--warning);
}
.gantt-calendar :deep(.bar-wrapper.has-risk .bar) {
  stroke: var(--warning);
  stroke-width: 3;
}
.gantt-calendar :deep(.bar-wrapper.has-risk.row-selected .bar) {
  stroke: var(--accent);
}
.gantt-calendar :deep(.bar-wrapper:focus-visible .bar) {
  stroke: var(--text);
  stroke-width: 3;
}
.gantt-task-row :deep(.risk-badges) {
  display: flex;
  max-width: 100%;
}
.gantt-task-row :deep(.risk-marker) {
  display: flex;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  padding: 0;
}
.gantt-calendar :deep(.gantt-today-line) {
  background: var(--accent);
  width: 2px;
  opacity: 1;
}
.gantt-calendar :deep(.gantt-today-line > span) {
  position: absolute;
  top: 0;
  left: 4px;
  padding: 2px 4px;
  background: var(--card);
  color: var(--accent);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.gantt-task-row {
  padding-top: 8px;
  padding-bottom: 8px;
  overflow: hidden;
}
.gantt-task-content {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.gantt-task-title {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: start;
  width: 100%;
  min-height: 0;
  padding: 0;
  border: 0;
  border-radius: 4px;
  color: var(--text);
  background: transparent;
  text-align: left;
  line-height: 1.4;
  font-size: 13px;
}
.gantt-task-title:hover {
  color: var(--accent);
  background: transparent;
}
.gantt-task-title:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.gantt-task-name {
  min-width: 0;
  max-height: 2.8em;
  overflow-wrap: anywhere;
}
.gantt-task-title .gantt-status-dot {
  margin-top: 4px;
}
.gantt-task-dates {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  margin: 0;
  font-size: 12px;
  line-height: 1.25;
}
.gantt-task-dates > span {
  white-space: nowrap;
}
.gantt-task-risks {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 20px;
}
.gantt-task-risks :deep(.risk-badges) {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  flex-wrap: nowrap;
}
.gantt-task-risks :deep(.risk-marker) {
  line-height: 20px;
  min-width: 0;
  width: 100%;
  padding: 0 4px;
}
.gantt-more-risks {
  flex: 0 0 auto;
  min-height: 20px;
  padding: 0 4px;
  border-color: var(--warning);
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
  color: var(--text);
}
.gantt-legend > span {
  font-size: 12px;
}
@media (max-width: 600px) {
  .gantt-task-row {
    padding: 4px 8px;
    align-items: center;
  }
  .gantt-task-title {
    font-size: 12px;
    line-height: 16px;
    gap: 4px;
  }
  .gantt-task-name {
    max-height: 32px;
  }
  .gantt-task-content {
    gap: 4px;
    padding-left: 0 !important;
  }
  .gantt-row-progress {
    flex-basis: 25px;
  }
}
</style>
