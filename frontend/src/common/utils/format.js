export const roles = {
  admin: "Администратор",
  manager: "Руководитель проекта",
  employee: "Сотрудник",
};
export const projectStatuses = {
  planned: "Планируется",
  active: "В работе",
  completed: "Завершён",
  cancelled: "Отменён",
};
export const taskStatuses = {
  backlog: "Бэклог",
  todo: "Пора делать",
  dev: "В разработке",
  review: "Проверка",
  testing: "Тестирование",
  release_wait: "Ожидает релиза",
  done: "Готово",
  cancelled: "Отклонена",
};
export const riskStatuses = {
  new: "Новый",
  reviewing: "На рассмотрении",
  in_progress: "В работе",
  closed: "Закрыт",
  rejected: "Отклонён",
};
export const severities = {
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая",
};
export const actionStates = {
  planned: "Запланировано",
  in_progress: "В работе",
  done: "Выполнено",
};
export const number = (v, d = 1) =>
  v == null
    ? "Нет данных"
    : Number(v).toLocaleString("ru-RU", { maximumFractionDigits: d });
export const date = (s) =>
  s ? String(s).slice(0, 10).split("-").reverse().join(".") : "Не задана";
export const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const today = () => iso(new Date());
export function monday(s) {
  const d = new Date(s + "T12:00:00");
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return iso(d);
}
export function shiftDate(s, n) {
  const d = new Date(s + "T12:00:00");
  d.setDate(d.getDate() + n);
  return iso(d);
}
export const list = (d) => (Array.isArray(d) ? d : d?.items || []);
export const taskProgress = (t) =>
  t.is_summary
    ? Number(t.progress_pct || 0)
    : t.status === "done"
      ? 100
      : ["backlog", "todo"].includes(t.status)
        ? 0
        : Number(t.progress_pct || 0);
export const filterTasks = (tasks, release) =>
  tasks.filter((t) => !release || String(t.release_id) === String(release));
export function planRows(tasks) {
  const nodes = new Map(tasks.map((t) => [t.task_id, { ...t, children: [] }]));
  const roots = [];
  for (const node of nodes.values()) {
    const parent = nodes.get(node.parent_task_id);
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const rows = [];
  function visit(nodes, prefix = "") {
    nodes.forEach((t, i) => {
      t.wbs = prefix + (i + 1);
      rows.push(t);
      visit(t.children, t.wbs + ".");
      if (t.children.length) {
        const active = t.children.filter((c) => c.status !== "cancelled");
        t.is_summary = true;
        t.planned_hours = active.reduce(
          (a, c) => a + Number(c.planned_hours || 0),
          0,
        );
        t.actual_hours = active.reduce(
          (a, c) => a + Number(c.actual_hours || 0),
          0,
        );
        t.progress_pct = t.planned_hours
          ? Math.round(
              active.reduce(
                (a, c) => a + Number(c.planned_hours || 0) * taskProgress(c),
                0,
              ) / t.planned_hours,
            )
          : 0;
      }
    });
  }
  visit(roots);
  return rows;
}
