<script setup>
import { computed } from 'vue';
import { number, date } from '../../../common/utils/format.js';
import { groupTimeEntries } from '../timeEntries.js';
const props = defineProps({ entries: { type: Array, default: () => [] }, currentUserId: Number });
defineEmits(['edit', 'remove']);
const people = computed(() => groupTimeEntries(props.entries));
</script>

<template>
  <div class="entry-groups">
    <div class="entry-group-heading" aria-hidden="true"><span>Сотрудник</span><span>Списано</span></div>
    <details v-for="person in people" :key="person.user_id" class="person-entries">
      <summary>
        <span class="entry-chevron" aria-hidden="true">›</span>
        <span class="person-name">{{ person.name }}<small>Задач {{ person.tasks.length }}</small></span>
        <strong class="entry-hours">{{ number(person.hours) }} ч</strong>
      </summary>
      <div class="person-tasks">
        <details v-for="task in person.tasks" :key="task.task_id" class="task-entries">
          <summary :style="{paddingLeft: (16 + task.depth * 16) + 'px'}">
            <span class="entry-chevron" aria-hidden="true">›</span>
            <span class="entry-task-name" :class="{'milestone-label': task.is_milestone}">{{ task.wbs ? task.wbs + ' ' : '' }}{{ task.is_milestone ? '◆ ' : '' }}{{ task.name }}<small>{{ task.project_name }}</small></span>
            <strong class="entry-hours">{{ number(task.hours) }} ч</strong>
          </summary>
          <div class="table-wrap mobile-cards entry-details">
            <table>
              <thead><tr><th>Дата</th><th>Часы</th><th>Комментарий</th><th v-if="person.user_id === currentUserId">Действия</th></tr></thead>
              <tbody>
                <tr v-for="entry in task.entries" :key="entry.entry_id">
                  <td data-label="Дата">{{ date(entry.work_date) }}</td>
                  <td data-label="Часы">{{ number(entry.hours) }}</td>
                  <td data-label="Комментарий">{{ entry.comment || 'Без комментария' }}</td>
                  <td v-if="person.user_id === currentUserId">
                    <div class="toolbar"><button type="button" @click="$emit('edit', entry)">Изменить</button><button type="button" class="danger" @click="$emit('remove', entry)">Удалить</button></div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </details>
  </div>
</template>

<style scoped>
.entry-groups { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.entry-group-heading { display: flex; justify-content: space-between; padding: 12px 20px; color: var(--secondary); background: var(--inset); font-size: 12px; }
.person-entries + .person-entries { border-top: 1px solid var(--border); }
summary { display: flex; align-items: center; gap: 12px; padding: 16px 20px; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary:hover { background: var(--inset); }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -3px; }
.entry-chevron { color: var(--muted); font-size: 22px; line-height: 1; width: 12px; flex-shrink: 0; transition: transform .15s; }
details[open] > summary .entry-chevron { transform: rotate(90deg); }
.person-name { font-weight: 600; }
.person-name, .entry-task-name { flex: 1; min-width: 0; }
small { display: block; color: var(--secondary); font-weight: 400; margin-top: 4px; }
.entry-hours { font-variant-numeric: tabular-nums; white-space: nowrap; }
.person-tasks { margin: 0 20px 16px 44px; border-left: 2px solid var(--border); }
.task-entries + .task-entries { border-top: 1px solid var(--border); }
.task-entries > summary { padding: 12px 16px; }
.task-entries .entry-hours { font-size: 13px; }
.entry-details { margin: 0 16px 12px; }
@media (max-width: 640px) {
  summary { padding: 14px 12px; gap: 8px; }
  .person-tasks { margin-left: 20px; margin-right: 8px; }
  .task-entries > summary { padding: 12px 8px; }
  .entry-details { margin: 0 8px 12px; }
}
</style>
