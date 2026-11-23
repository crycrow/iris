<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client.js";
import { list } from "../utils/format.js";
import UiIcon from "./UiIcon.vue";
const router = useRouter(),
  query = ref(""),
  projects = ref([]),
  busy = ref(false),
  error = ref(""),
  focused = ref(false);
const results = computed(() =>
  projects.value
    .filter((p) =>
      p.name
        .toLocaleLowerCase("ru")
        .includes(query.value.trim().toLocaleLowerCase("ru")),
    )
    .slice(0, 6),
);
async function load() {
  focused.value = true;
  if (projects.value.length || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    projects.value = list(await api.get("/projects"));
  } catch {
    error.value = "Не удалось загрузить проекты";
  } finally {
    busy.value = false;
  }
}
function choose(p) {
  query.value = "";
  focused.value = false;
  router.push("/projects/" + p.project_id);
}
</script>
<template>
  <div
    class="project-search"
    @focusout="
      (e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) focused = false;
      }
    "
  >
    <form role="search" @submit.prevent="results[0] && choose(results[0])">
      <UiIcon name="search" /><input
        v-model="query"
        aria-label="Найти проект"
        placeholder="Найти проект"
        @focus="load"
        @keydown.esc="focused = false"
        autocomplete="off"
      /><kbd>↵</kbd>
    </form>
    <div v-if="focused && query.trim()" class="search-results">
      <p v-if="busy">Ищем проекты…</p>
      <p v-else-if="error">{{ error }}</p>
      <template v-else
        ><button v-for="p in results" :key="p.project_id" @click="choose(p)">
          <UiIcon name="projects" /><span>{{ p.name }}</span
          ><span>↗</span>
        </button>
        <p v-if="!results.length">Проекты не найдены</p></template
      >
    </div>
  </div>
</template>
<style scoped>
.project-search {
  position: relative;
  flex: 1;
  max-width: 30rem;
  min-width: 0;
}
.project-search form {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--inset);
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 0 12px;
  min-height: 36px;
}
.project-search form:focus-within {
  border-color: var(--accent);
}
svg {
  width: 18px;
  height: 18px;
  flex: none;
  color: var(--muted);
}
input {
  background: transparent;
  border: 0;
  outline: none;
  min-height: 36px;
  padding: 8px 0;
  font-size: 14px;
}
kbd {
  font: inherit;
  color: var(--muted);
  font-size: 12px;
  line-height: 20px;
  min-width: 20px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--card);
}
.search-results {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  min-width: 15rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 4px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 8%);
  z-index: 65;
}
.search-results button {
  display: flex;
  width: 100%;
  border: 0;
  gap: 12px;
  text-align: left;
  align-items: center;
  font-size: 14px;
  min-height: 36px;
  padding: 8px;
}
.search-results button span:nth-child(2) {
  flex: 1;
}
.search-results p {
  padding: 8px;
  margin: 0;
  font-size: 13px;
}
@media (max-width: 600px) {
  kbd {
    display: none;
    font-size: 12px;
  line-height: 20px;
  min-width: 20px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--card);
}
  .project-search {
    max-width: none;
  }
  .project-search form {
  padding: 0 12px;
    gap: 8px;
  min-height: 36px;
  border-radius: 8px;
}
}
</style>
