import { taskProgress, monday, shiftDate } from "../common/utils/format.js";

export const taskGroups = [
  {
    key: "completed",
    label: "Завершены",
    statuses: ["done"],
    color: "var(--secondary)",
  },
  {
    key: "working",
    label: "В работе",
    statuses: ["dev", "review", "testing", "release_wait"],
    color: "var(--accent)",
  },
  {
    key: "waiting",
    label: "К выполнению",
    statuses: ["backlog", "todo"],
    color: "var(--muted)",
  },
  {
    key: "cancelled",
    label: "Отклонены",
    statuses: ["cancelled"],
    color: "var(--border)",
  },
];

export function leafTasks(tasks) {
  const parents = new Set(
    tasks.map((task) => task.parent_task_id).filter(Boolean),
  );
  return tasks.filter((task) => !parents.has(task.task_id));
}

export function projectOverview(project, tasks, risks = []) {
  if (!Array.isArray(tasks))
    return {
      ...project,
      progress: null,
      taskCount: null,
      completedCount: null,
      available: false,
      openRiskCount: risks.length,
    };
  const leaves = leafTasks(tasks).filter((task) => task.status !== "cancelled");
  const work = leaves.filter((task) => !task.is_milestone);
  const budget = work.reduce(
    (total, task) => total + Number(task.planned_hours || 0),
    0,
  );
  const earned = work.reduce(
    (total, task) =>
      total + (Number(task.planned_hours || 0) * taskProgress(task)) / 100,
    0,
  );
  return {
    ...project,
    available: true,
    progress: budget > 0 ? Math.round((earned / budget) * 100) : null,
    taskCount: leaves.length,
    completedCount: leaves.filter((task) => task.status === "done").length,
    budget,
    earned,
    openRiskCount: risks.length,
  };
}

export function initials(name = "") {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

export function weekDates(date) {
  const first = monday(date);
  return Array.from({ length: 7 }, (_, index) => shiftDate(first, index));
}

export function projectTeam(projects) {
  const people = new Map();
  for (const project of projects) {
    for (const person of project.members || []) {
      if (!people.has(person.user_id))
        people.set(person.user_id, { ...person, projects: [] });
      people
        .get(person.user_id)
        .projects.push({ project_id: project.project_id, name: project.name });
    }
  }
  return [...people.values()].sort((a, b) =>
    a.full_name.localeCompare(b.full_name, "ru"),
  );
}
