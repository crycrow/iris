import test from "node:test";
import assert from "node:assert/strict";
import { historyDate, historyNumber, presentRiskEvent, presentTaskEvent } from "../src/common/utils/history.js";
import { apiErrorMessage, clientErrorMessage } from "../src/common/utils/errors.js";
import { groupedCounts } from "../src/common/utils/reportCharts.js";

test("Stored restoration payload has labelled Russian dates and rounded values, without internal source", () => {
  const event = {
    event_type: "history_restored",
    event_at: "2026-11-13T09:42:11.123456+00:00",
    details: JSON.stringify({
      comment: "Дата основания восстановлена по сохранённым недельным показателям",
      week_start: "2026-11-09",
      measured_value: 0.6666666666666666,
      source: "metric_snapshots",
    }),
  };
  const rendered = presentRiskEvent(event);
  assert.equal(rendered.title, "Дата выявления уточнена");
  assert.equal(rendered.at, "13.11.2026, 12:42");
  assert.deepEqual(rendered.details.slice(1), [
    { label: "Начало расчётной недели", value: "09.11.2026" },
    { label: "Значение показателя", value: "0,667" },
  ]);
  assert.doesNotMatch(JSON.stringify(rendered), /metric_snapshots|2026-11|0\.6666|source/);
  assert.match(event.details, /metric_snapshots/);
});

test("Unknown enums and payload fields never leak technical values", () => {
  const rendered = presentRiskEvent({ event_type: "status_changed", details: JSON.stringify({
    from: "new", to: "future_status", severity: "future_level", execution_state: "future_state",
    internal_table: "metric_snapshots", trace: { secret_id: 42 }, source: "future_source",
  }) });
  assert.deepEqual(rendered.details.map((item) => item.value), ["Новый", "Неизвестный статус", "Неизвестная критичность", "Неизвестное состояние"]);
  assert.doesNotMatch(JSON.stringify(rendered), /future_|metric_snapshots|secret_id|\[object Object\]/);
  assert.deepEqual(presentRiskEvent({ event_type: "future_event", details: '{"internal_id":42}' }).details, []);
  assert.equal(presentRiskEvent({ event_type: "constructor" }).title, "Изменение риска");
});

test("Risk transitions use the right enum and resolve references to names", () => {
  assert.deepEqual(presentRiskEvent({ event_type: "severity_changed", details: '{"from":"medium","to":"high"}' }).details.map((item) => item.value), ["Средняя", "Высокая"]);
  const users = [{ user_id: 7, full_name: "Белов Иван Петрович" }];
  assert.equal(presentRiskEvent({ event_type: "assigned", details: '{"responsible_id":"7"}' }, { users }).details[0].value, users[0].full_name);
  assert.equal(presentRiskEvent({ event_type: "assigned", details: '{"responsible_id":999}' }).details[0].value, "Имя сотрудника недоступно");
  assert.equal(presentRiskEvent({ event_type: "assigned", details: '{"responsible_id":null}' }).details[0].value, "Не назначен");
  const action = presentRiskEvent({ event_type: "action_changed", details: '{"action_id":1,"execution_state":"done"}' }, { actions: [{ action_id: 1, description: "Проверить план" }] });
  assert.deepEqual(action.details.map((item) => item.value), ["Проверить план", "Выполнено"]);
});

test("Free text, including JSON, English words and decimal strings, is preserved exactly", () => {
  const comment = '{"source":"metric_snapshots","value":0.666666}\nKeep this text';
  assert.equal(presentRiskEvent({ event_type: "comment", details: comment }).details[0].value, comment);
  assert.equal(presentTaskEvent({ change_type: "comment", new_value: comment }).details[0].value, comment);
  assert.equal(presentTaskEvent({ change_type: "name", old_value: "API review", new_value: comment }).details[1].value, comment);
  assert.equal(presentRiskEvent({ event_type: "action_added", details: JSON.stringify({ action_id: 3, description: comment }) }).details[0].value, comment);
});

test("Numeric and date formatting handles zero, decimals and malformed values", () => {
  assert.equal(historyNumber(0), "0");
  assert.equal(historyNumber("1234.567891"), "1\u00a0234,568");
  assert.equal(historyNumber(-0.777777), "-0,778");
  for (const value of [null, undefined, "", "NaN", NaN, Infinity, -Infinity, true, {}, []])
    assert.equal(historyNumber(value), "Нет данных");
  assert.equal(historyDate("2026-11-09"), "09.11.2026");
  assert.equal(historyDate("2026-02-30"), "Дата недоступна");
  assert.equal(historyDate("not_a_date"), "Дата недоступна");
  assert.equal(historyDate(null), "Не задана");
});

test("Event timestamps use Moscow time across calendar boundaries; calendar dates do not shift", () => {
  assert.equal(historyDate("2026-11-12T22:30:00Z", true), "13.11.2026, 01:30");
  assert.equal(historyDate("2026-11-13T01:30:00+05:00", true), "12.11.2026, 23:30");
  assert.equal(historyDate("2026-11-12T22:30:00", true), "13.11.2026, 01:30");
  assert.equal(historyDate("2026-11-12", true), "12.11.2026");
});

test("Stored task changes display release and parent names, dates, percentages and booleans", () => {
  const render = (change_type, old_value, new_value, context) => presentTaskEvent({ change_type, old_value, new_value }, context).details.map((item) => item.value);
  assert.deepEqual(render("release_id", "None", "4", { releases: [{ release_id: 4, name: "Ноябрь" }] }), ["Без релиза", "Ноябрь"]);
  assert.deepEqual(render("parent_task_id", "None", "5", { tasks: [{ task_id: 5, name: "Подготовка" }] }), ["Верхний уровень", "Подготовка"]);
  assert.deepEqual(render("is_milestone", "False", "True"), ["Нет", "Да"]);
  assert.deepEqual(render("due_date", "2026-11-10", "2026-11-12"), ["10.11.2026", "12.11.2026"]);
  assert.deepEqual(render("progress_pct", "0.0", "66.666666"), ["0 %", "66,7 %"]);
  assert.deepEqual(render("status", "todo", "unknown_enum"), ["Пора делать", "Неизвестный статус"]);
  assert.deepEqual(render("private_column", "raw_old", "raw_new"), []);
});

test("Validation and transport errors are Russian without schema names or server internals", () => {
  assert.equal(apiErrorMessage([{ loc: ["body", "responsible_id"], type: "missing", msg: "Field required" }], 422), "Ответственный. Заполните это поле");
  assert.equal(apiErrorMessage([{ loc: ["body", "secret_field"], type: "literal_error", msg: "Input should be 'admin'" }], 422), "Поле формы. Выберите значение из списка");
  assert.equal(apiErrorMessage([{ loc: ["body", "hours"], type: "float_parsing", msg: "Input should be a valid number" }], 422), "Часы. Укажите корректное число");
  assert.equal(apiErrorMessage("Сначала назначьте ответственного", 409), "Сначала назначьте ответственного");
  assert.equal(apiErrorMessage("Internal Server Error", 500), "Сервис временно недоступен. Попробуйте ещё раз позже");
  assert.equal(apiErrorMessage({ internal_table: "metric_snapshots" }, 422), "Проверьте введённые данные");
  assert.doesNotMatch(clientErrorMessage(new Error("Cannot read properties of undefined")), /Cannot|undefined/);
});

test("Unknown chart enums are localized while user-defined category names stay unchanged", () => {
  assert.equal(groupedCounts([{ status: "future_status" }], "status", { new: "Новый" }).at(-1).label, "Неизвестная категория");
  assert.equal(groupedCounts([{ name: "API review" }], "name")[0].label, "API review");
});
