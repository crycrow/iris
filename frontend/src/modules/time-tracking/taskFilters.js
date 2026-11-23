const normalized = (value) =>
  String(value || "")
    .toLocaleLowerCase("ru-RU")
    .replaceAll("ё", "е")
    .trim();

export function filterProjectTasks(
  tasks,
  { query = "", assignee = "", riskOnly = false, indicators = {} } = {},
) {
  const words = normalized(query).split(/\s+/).filter(Boolean);
  return tasks.filter((task) => {
    const text = normalized(
      `${task.name} ${task.description || ""} #${task.task_id}`,
    );
    if (!words.every((word) => text.includes(word))) return false;
    if (assignee === "unassigned" && task.assignments?.length) return false;
    if (
      assignee &&
      assignee !== "unassigned" &&
      !task.assignments?.some(
        (person) => String(person.user_id) === String(assignee),
      )
    )
      return false;
    return !riskOnly || Boolean(indicators[task.task_id]?.length);
  });
}

export function includeTaskAncestors(tasks, matches) {
  const byId = new Map(tasks.map((task) => [task.task_id, task]));
  const ids = new Set(matches.map((task) => task.task_id));
  for (const task of matches) {
    const visited = new Set([task.task_id]);
    let parent = byId.get(task.parent_task_id);
    while (parent && !visited.has(parent.task_id)) {
      ids.add(parent.task_id);
      visited.add(parent.task_id);
      parent = byId.get(parent.parent_task_id);
    }
  }
  return tasks.filter((task) => ids.has(task.task_id));
}

export function taskDepth(task, tasks = []) {
  if (!task) return 0;
  if (task.wbs) return Math.max(0, String(task.wbs).split(".").length - 1);
  const byId = new Map(tasks.map((item) => [item.task_id, item]));
  const visited = new Set([task.task_id]);
  let depth = 0, parent = byId.get(task.parent_task_id);
  while (parent && !visited.has(parent.task_id)) {
    visited.add(parent.task_id);
    depth += 1;
    parent = byId.get(parent.parent_task_id);
  }
  return depth;
}
export function taskHierarchy(tasks = []) {
  const byId = new Map(tasks.map((task) => [task.task_id, task]));
  const children = new Map();
  for (const task of tasks) {
    const parent = byId.has(task.parent_task_id) ? task.parent_task_id : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(task);
  }
  const result = [], visited = new Set();
  function walk(branch, prefix = "", depth = 0) {
    branch.forEach((task, index) => {
      if (visited.has(task.task_id)) return;
      visited.add(task.task_id);
      const wbs = task.wbs || `${prefix}${index + 1}`;
      result.push({ ...task, wbs, depth });
      walk(children.get(task.task_id) || [], `${wbs}.`, depth + 1);
    });
  }
  walk(children.get(null) || []);
  walk(tasks.filter((task) => !visited.has(task.task_id)));
  return result;
}
export function taskLabel(task, tasks = []) {
  return `${"\u2003".repeat(Math.min(taskDepth(task, tasks), 8))}${task.wbs ? task.wbs + " " : ""}${task.is_milestone ? "◆ " : ""}${task.name || task.task_name || "Без названия"}`;
}
