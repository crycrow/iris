import { defineStore } from "pinia";
import { clientErrorMessage } from "../utils/errors.js";
export const useUi = defineStore("ui", {
  state: () => ({ message: "", error: false }),
  actions: {
    notify(message, error = false) {
      this.message = error ? clientErrorMessage({ message }) : message;
      this.error = error;
      const shownMessage = this.message;
      setTimeout(() => {
        if (this.message === shownMessage) this.message = "";
      }, 7000);
    },
    async act(fn, message = "Сохранено") {
      try {
        const result = await fn();
        if (message) this.notify(message);
        return result;
      } catch (e) {
        this.notify(e.message, true);
        return undefined;
      }
    },
  },
});
