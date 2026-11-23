import test from 'node:test';
import assert from 'node:assert/strict';
import { groupTimeEntries } from '../src/modules/time-tracking/timeEntries.js';

test('Groups by employee and task ids, sums decimal hours and sorts by surname', () => {
  const entries = [
    {entry_id: 1, user_id: 1, user_name: 'Яковлев Иван Петрович', project_id: 1, project_name: 'Проект', task_id: 10, task_name: 'Поддержка', work_date: '2026-11-10', hours: '1.50'},
    {entry_id: 2, user_id: 2, user_name: 'Белов Алексей Павлович', project_id: 1, project_name: 'Проект', task_id: 10, task_name: 'Поддержка', work_date: '2026-11-10', hours: '2.00'},
    {entry_id: 3, user_id: 1, user_name: 'Яковлев Иван Петрович', project_id: 1, project_name: 'Проект', task_id: 10, task_name: 'Поддержка', work_date: '2026-11-11', hours: '0.50'},
    {entry_id: 4, user_id: 1, user_name: 'Яковлев Иван Петрович', project_id: 2, project_name: 'Другой проект', task_id: 20, task_name: 'Поддержка', work_date: '2026-11-11', hours: '3.00'},
  ];
  const grouped = groupTimeEntries(entries);
  assert.deepEqual(grouped.map(p => [p.user_id, p.hours]), [[2,2], [1,5]]);
  assert.equal(grouped[1].tasks.length, 2);
  const firstTask = grouped[1].tasks.find(t => t.task_id === 10);
  assert.equal(firstTask.hours, 2);
  assert.deepEqual(firstTask.entries.map(e=>e.entry_id), [3,1]);
  assert.deepEqual(entries.map(e=>e.entry_id), [1,2,3,4]);
});

test('Empty result contains no employee groups', () => {
  assert.deepEqual(groupTimeEntries([]), []);
});
