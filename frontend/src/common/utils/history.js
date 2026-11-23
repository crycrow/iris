import { actionStates, riskStatuses, severities, taskStatuses } from "./format.js";

const riskEventTitles = {
  status: "Статус изменён",
  status_changed: "Статус изменён",
  created_manual: "Риск добавлен вручную",
  created: "Риск создан",
  updated: "Показатели обновлены",
  assigned: "Назначен ответственный",
  responsible_changed: "Изменён ответственный",
  action_added: "Добавлено мероприятие",
  action_changed: "Мероприятие изменено",
  action_updated: "Мероприятие обновлено",
  comment: "Комментарий",
  viewed: "Риск просмотрен",
  severity_set: "Задана критичность",
  severity_changed: "Критичность изменена",
  cause_resolved: "Основание устранено",
  cause_returned: "Основание появилось снова",
  history_restored: "Дата выявления уточнена",
};
const taskEventTitles = {
  created: "Задача создана",
  comment: "Комментарий",
  name: "Название изменено",
  description: "Описание изменено",
  status: "Статус изменён",
  progress_pct: "Прогресс изменён",
  start_date: "Дата начала изменена",
  due_date: "Дата окончания изменена",
  release_id: "Релиз изменён",
  parent_task_id: "Родительская задача изменена",
  is_milestone: "Признак вехи изменён",
  assignment_removed: "Назначение снято",
};
const empty = (value) => value == null || value === "" || value === "None" || value === "null";
const text = (value) => typeof value === "string" ? value : "";
const named = (items, idKey, value, nameKey, fallback) =>
  items?.find((item) => String(item[idKey]) === String(value))?.[nameKey] || fallback;
const enumValue = (labels, value, fallback) =>
  Object.hasOwn(labels, value) ? labels[value] : fallback;

export function historyNumber(value, digits = 3) {
  if (empty(value) || typeof value === "boolean" || typeof value === "object") return "Нет данных";
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? numeric.toLocaleString("ru-RU", { maximumFractionDigits: digits })
    : "Нет данных";
}

export function historyDate(value, includeTime = false) {
  if (empty(value)) return "Не задана";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/);
  if (!match) return "Дата недоступна";
  const [, year, month, day, hour, minute] = match;
  const check = new Date(Number(year), Number(month) - 1, Number(day));
  if (check.getFullYear() !== Number(year) || check.getMonth() + 1 !== Number(month) || check.getDate() !== Number(day) || Number(hour || 0) > 23 || Number(minute || 0) > 59) return "Дата недоступна";
  if (includeTime && hour) {

    const timestamp = String(value).replace(" ", "T");
    const instant = new Date(/[Zz]|[+-]\d{2}:?\d{2}$/.test(timestamp) ? timestamp : `${timestamp}Z`);
    if (!Number.isFinite(instant.getTime())) return "Дата недоступна";
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: "Europe/Moscow", dateStyle: "short", timeStyle: "short",
    }).format(instant);
  }
  return `${day}.${month}.${year}`;
}

function riskChangeValue(eventType, value, context) {
  if (["status", "status_changed"].includes(eventType)) return enumValue(riskStatuses, value, "Неизвестный статус");
  if (["severity_set", "severity_changed"].includes(eventType)) return enumValue(severities, value, "Неизвестная критичность");
  if (["assigned", "responsible_changed"].includes(eventType)) return empty(value) ? "Не назначен" : named(context.users, "user_id", value, "full_name", "Имя сотрудника недоступно");
  if (eventType === "updated") return historyNumber(value);
  return "Сведения недоступны";
}

export function presentRiskEvent(event, context = {}) {
  const result = {
    title: enumValue(riskEventTitles, event.event_type, "Изменение риска"),
    at: historyDate(event.event_at, true),
    details: [],
  };

  if (event.event_type === "comment") {
    result.details.push({ label: "", value: text(event.details) });
    return result;
  }
  let payload = event.details;
  if (typeof payload === "string") {
    try { payload = JSON.parse(payload); }
    catch {
      if (/[а-яё]/i.test(payload)) result.details.push({ label: "", value: payload });
      return result;
    }
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return result;
  for (const [key, value] of Object.entries(payload)) {
    if (value === "") continue;
    let label, display;
    if (["comment", "description", "reason"].includes(key)) {
      label = { comment: "Комментарий", description: "Описание", reason: "Причина" }[key];
      display = text(value);
    } else if (["from", "old", "to", "new"].includes(key)) {
      label = ["from", "old"].includes(key) ? "Ранее" : "Теперь";
      display = riskChangeValue(event.event_type, value, context);
    } else if (key === "responsible_id") {
      label = "Ответственный";
      display = empty(value) ? "Не назначен" : named(context.users, "user_id", value, "full_name", "Имя сотрудника недоступно");
    } else if (key === "action_id" && !payload.description) {
      label = "Мероприятие";
      display = named(context.actions, "action_id", value, "description", "Описание мероприятия недоступно");
    } else if (key === "execution_state" || key === "status" || key === "severity") {
      const dictionaries = { execution_state: actionStates, status: riskStatuses, severity: severities };
      label = { execution_state: "Состояние мероприятия", status: "Статус", severity: "Критичность" }[key];
      display = enumValue(dictionaries[key], value, key === "severity" ? "Неизвестная критичность" : "Неизвестное состояние");
    } else if (["due_date", "week_start", "as_of", "snapshot_date", "detected_at"].includes(key)) {
      label = { due_date: "Срок", week_start: "Начало расчётной недели", as_of: "Дата расчёта", snapshot_date: "Дата показателей", detected_at: "Дата выявления" }[key];
      display = historyDate(value);
    } else if (["measured_value", "threshold"].includes(key)) {
      label = key === "measured_value" ? "Значение показателя" : "Порог выявления";
      display = historyNumber(value);
    }

    if (label && display) result.details.push({ label, value: display });
  }
  return result;
}

function taskValue(field, value, context) {
  if (["name", "description"].includes(field)) return text(value) || "Не заполнено";
  if (field === "status") return enumValue(taskStatuses, value, "Неизвестный статус");
  if (field === "start_date" || field === "due_date") return historyDate(value);
  if (field === "progress_pct") {
    const valueText = historyNumber(value, 1);
    return valueText === "Нет данных" ? valueText : `${valueText} %`;
  }
  if (field === "release_id") return empty(value) ? "Без релиза" : named(context.releases, "release_id", value, "name", "Название релиза недоступно");
  if (field === "parent_task_id") return empty(value) ? "Верхний уровень" : named(context.tasks, "task_id", value, "name", "Название задачи недоступно");
  if (field === "is_milestone") {
    if ([true, "True", "true", 1, "1"].includes(value)) return "Да";
    if ([false, "False", "false", 0, "0"].includes(value)) return "Нет";
    return "Не указано";
  }
  return "Сведения недоступны";
}

export function presentTaskEvent(event, context = {}) {
  const type = event.change_type;
  const result = { title: enumValue(taskEventTitles, type, "Задача изменена"), at: historyDate(event.changed_at, true), details: [] };
  if (type === "comment" || type === "created") {
    result.details.push({ label: type === "created" ? "Название" : "", value: text(event.new_value) });
  } else if (type === "assignment_removed") {
    result.details.push({ label: "Сотрудник", value: named(context.users, "user_id", event.old_value, "full_name", "Имя сотрудника недоступно") });
  } else if (Object.hasOwn(taskEventTitles, type)) {
    result.details.push({ label: "Ранее", value: taskValue(type, event.old_value, context) }, { label: "Теперь", value: taskValue(type, event.new_value, context) });
  }
  return result;
}
