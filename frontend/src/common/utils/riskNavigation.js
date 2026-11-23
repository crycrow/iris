export function safeReturn(value) {
  return typeof value === "string" &&
    /^\/(projects(?:\/\d+)?|risks|timebook|reports(?:\/\w+)?)(?:[?#]|$)/.test(
      value,
    )
    ? value
    : value === "/"
      ? "/"
      : null;
}
export function riskObjectLocation(risk, canManage = true, projectId = null) {
  const project = risk.project_id || projectId;
  if (!project) return null;
  const query = risk.task_id
    ? { tab: "plan", task: String(risk.task_id) }
    : risk.subject_user_id && canManage
      ? { tab: "resources", user: String(risk.subject_user_id) }
      : { tab: "summary" };
  return { path: `/projects/${project}`, query };
}
