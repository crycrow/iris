import { taskProgress } from "../../common/utils/format.js";

const DAY = 86400000;
const knownStatuses = new Set([
  "backlog",
  "todo",
  "dev",
  "review",
  "testing",
  "release_wait",
  "done",
]);

export function dayNumber(value) {
  const text = String(value || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const valueMs = Date.parse(`${text}T00:00:00Z`);
  return Number.isFinite(valueMs) &&
    new Date(valueMs).toISOString().slice(0, 10) === text
    ? valueMs / DAY
    : null;
}
const dayText = (day) => new Date(day * DAY).toISOString().slice(0, 10);

export function buildGanttRows(tasks) {
  const active = tasks.filter((task) => task.status !== "cancelled");
  const children = new Map();
  for (const task of active) {
    const key = String(task.parent_task_id);
    if (!children.has(key)) children.set(key, []);
    children.get(key).push(task);
  }
  const ranges = new Map();
  function range(task, visited = new Set()) {
    const key = String(task.task_id);
    if (ranges.has(key)) return ranges.get(key);
    if (visited.has(key)) return null;
    const branch = new Set(visited).add(key);
    const start = dayNumber(
      task.start_date || (task.is_milestone && task.due_date),
    );
    const end = dayNumber(
      task.due_date || (task.is_milestone && task.start_date),
    );
    const parts =
      start !== null && end !== null && end >= start ? [[start, end]] : [];
    for (const child of children.get(key) || []) {
      const childRange = range(child, branch);
      if (childRange) parts.push(childRange);
    }
    const result = parts.length
      ? [
          Math.min(...parts.map((part) => part[0])),
          Math.max(...parts.map((part) => part[1])),
        ]
      : null;
    ranges.set(key, result);
    return result;
  }
  return active.flatMap((task, index) => {
    const dates = range(task);
    if (!dates) return [];
    const summary = Boolean(
      task.is_summary || children.get(String(task.task_id))?.length,
    );
    const milestone = Boolean(task.is_milestone && !summary);
    const status = knownStatuses.has(task.status) ? task.status : "todo";
    return [
      {
        id: String(task.task_id),
        task,
        name: task.name || "Без названия",
        wbs: task.wbs || String(index + 1),
        depth: Math.max(0, String(task.wbs || "").split(".").length - 1),
        start: dayText(dates[0]),
        end: dayText(milestone ? dates[0] : dates[1]),
        progress: Math.min(
          100,
          Math.max(0, taskProgress({ ...task, is_summary: summary }) || 0),
        ),
        summary,
        milestone,
        status,

        custom_class: `status-${status}`,
      },
    ];
  });
}

export function ganttRange(rows, includeDate) {
  if (!rows.length) return null;
  const taskStart = Math.min(...rows.map((row) => dayNumber(row.start)));
  const taskEnd = Math.max(...rows.map((row) => dayNumber(row.end)));
  const extra = dayNumber(includeDate);
  const start = extra === null ? taskStart : Math.min(taskStart, extra);
  const end = extra === null ? taskEnd : Math.max(taskEnd, extra);
  return {
    start: dayText(start),
    end: dayText(end),
    days: end - start + 1,
    before: taskStart - start + 2,
    after: end - taskEnd + 2,
  };
}

export function fitGantt(range, availableWidth) {
  if (!range) return { stepDays: 1, columnWidth: 44, columns: 0 };
  const width = Math.max(120, Number(availableWidth) || 120);
  const span = range.days + 4;
  const columns = span + 1;
  const columnWidth = (width - 2) / columns;
  const labelEveryDays =
    [1, 2, 7, 14, 30, 60, 90, 180, 365].find(
      (step) => step * columnWidth >= 65,
    ) || Math.ceil(65 / columnWidth);

  return { stepDays: 1, columns, columnWidth, labelEveryDays };
}

export function canDragGanttRow(row, editable) {
  return Boolean(editable && row && !row.summary && !row.milestone);
}
