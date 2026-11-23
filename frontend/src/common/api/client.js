import { apiErrorMessage } from "../utils/errors.js";

export async function request(path, options = {}) {
  const token = sessionStorage.getItem("token");
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).catch((cause) => {
    throw new Error(cause?.name === "AbortError"
      ? "Запрос отменён"
      : "Не удалось связаться с сервером. Проверьте подключение и повторите действие", { cause });
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.includes("login")) {
      sessionStorage.clear();
      window.dispatchEvent(new Event("session-expired"));
    }
    const error = new Error(apiErrorMessage(data?.detail, response.status));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return (options.download ? response.blob() : response.json()).catch((cause) => {
    throw new Error("Не удалось прочитать ответ сервера. Обновите страницу и повторите действие", { cause });
  });
}
export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: "POST", body }),
  put: (p, body) => request(p, { method: "PUT", body }),
  del: (p) => request(p, { method: "DELETE" }),
};
export async function download(path, name) {
  const blob = await request(path, { download: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
