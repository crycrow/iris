import { defineStore } from "pinia";
import { api } from "../api/client.js";
export const useAuth = defineStore("auth", {
  state: () => ({
    user: JSON.parse(sessionStorage.getItem("user") || "null"),
    token: sessionStorage.getItem("token"),
  }),
  getters: {
    manager: (s) => ["admin", "manager"].includes(s.user?.role),
    admin: (s) => s.user?.role === "admin",
  },
  actions: {
    async refresh() {
      if (!this.token) return;
      this.user = await api.get("/auth/me");
      sessionStorage.setItem("user", JSON.stringify(this.user));
    },
    async login(login, password) {
      const d = await api.post("/auth/login", { login, password });
      this.token = d.access_token;
      this.user = d.user;
      sessionStorage.setItem("token", this.token);
      sessionStorage.setItem("user", JSON.stringify(this.user));
    },
    async logout() {
      try {
        await api.post("/auth/logout");
      } finally {
        this.clear();
      }
    },
    clear() {
      this.user = null;
      this.token = null;
      sessionStorage.removeItem("user");
      sessionStorage.removeItem("token");
    },
  },
});
