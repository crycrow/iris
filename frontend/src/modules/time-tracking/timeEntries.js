export function groupTimeEntries(entries) {
  const people = new Map();
  for (const entry of entries) {
    if (!people.has(entry.user_id)) {
      people.set(entry.user_id, {
        user_id: entry.user_id,
        name: entry.user_name,
        hours: 0,
        tasks: new Map(),
      });
    }
    const person = people.get(entry.user_id);
    const hours = Number(entry.hours);
    person.hours += hours;
    if (!person.tasks.has(entry.task_id)) {
      person.tasks.set(entry.task_id, {
        task_id: entry.task_id,
        project_id: entry.project_id,
        project_name: entry.project_name,
        name: entry.task_name,
        parent_task_id: entry.parent_task_id,
        depth: entry.task_depth ?? (entry.parent_task_id ? 1 : 0),
        wbs: entry.task_wbs,
        is_milestone: entry.task_is_milestone,
        hours: 0,
        entries: [],
      });
    }
    const task = person.tasks.get(entry.task_id);
    task.hours += hours;
    task.entries.push(entry);
  }
  return [...people.values()]
    .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'))
    .map((person) => ({
      ...person,
      tasks: [...person.tasks.values()]
        .sort((a, b) => (a.project_name || '').localeCompare(b.project_name || '', 'ru') ||
          (a.wbs && b.wbs ? a.wbs.localeCompare(b.wbs, 'ru', {numeric: true}) : (a.name || '').localeCompare(b.name || '', 'ru')))
        .map((task) => ({
          ...task,
          entries: task.entries.slice().sort((a, b) => b.work_date.localeCompare(a.work_date) || b.entry_id - a.entry_id),
        })),
    }));
}
