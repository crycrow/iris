const fieldLabels = {
  name: "Название", full_name: "ФИО", login: "Логин", password: "Пароль",
  description: "Описание", text: "Текст", comment: "Комментарий",
  email: "Электронная почта", role: "Роль", status: "Статус",
  severity: "Критичность", execution_state: "Состояние мероприятия",
  start_date: "Дата начала", due_date: "Дата окончания", work_date: "Дата списания",
  period_from: "Начало периода", period_to: "Конец периода", as_of: "Дата расчёта",
  hours: "Часы", planned_hours: "Плановые часы", progress_pct: "Прогресс",
  threshold: "Порог", metric: "Показатель", condition_op: "Условие",
  risk_group: "Группа риска", recommendation: "Рекомендация",
  project_id: "Проект", task_id: "Задача", parent_task_id: "Родительская задача",
  user_id: "Сотрудник", subject_user_id: "Сотрудник", responsible_id: "Ответственный",
  manager_id: "Руководитель", release_id: "Релиз", risk_type_id: "Тип риска",
  daily_hours: "Часы в рабочем дне", plan_month: "Месяц плана",
};
const statusMessages = {
  400: "Проверьте введённые данные",
  401: "Войдите в систему заново",
  403: "У вас нет доступа к этому действию",
  404: "Запись не найдена или больше недоступна",
  409: "Данные изменились. Обновите страницу и повторите действие",
  422: "Проверьте введённые данные",
  429: "Слишком много запросов. Повторите действие чуть позже",
};
const genericError = "Не удалось выполнить действие. Попробуйте ещё раз";

function businessMessage(value) {
  return typeof value === "string" && /[а-яё]/i.test(value) &&
    !/Traceback|\[SQL:|SQLAlchemy|IntegrityError|ValidationError|<html|\bat \S+\.(?:js|py):/i.test(value);
}

function validationMessage(error) {
  if (!error || typeof error !== "object") return "Проверьте введённые данные";
  const field = [...(Array.isArray(error.loc) ? error.loc : [])].reverse().find((key) => Object.hasOwn(fieldLabels, key));
  const label = field ? fieldLabels[field] : "Поле формы";
  const type = String(error.type || "");
  if (type === "missing" || type === "value_error.missing") return `${label}. Заполните это поле`;
  if (/literal|enum/.test(type)) return `${label}. Выберите значение из списка`;
  if (/date|time/.test(type)) return `${label}. Укажите корректную дату`;
  if (/int|float|decimal|finite_number/.test(type)) return `${label}. Укажите корректное число`;
  if (/greater_than|less_than|multiple_of/.test(type)) return `${label}. Значение выходит за допустимые границы`;
  if (/too_short|string_too_short/.test(type)) return `${label}. Значение слишком короткое`;
  if (/too_long|string_too_long/.test(type)) return `${label}. Значение слишком длинное`;
  if (/bool/.test(type)) return `${label}. Выберите значение`;
  return `${label}. Проверьте введённое значение`;
}

export function apiErrorMessage(detail, status) {
  if (status >= 500) return "Сервис временно недоступен. Попробуйте ещё раз позже";
  if (Array.isArray(detail) && detail.length) return [...new Set(detail.map(validationMessage))].join(". ");
  if (businessMessage(detail)) return detail;
  return statusMessages[status] || genericError;
}

export function clientErrorMessage(error) {
  return businessMessage(error?.message) ? error.message : genericError;
}
